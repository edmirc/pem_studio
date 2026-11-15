"""Regras de negócio: aprovar orçamento, gerar vendas na entrega, mensagem de WhatsApp."""
import re
from decimal import Decimal
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone

from cadastro.models import CadClientes, Category, Product
from painel.utils import brl
from vendas.models import VendasInternas

from .models import Configuracao, ItemPedido, Pedido, StatusOrcamento, StatusPedido

D0 = Decimal('0')


def so_digitos(texto):
    return re.sub(r'\D', '', texto or '')


class ErroNegocio(Exception):
    pass


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
def cliente_do_orcamento(orc):
    """Usa o cliente cadastrado ou encontra/cria um pelo telefone."""
    if orc.cliente_id:
        return orc.cliente
    nome = (orc.nome_cliente or '').strip()
    fone = so_digitos(orc.telefone)
    if not nome:
        raise ErroNegocio('Informe o nome do cliente para aprovar o orçamento.')
    if len(fone) < 8:
        raise ErroNegocio('Informe o telefone do cliente para aprovar (ele vira cadastro de cliente).')
    for c in CadClientes.objects.all().only('id', 'telefone', 'name'):
        if so_digitos(c.telefone).endswith(fone[-8:]) and len(so_digitos(c.telefone)) >= 8:
            return c
    existente = CadClientes.objects.filter(name__iexact=nome).first()
    if existente:
        nome = f'{nome} ({fone[-4:]})'
    telefone = orc.telefone.strip()[:15] if len(orc.telefone.strip()) <= 15 else fone[-11:]
    return CadClientes.objects.create(name=nome[:250], telefone=telefone)


# ---------------------------------------------------------------------------
# Orçamento -> Pedido
# ---------------------------------------------------------------------------
@transaction.atomic
def aprovar_orcamento(orc):
    if hasattr(orc, 'pedido') and orc.pedido:
        return orc.pedido
    if not orc.itens.exists():
        raise ErroNegocio('O orçamento não tem itens.')
    cliente = cliente_do_orcamento(orc)
    if not orc.cliente_id:
        orc.cliente = cliente
    orc.status = StatusOrcamento.APROVADO
    orc.save()
    prazo = Pedido.prazo_padrao(orc.prazo_dias)
    sol = orc.solicitacao
    if sol and sol.prazo and sol.prazo >= timezone.localdate():
        prazo = sol.prazo  # data que o cliente pediu na solicitação
    if sol and not sol.cliente_id:
        sol.cliente = cliente
        sol.save(update_fields=['cliente'])
    pedido = Pedido.objects.create(
        orcamento=orc, cliente=cliente, prazo=prazo,
        desconto=orc.desconto, frete=orc.frete, observacoes=orc.observacoes,
        sinal_combinado=orc.valor_sinal,
    )
    for i in orc.itens.all():
        ItemPedido.objects.create(pedido=pedido, produto=i.produto, descricao=i.descricao, qnt=i.qnt,
                                  preco_unitario=i.preco_unitario, calculo=i.calculo)
    return pedido


# ---------------------------------------------------------------------------
# Entrega -> vendas diretas (entram nos relatórios)
# ---------------------------------------------------------------------------
def _produto_generico(nome):
    cat, _ = Category.objects.get_or_create(category='Encomendas')
    prod, _ = Product.objects.get_or_create(product=nome, defaults={'category': cat})
    return prod


def _distribuir(total, pesos):
    """Divide `total` proporcionalmente aos pesos, com centavos exatos."""
    soma = sum(pesos)
    if not soma:
        return [D0 for _ in pesos]
    partes = [(total * p / soma).quantize(Decimal('0.01')) for p in pesos]
    partes[-1] += total - sum(partes)
    return partes


