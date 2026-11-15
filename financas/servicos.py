"""
Regras do financeiro:
- em que fatura cai cada parcela de uma compra no cartão de crédito;
- geração automática das contas a pagar a partir das compras;
- lançamento mensal das despesas fixas.
"""
import calendar
import re
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

D0 = Decimal('0')


def somar_meses(d, n):
    m = d.month - 1 + n
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def dia_no_mes(ano, mes, dia):
    return date(ano, mes, min(max(1, dia), calendar.monthrange(ano, mes)[1]))


def vencimento_fatura(conta, data_compra, n=0):
    """
    Vencimento da fatura em que cai a parcela n (0 = primeira) de uma compra feita em data_compra.
    Compra no dia do fechamento ou depois entra na fatura seguinte.
    Sem fechamento/vencimento configurados: um mês depois da compra, por parcela.
    """
    if not (conta and conta.dia_fechamento and conta.dia_vencimento):
        return somar_meses(data_compra, n + 1)
    fech, venc = conta.dia_fechamento, conta.dia_vencimento
    fecha_em = date(data_compra.year, data_compra.month, 1)
    fech_neste_mes = min(fech, calendar.monthrange(data_compra.year, data_compra.month)[1])
    if data_compra.day >= fech_neste_mes:
        fecha_em = somar_meses(fecha_em, 1)
    # o vencimento é depois do fechamento: se o dia do vencimento é menor, é no mês seguinte
    venc_mes = somar_meses(fecha_em, 1) if venc <= fech else fecha_em
    venc_mes = somar_meses(venc_mes, n)
    return dia_no_mes(venc_mes.year, venc_mes.month, venc)


def dividir(valor, partes):
    """Divide em parcelas com centavos exatos (a diferença vai na primeira)."""
    valor = Decimal(valor)
    base = (valor / partes).quantize(Decimal('0.01'))
    lista = [base] * partes
    lista[0] += valor - base * partes
    return lista


def _parcelas(texto):
    if isinstance(texto, int):
        return max(1, texto)
    achado = re.search(r'\d+', str(texto or ''))
    return max(1, min(int(achado.group()) if achado else 1, 48))


def _dados_da_compra(obj):
    from .models import Categoria, CompraFilamento, CompraInsumo
    if isinstance(obj, CompraFilamento):
        return {'campo': 'compra_filamento', 'categoria': Categoria.FILAMENTO,
                'descricao': f'Filamento: {obj.qnt}× {obj.filamento.name} {obj.filamento.color}'.strip(),
                'parcelas': obj.parcelas}
    if isinstance(obj, CompraInsumo):
        return {'campo': 'compra_insumo', 'categoria': Categoria.INSUMOS,
                'descricao': f'Insumo: {obj.insumo}', 'parcelas': obj.parcelas}
    return {'campo': 'despesa', 'categoria': Categoria.OUTROS, 'descricao': obj.saida, 'parcelas': obj.parcela}


@transaction.atomic
def gerar_da_compra(obj, Lancamento=None):
    """(Re)cria as contas a pagar de uma compra. Não mexe se alguma parcela já foi paga à mão."""
    if Lancamento is None:
        from .models import Lancamento
    d = _dados_da_compra(obj)
    filtro = {d['campo']: obj}
    existentes = Lancamento.objects.filter(**filtro)
    if existentes.filter(pago_em__isnull=False, baixa_automatica=False).exists():
        return 0
    existentes.delete()
    if not obj.valor:
        return 0

    hoje = timezone.localdate()
    conta = obj.pagamento
    n = _parcelas(d['parcelas'])
    credito = bool(conta and conta.operacao == 'CREDITO')
    if not credito and n == 1:
        vencs = [obj.date]                                  # Pix, débito, dinheiro: pago na hora
    elif credito:
        vencs = [vencimento_fatura(conta, obj.date, i) for i in range(n)]
    else:
        vencs = [somar_meses(obj.date, i) for i in range(n)]  # boleto/carnê parcelado
    for i, (venc, valor) in enumerate(zip(vencs, dividir(obj.valor, n)), start=1):
        pago = venc < hoje or (not credito and venc <= hoje)
        Lancamento.objects.create(
            tipo='PAGAR', descricao=d['descricao'][:200], categoria=d['categoria'], valor=valor,
            vencimento=venc, conta=conta, parcela=i, parcelas=n,
            pago_em=venc if pago else None, baixa_automatica=pago, **filtro)
    return n


def gerar_recorrentes(ate=None):
    """Lança as despesas fixas ativas do mês atual e do próximo (não duplica)."""
    from .models import DespesaFixa, Lancamento
    hoje = timezone.localdate()
    ate = ate or somar_meses(date(hoje.year, hoje.month, 1), 1)
    criados = 0
    for fixa in DespesaFixa.objects.filter(ativa=True, valor__isnull=False).select_related('conta'):
        inicio = date(fixa.criado_em.year, fixa.criado_em.month, 1) if fixa.criado_em else date(hoje.year, hoje.month, 1)
        mes = max(inicio, date(hoje.year, hoje.month, 1))
        while mes <= ate:
            if not Lancamento.objects.filter(recorrente=fixa, competencia=mes).exists():
                cobranca = dia_no_mes(mes.year, mes.month, fixa.dia_vencimento)
                credito = bool(fixa.conta and fixa.conta.operacao == 'CREDITO')
                venc = vencimento_fatura(fixa.conta, cobranca) if credito else cobranca
                Lancamento.objects.create(
                    tipo='PAGAR', descricao=fixa.descricao, categoria=fixa.categoria, valor=fixa.valor,
                    vencimento=venc, conta=fixa.conta, recorrente=fixa, competencia=mes)
                criados += 1
            mes = somar_meses(mes, 1)
    return criados


