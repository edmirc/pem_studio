from django.utils import timezone
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cadastro.models import CadClientes, CadFeiras, Category, Product
from vendas.models import Feiras, FormaPagamento, Precificacao, VendasInternas

from encomendas.models import ABERTAS, ETAPAS, Orcamento, Pedido, Solicitacao, StatusOrcamento

from . import relatorios as rel
from .crud import atualizar_totais_feira
from .utils import MESES_CURTOS, ler_mes, mes_anterior, mes_seguinte, nome_mes


def _f(lista):
    """Converte Decimals para float (para os gráficos)."""
    return [float(v) for v in lista]


def _mei(ano, faturado):
    limite = rel.limite_mei(ano)
    pct = float(faturado * 100 / limite) if limite else 0
    return {'ano': ano, 'limite': limite, 'faturado': faturado, 'pct': round(pct, 1),
            'resta': limite - faturado, 'nivel': 'perigo' if pct >= 90 else 'alerta' if pct >= 70 else ''}


# --------------------------------------------------------------------------
# Painel inicial
# --------------------------------------------------------------------------
@login_required
def inicio(request):
    hoje = timezone.localdate()
    ano, mes = hoje.year, hoje.month
    resumo = rel.resumo_mes(ano, mes)
    pa, pm = mes_anterior(ano, mes)
    anterior = rel.resumo_mes(pa, pm)

    feiras, internas = rel.vendas_do_mes(ano, mes)
    produtos = rel.por_produto(feiras, internas)[:6]
    meses = rel.resumo_ano(ano)

    def variacao(atual, antes):
        if not antes:
            return None
        return round(float((atual - antes) * 100 / antes))

    from datetime import timedelta
    pedidos_ativos = list(Pedido.objects.filter(status__in=ETAPAS).select_related('cliente')
                          .filter(prazo__lte=hoje + timedelta(days=7)).order_by('prazo'))
    from financas.models import Lancamento
    from financas.servicos import gerar_recorrentes
    gerar_recorrentes()
    abertos = Lancamento.objects.filter(tipo='PAGAR', pago_em__isnull=True)
    atrasadas = abertos.filter(vencimento__lt=hoje)
    semana = abertos.filter(vencimento__gte=hoje, vencimento__lte=hoje + timedelta(days=7))
    fin = {
        'atrasado': atrasadas.aggregate(t=Sum('valor'))['t'] or 0, 'atrasado_n': atrasadas.count(),
        'semana': semana.aggregate(t=Sum('valor'))['t'] or 0, 'semana_n': semana.count(),
    }
    return render(request, 'painel/inicio.html', {
        'menu': 'inicio',
        'fin': fin,
        'mei': _mei(ano, sum(m['receita'] for m in meses)),
        'pedidos_semana': pedidos_ativos,
        'pedidos_em_producao': Pedido.objects.filter(status__in=ETAPAS).count(),
        'solicitacoes_abertas': Solicitacao.objects.filter(status__in=ABERTAS).count(),
        'orcamentos_aguardando': Orcamento.objects.filter(status=StatusOrcamento.ENVIADO).count(),
        'mes_nome': nome_mes(ano, mes),
        'mes_valor': f'{ano}-{mes:02d}',
        'r': resumo,
        'var_receita': variacao(resumo['receita'], anterior['receita']),
        'var_despesas': variacao(resumo['despesas'], anterior['despesas']),
        'produtos': produtos,
        'pagamentos': rel.por_pagamento(feiras, internas),
        'ultimas_feiras': CadFeiras.objects.filter(date__lte=hoje).order_by('-date')[:5],
        'aniversariantes': CadClientes.objects.filter(date_nasc__month=mes).order_by('date_nasc__day'),
        'grafico': ({
            'rotulos': MESES_CURTOS,
            'receita': _f(m['receita'] for m in meses),
            'despesas': _f(m['despesas'] for m in meses),
        }),
        'ano': ano,
    })