@transaction.atomic
def entregar_pedido(pedido, forma_final, data=None):
    if pedido.vendas_geradas:
        raise ErroNegocio('Este pedido já foi entregue.')
    data = data or timezone.localdate()
    itens = list(pedido.itens.select_related('produto'))
    if not itens:
        raise ErroNegocio('O pedido não tem itens.')

    # linhas de venda: itens (com desconto distribuído) + frete
    subtotal = sum((i.total for i in itens), D0)
    valor_itens = max(D0, subtotal - pedido.desconto)
    valores = _distribuir(valor_itens, [i.total for i in itens])
    linhas = [(i.produto or _produto_generico('Peça personalizada'), i.qnt, v) for i, v in zip(itens, valores)]
    if pedido.frete:
        linhas.append((_produto_generico('Frete / entrega'), 0, pedido.frete))

    total = sum(v for _, _, v in linhas)
    sinal = min(pedido.sinal_recebido or D0, total)
    partes_sinal = _distribuir(sinal, [v for _, _, v in linhas]) if sinal else [D0] * len(linhas)
    forma_sinal = pedido.sinal_forma or forma_final

    for (produto, qnt, valor), p_sinal in zip(linhas, partes_sinal):
        if not p_sinal:
            VendasInternas.objects.create(date=data, client=pedido.cliente, product=produto, qnt=qnt,
                                          valor=valor, pagment=forma_final)
        else:
            # sinal e restante pagos de formas diferentes: duas linhas (a do sinal sem quantidade)
            VendasInternas.objects.create(date=pedido.sinal_data or data, client=pedido.cliente, product=produto,
                                          qnt=0, valor=p_sinal, pagment=forma_sinal)
            if valor - p_sinal:
                VendasInternas.objects.create(date=data, client=pedido.cliente, product=produto, qnt=qnt,
                                              valor=valor - p_sinal, pagment=forma_final)

    # o sinal agora está nas vendas (com a data dele): sai o lançamento provisório do sinal
    from financas.models import Lancamento
    Lancamento.objects.filter(pedido=pedido).delete()

    pedido.status = StatusPedido.ENTREGUE
    pedido.forma_final = forma_final
    pedido.entregue_em = data
    pedido.vendas_geradas = True
    pedido.save()


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------
def texto_orcamento(orc, cfg=None):
    cfg = cfg or Configuracao.atual()
    linhas = [f'Olá, {orc.nome_exibicao.split()[0].title()}! 😊',
              f'Segue o orçamento *{orc.numero}* da {cfg.nome_empresa}:', '']
    for i in orc.itens.all():
        linhas.append(f'• {i.qnt}× {i.nome} — {brl(i.total)}')
    linhas.append('')
    if orc.desconto or orc.frete:
        linhas.append(f'Subtotal: {brl(orc.subtotal)}')
        if orc.desconto:
            linhas.append(f'Desconto: -{brl(orc.desconto)}')
        if orc.frete:
            linhas.append(f'Entrega: {brl(orc.frete)}')
    linhas.append(f'*Total no Pix ou dinheiro: {brl(orc.total)}*')
    tabela = cfg.tabela_cartao(orc.total)
    ultima = tabela[-1]
    linhas.append(f'No cartão: até {ultima["parcelas"]}x de {brl(ultima["parcela"])} ({brl(ultima["total"])})')
    if orc.sinal_percentual:
        linhas.append('')
        linhas.append(f'Para iniciar a produção: sinal de {orc.sinal_percentual:.0f}% ({brl(orc.valor_sinal)}).')
    linhas.append(f'Prazo de produção: {orc.prazo_dias} dias após o sinal.')
    if orc.validade:
        linhas.append(f'Orçamento válido até {orc.validade:%d/%m/%Y}.')
    if orc.observacoes:
        linhas += ['', orc.observacoes]
    return '\n'.join(linhas)


def link_whatsapp(telefone, texto):
    fone = so_digitos(telefone)
    if fone and not fone.startswith('55') and len(fone) <= 11:
        fone = '55' + fone
    base = f'https://wa.me/{fone}' if fone else 'https://wa.me/'
    return f'{base}?text={quote(texto)}'
