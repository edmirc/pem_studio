"""Cálculos usados no painel inicial e nos relatórios."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth

from financas.models import CompraFilamento, CompraInsumo, Compras
from vendas.models import Feiras, FormaPagamento, Precificacao, VendasInternas

ZERO = Decimal('0')
DEC = Value(ZERO)


def _soma(qs, campo):
    return qs.aggregate(t=Coalesce(Sum(campo), DEC))['t']


def vendas_do_mes(ano, mes):
    feiras = Feiras.objects.filter(nomeFeira__date__year=ano, nomeFeira__date__month=mes)
    internas = VendasInternas.objects.filter(date__year=ano, date__month=mes)
    return feiras, internas


def compras_do_mes(ano, mes):
    filtro = {'date__year': ano, 'date__month': mes}
    return (CompraFilamento.objects.filter(**filtro).select_related('filamento', 'pagamento'),
            CompraInsumo.objects.filter(**filtro).select_related('insumo', 'pagamento'),
            Compras.objects.filter(**filtro).select_related('pagamento'))


def resumo_mes(ano, mes):
    """Totais principais de um mês (usado no painel e no relatório)."""
    feiras, internas = vendas_do_mes(ano, mes)
    cf, ci, outras = compras_do_mes(ano, mes)
    r = {
        'receita_feiras': _soma(feiras, 'value'),
        'receita_internas': _soma(internas, 'valor'),
        'itens': (feiras.aggregate(t=Coalesce(Sum('qnt'), 0))['t'] +
                  internas.aggregate(t=Coalesce(Sum(Coalesce('qnt', 1)), 0))['t']),
        'vendas': feiras.count() + internas.count(),
        'desp_filamento': _soma(cf, 'valor'),
        'desp_insumos': _soma(ci, 'valor'),
        'desp_outras': _soma(outras, 'valor'),
    }
    r['receita'] = r['receita_feiras'] + r['receita_internas']
    r['despesas'] = r['desp_filamento'] + r['desp_insumos'] + r['desp_outras']
    r['resultado'] = r['receita'] - r['despesas']
    r['ticket'] = (r['receita'] / r['vendas']) if r['vendas'] else ZERO
    return r


def por_pagamento(feiras, internas):
    totais = {k: ZERO for k, _ in FormaPagamento.choices}
    for qs, campo in ((feiras, 'value'), (internas, 'valor')):
        for linha in qs.order_by().values('pagment').annotate(t=Sum(campo)):
            totais[linha['pagment']] = totais.get(linha['pagment'], ZERO) + (linha['t'] or ZERO)
    nomes = dict(FormaPagamento.choices)
    return [{'nome': nomes.get(k, k), 'total': v} for k, v in totais.items()]


def por_produto(feiras, internas):
    custos = dict(Precificacao.objects.values_list('product_id', 'custo'))
    dados = {}
    for qs, campo_valor, campo_qnt in ((feiras, 'value', 'qnt'), (internas, 'valor', Coalesce('qnt', 1))):
        linhas = qs.order_by().values('product_id', 'product__product', 'product__category__category') \
                   .annotate(qnt=Sum(campo_qnt), total=Sum(campo_valor))
        for l in linhas:
            d = dados.setdefault(l['product_id'], {
                'produto': l['product__product'], 'categoria': l['product__category__category'],
                'qnt': 0, 'total': ZERO})
            d['qnt'] += l['qnt'] or 0
            d['total'] += l['total'] or ZERO
    for pid, d in dados.items():
        custo = custos.get(pid)
        d['custo'] = (custo * d['qnt']) if custo is not None else None
        d['lucro'] = (d['total'] - d['custo']) if d['custo'] is not None else None
    return sorted(dados.values(), key=lambda d: d['total'], reverse=True)


def por_categoria(produtos):
    cat = defaultdict(lambda: {'qnt': 0, 'total': ZERO})
    for p in produtos:
        c = cat[p['categoria'] or 'Sem categoria']
        c['qnt'] += p['qnt']
        c['total'] += p['total']
    return sorted(({'nome': k, **v} for k, v in cat.items()), key=lambda d: d['total'], reverse=True)


def por_feira(feiras):
    return list(feiras.order_by().values('nomeFeira', 'nomeFeira__name', 'nomeFeira__date', 'nomeFeira__local')
                .annotate(itens=Sum('qnt'), vendas=Count('id'), total=Sum('value'))
                .order_by('nomeFeira__date'))


def por_dia(ano, mes, feiras, internas):
    import calendar
    dias = calendar.monthrange(ano, mes)[1]
    serie = [ZERO] * dias
    for l in feiras.order_by().values('nomeFeira__date').annotate(t=Sum('value')):
        serie[l['nomeFeira__date'].day - 1] += l['t'] or ZERO
    for l in internas.order_by().values('date').annotate(t=Sum('valor')):
        serie[l['date'].day - 1] += l['t'] or ZERO
    return serie


def resumo_ano(ano):
    """Lista com 12 meses: receitas e despesas por tipo."""
    meses = [{'mes': m, 'receita_feiras': ZERO, 'receita_internas': ZERO, 'desp_filamento': ZERO,
              'desp_insumos': ZERO, 'desp_outras': ZERO, 'itens': 0} for m in range(1, 13)]

    def juntar(qs, campo_data, campo_valor, chave, campo_qnt=None):
        anot = {'t': Sum(campo_valor)}
        if campo_qnt is not None:
            anot['q'] = Sum(campo_qnt)
        for l in qs.filter(**{f'{campo_data}__year': ano}).order_by().annotate(m=ExtractMonth(campo_data)) \
                   .values('m').annotate(**anot):
            meses[l['m'] - 1][chave] += l['t'] or ZERO
            if campo_qnt is not None:
                meses[l['m'] - 1]['itens'] += l['q'] or 0

    juntar(Feiras.objects.all(), 'nomeFeira__date', 'value', 'receita_feiras', 'qnt')
    juntar(VendasInternas.objects.all(), 'date', 'valor', 'receita_internas', Coalesce('qnt', 1))
    juntar(CompraFilamento.objects.all(), 'date', 'valor', 'desp_filamento')
    juntar(CompraInsumo.objects.all(), 'date', 'valor', 'desp_insumos')
    juntar(Compras.objects.all(), 'date', 'valor', 'desp_outras')

    for m in meses:
        m['receita'] = m['receita_feiras'] + m['receita_internas']
        m['despesas'] = m['desp_filamento'] + m['desp_insumos'] + m['desp_outras']
        m['resultado'] = m['receita'] - m['despesas']
    return meses