# --------------------------------------------------------------------------
# Venda na feira (PDV)
# --------------------------------------------------------------------------
@login_required
def pdv_escolher(request):
    feiras = CadFeiras.objects.order_by('-date')[:30]
    hoje = timezone.localdate()
    feira_hoje = next((f for f in feiras if f.date == hoje), None)
    if feira_hoje and 'escolher' not in request.GET:
        return redirect('painel:pdv', pk=feira_hoje.pk)
    return render(request, 'painel/pdv_escolher.html', {'menu': 'pdv', 'feiras': feiras, 'hoje': hoje})


def _ctx_vendas_feira(feira):
    qs = Feiras.objects.filter(nomeFeira=feira).select_related('product').order_by('-id')
    vendas = list(qs)
    for v in vendas:
        v.unitario = (v.value / v.qnt) if v.qnt else v.value
    totais = {k: Decimal('0') for k, _ in FormaPagamento.choices}
    # order_by() vazio: sem ele o GROUP BY inclui o id e cada venda vira um grupo
    for l in qs.order_by().values('pagment').annotate(t=Sum('value')):
        totais[l['pagment']] = totais.get(l['pagment'], Decimal('0')) + (l['t'] or Decimal('0'))
    nomes = dict(FormaPagamento.choices)
    return {
        'feira': feira,
        'vendas': vendas,
        'totais': [{'nome': nomes.get(k, k), 'total': v} for k, v in totais.items()],
        'total_geral': sum(totais.values()),
        'itens': sum(v.qnt for v in vendas),
    }


@login_required
def pdv(request, pk):
    feira = get_object_or_404(CadFeiras, pk=pk)
    precos = {p.product_id: (p.vanda or p.sugerido) for p in Precificacao.objects.all()}
    # produtos mais vendidos aparecem primeiro
    mais_vendidos = dict(Feiras.objects.order_by().values_list('product_id').annotate(q=Sum('qnt')))
    produtos = sorted(Product.objects.select_related('category'),
                      key=lambda p: (-(mais_vendidos.get(p.id) or 0), p.product.lower()))
    ctx = _ctx_vendas_feira(feira)
    ctx.update({
        'menu': 'pdv',
        'produtos': [{'p': p, 'preco': precos.get(p.id)} for p in produtos],
        'categorias': Category.objects.all(),
        'formas': FormaPagamento.choices,
    })
    return render(request, 'painel/pdv.html', ctx)


@login_required
@require_POST
def pdv_adicionar(request, pk):
    feira = get_object_or_404(CadFeiras, pk=pk)
    produto = get_object_or_404(Product, pk=request.POST.get('produto'))
    try:
        qnt = max(1, int(request.POST.get('qnt', 1)))
        if request.POST.get('preco', '') != '':
            # preço unitário × quantidade: o servidor faz a conta
            unitario = Decimal(request.POST['preco'].replace(',', '.'))
            valor = (unitario * qnt).quantize(Decimal('0.01'))
        else:
            valor = Decimal(request.POST.get('valor', '').replace(',', '.'))
    except (ValueError, InvalidOperation):
        return HttpResponseBadRequest('Quantidade ou valor inválido')
    pagamento = request.POST.get('pagamento')
    if pagamento not in dict(FormaPagamento.choices) or valor < 0:
        return HttpResponseBadRequest('Forma de pagamento inválida')
    Feiras.objects.create(nomeFeira=feira, product=produto, qnt=qnt, value=valor, pagment=pagamento)
    atualizar_totais_feira(feira)
    return render(request, 'painel/parciais/pdv_vendas.html', _ctx_vendas_feira(feira))


@login_required
@require_POST
def pdv_apagar(request, pk, venda_id):
    feira = get_object_or_404(CadFeiras, pk=pk)
    Feiras.objects.filter(nomeFeira=feira, pk=venda_id).delete()
    atualizar_totais_feira(feira)
    return render(request, 'painel/parciais/pdv_vendas.html', _ctx_vendas_feira(feira))