def gerar_parcelas_manuais(dados, n):
    """Cria um lançamento avulso em n parcelas mensais (ou nas faturas, se for cartão)."""
    from .models import Lancamento
    conta = dados.get('conta')
    credito = bool(conta and conta.operacao == 'CREDITO' and dados.get('tipo') == 'PAGAR')
    base = dados['vencimento']
    criados = []
    for i, valor in enumerate(dividir(dados['valor'], n), start=1):
        venc = vencimento_fatura(conta, base, i - 1) if credito else somar_meses(base, i - 1)
        criados.append(Lancamento.objects.create(
            tipo=dados['tipo'], descricao=dados['descricao'], categoria=dados['categoria'], valor=valor,
            vencimento=venc, conta=conta, cliente=dados.get('cliente'), observacao=dados.get('observacao', ''),
            parcela=i if n > 1 else None, parcelas=n if n > 1 else None,
            pago_em=dados.get('pago_em') if i == 1 else None))
    return criados


# ---------------------------------------------------------------------------
# Vendas -> recebimentos (valor líquido, já sem a taxa da maquininha)
# ---------------------------------------------------------------------------
def taxas_maquininha(Configuracao=None):
    """{forma: taxa %} das Configurações (débito e crédito à vista)."""
    if Configuracao is None:
        from encomendas.models import Configuracao
    cfg = Configuracao.objects.order_by('pk').first()
    if not cfg:
        return {'DEBITO': Decimal('0.89'), 'CREDITO': Decimal('3.15')}
    return {'DEBITO': cfg.taxa_debito, 'CREDITO': cfg.taxa_credito_1x}


NOMES_FORMA = {'PIX': 'Pix', 'DEBITO': 'Débito', 'CREDITO': 'Crédito', 'DINHEIRO': 'Dinheiro'}


def _liquido(bruto, forma, taxas):
    taxa = (Decimal(bruto) * taxas.get(forma, D0) / 100).quantize(Decimal('0.01'))
    return Decimal(bruto) - taxa, taxa


def _obs(bruto, taxa):
    from painel.utils import brl
    return f'Bruto {brl(bruto)} · taxa da maquininha {brl(taxa)}' if taxa else ''


def gerar_da_feira(feira, Lancamento=None, Feiras=None, taxas=None):
    """Um recebimento por forma de pagamento da feira, na data da feira."""
    if Lancamento is None:
        from .models import Lancamento
    if Feiras is None:
        from vendas.models import Feiras
    taxas = taxas or taxas_maquininha()
    existentes = Lancamento.objects.filter(feira=feira)
    mexidos = set(existentes.filter(baixa_automatica=False).values_list('forma', flat=True))
    existentes.filter(baixa_automatica=True).delete()
    totais = (Feiras.objects.filter(nomeFeira=feira).order_by().values('pagment')
              .annotate(t=models_sum('value')))
    for l in totais:
        forma, bruto = l['pagment'], l['t'] or D0
        if not bruto or forma in mexidos:
            continue
        liquido, taxa = _liquido(bruto, forma, taxas)
        Lancamento.objects.create(
            tipo='RECEBER', categoria='VENDA', valor=liquido, vencimento=feira.date, pago_em=feira.date,
            descricao=f'Vendas {feira.name} · {NOMES_FORMA.get(forma, forma)}'[:200], feira=feira, forma=forma,
            observacao=_obs(bruto, taxa), baixa_automatica=True)


def gerar_da_venda_interna(venda, Lancamento=None, taxas=None):
    if Lancamento is None:
        from .models import Lancamento
    existente = Lancamento.objects.filter(venda_interna=venda).first()
    if existente and not existente.baixa_automatica:
        return  # foi ajustado à mão (ex.: virou fiado): não mexe
    if existente:
        existente.delete()
    if not venda.valor:
        return
    taxas = taxas or taxas_maquininha()
    liquido, taxa = _liquido(venda.valor, venda.pagment, taxas)
    qnt = venda.qnt if venda.qnt is not None else 1
    desc = f'Venda direta: {qnt}× {venda.product.product}' if qnt else f'Sinal de encomenda: {venda.product.product}'
    Lancamento.objects.create(
        tipo='RECEBER', categoria='VENDA', valor=liquido, vencimento=venda.date, pago_em=venda.date,
        descricao=desc[:200], venda_interna=venda, cliente_id=venda.client_id, forma=venda.pagment,
        observacao=_obs(venda.valor, taxa), baixa_automatica=True)


def models_sum(campo):
    from django.db.models import Sum
    return Sum(campo)


def gerar_do_sinal(pedido, Lancamento=None):
    """Sinal recebido de uma encomenda entra no caixa na data em que foi pago."""
    if Lancamento is None:
        from .models import Lancamento
    existente = Lancamento.objects.filter(pedido=pedido).first()
    if existente and not existente.baixa_automatica:
        return
    if existente:
        existente.delete()
    if not pedido.sinal_recebido or pedido.vendas_geradas:
        return
    liquido, taxa = _liquido(pedido.sinal_recebido, pedido.sinal_forma, taxas_maquininha())
    data = pedido.sinal_data or timezone.localdate()
    Lancamento.objects.create(
        tipo='RECEBER', categoria='VENDA', valor=liquido, vencimento=data, pago_em=data,
        descricao=f'Sinal da encomenda {pedido.numero}'[:200], pedido=pedido, cliente_id=pedido.cliente_id,
        forma=pedido.sinal_forma, observacao=_obs(pedido.sinal_recebido, taxa), baixa_automatica=True)