@login_required
def fechamento_feira(request, pk):
    feira = get_object_or_404(CadFeiras, pk=pk)
    ctx = _ctx_vendas_feira(feira)
    vendas = Feiras.objects.filter(nomeFeira=feira)
    ctx['produtos'] = rel.por_produto(vendas, VendasInternas.objects.none())
    ctx['custo_total'] = sum((p['custo'] or 0) for p in ctx['produtos'])
    ctx['lucro'] = ctx['total_geral'] - ctx['custo_total']
    ctx['menu'] = 'pdv'
    return render(request, 'painel/fechamento_feira.html', ctx)


# --------------------------------------------------------------------------
# Cliente (ficha com histórico)
# --------------------------------------------------------------------------
@login_required
def cliente(request, pk):
    c = get_object_or_404(CadClientes, pk=pk)
    compras = VendasInternas.objects.filter(client=c).select_related('product').order_by('-date', '-id')
    return render(request, 'painel/cliente.html', {
        'menu': 'clientes', 'c': c, 'compras': compras,
        'total': compras.aggregate(t=Sum('valor'))['t'] or 0,
    })


# --------------------------------------------------------------------------
# Relatórios
# --------------------------------------------------------------------------
@login_required
def relatorio_mensal(request):
    ano, mes = ler_mes(request.GET.get('mes'))
    feiras, internas = rel.vendas_do_mes(ano, mes)
    cf, ci, outras = rel.compras_do_mes(ano, mes)
    produtos = rel.por_produto(feiras, internas)
    r = rel.resumo_mes(ano, mes)
    custo_vendido = sum((p['custo'] or 0) for p in produtos)
    pa, pm = mes_anterior(ano, mes)
    sa, sm = mes_seguinte(ano, mes)
    import calendar
    return render(request, 'painel/relatorio_mensal.html', {
        'menu': 'rel-mensal',
        'mes_nome': nome_mes(ano, mes), 'mes_valor': f'{ano}-{mes:02d}',
        'anterior': f'{pa}-{pm:02d}', 'seguinte': f'{sa}-{sm:02d}',
        'r': r,
        'pagamentos': rel.por_pagamento(feiras, internas),
        'produtos': produtos,
        'categorias': rel.por_categoria(produtos),
        'feiras': rel.por_feira(feiras),
        'internas': internas.select_related('client', 'product').order_by('date'),
        'compras_filamento': cf.order_by('date'),
        'compras_insumo': ci.order_by('date'),
        'outras': outras.order_by('date'),
        'custo_vendido': custo_vendido,
        'lancamentos': rel.lancamentos_do_mes(ano, mes).select_related('conta').order_by('ref', 'id'),
        'total_compras_lanc': r['despesas'] - r['taxas'] + r['retiradas'],
        'sem_custo': [p['produto'] for p in produtos if p['custo'] is None],
        'grafico': ({
            'rotulos': [str(d) for d in range(1, calendar.monthrange(ano, mes)[1] + 1)],
            'valores': _f(rel.por_dia(ano, mes, feiras, internas)),
        }),
    })


@login_required
def relatorio_anual(request):
    try:
        ano = int(request.GET.get('ano', timezone.localdate().year))
    except ValueError:
        ano = timezone.localdate().year
    meses = rel.resumo_ano(ano)
    for m in meses:
        m['nome'] = MESES_CURTOS[m['mes'] - 1]
        m['link'] = f'{ano}-{m["mes"]:02d}'
    chaves = ['receita_feiras', 'receita_internas', 'receita', 'desp_filamento', 'desp_insumos',
              'desp_outras', 'desp_fixas', 'taxas', 'retiradas', 'despesas', 'resultado', 'sobra', 'itens']
    totais = {k: sum(m[k] for m in meses) for k in chaves}
    return render(request, 'painel/relatorio_anual.html', {
        'menu': 'rel-anual', 'ano': ano, 'meses': meses, 't': totais, 'mei': _mei(ano, totais['receita']),
        'grafico': ({
            'rotulos': MESES_CURTOS,
            'receita': _f(m['receita'] for m in meses),
            'despesas': _f(m['despesas'] for m in meses),
            'resultado': _f(m['resultado'] for m in meses),
        }),
    })
