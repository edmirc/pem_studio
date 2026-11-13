"""Dados de custo usados pela calculadora (filamento, insumos, impressoras)."""
from decimal import Decimal, ROUND_FLOOR

from django.db.models import F, Sum

from cadastro.models import Filment, Insumo
from financas.models import CompraFilamento, CompraInsumo

from .models import Configuracao, Impressora


def custo_kg_filamentos():
    """{filamento_id: R$/kg} pela média ponderada de todas as compras."""
    linhas = (CompraFilamento.objects.order_by().values('filamento_id')
              .annotate(valor=Sum('valor'), gramas=Sum(F('qnt') * F('peso'))))
    return {l['filamento_id']: (l['valor'] * 1000 / l['gramas']).quantize(Decimal('0.01'))
            for l in linhas if l['gramas']}


def custo_kg_medio():
    tot = CompraFilamento.objects.aggregate(valor=Sum('valor'), gramas=Sum(F('qnt') * F('peso')))
    if tot['gramas']:
        return (tot['valor'] * 1000 / tot['gramas']).quantize(Decimal('0.01'))
    return Configuracao.atual().custo_kg_padrao


def custo_insumos():
    """{insumo_id: custo unitário da compra mais recente}"""
    custos = {}
    for c in CompraInsumo.objects.order_by('date', 'id'):
        if c.qnt:
            custos[c.insumo_id] = (c.valor / c.qnt).quantize(Decimal('0.0001'))
    return custos


def dados_calculadora():
    cfg = Configuracao.atual()
    kg = custo_kg_filamentos()
    medio = custo_kg_medio()
    ins = custo_insumos()
    return {
        'config': {
            'preco_kwh': float(cfg.preco_kwh),
            'valor_hora_trabalho': float(cfg.valor_hora_trabalho),
            'taxa_falha': float(cfg.taxa_falha),
            'lucro_padrao': float(cfg.lucro_padrao),
            'custo_kg_medio': float(medio),
            'taxas': [{'nome': n, 'parcelas': p, 'taxa': float(t)} for n, p, t in cfg.taxas()],
        },
        'impressoras': [{'id': i.id, 'nome': i.nome, 'modelo': i.modelo, 'custo_hora': float(i.custo_hora),
                         'watts': i.potencia_media_w}
                        for i in Impressora.objects.filter(ativa=True)],
        'filamentos': [{'id': f.id, 'nome': f'{f.name} · {f.filamentBrand} ({f.filamentType})',
                        'custo_kg': float(kg[f.id]) if f.id in kg else None}
                       for f in Filment.objects.select_related('filamentBrand', 'filamentType')],
        'insumos': [{'id': i.id, 'nome': i.name, 'unidade': i.get_unidade_display(),
                     'custo': float(ins[i.id]) if i.id in ins else None}
                    for i in Insumo.objects.all()],
    }


def campos_precificacao(calculo):
    """
    Converte o resultado da calculadora (por peça) nos campos da Precificação antiga,
    de forma que o custo calculado por ela (horas × 2 + filamento + embalagem + acessórios)
    fique igual ao custo da calculadora.
    """
    p = calculo['partes']
    custo = Decimal(str(calculo['custo_peca']))
    filamento = (Decimal(str(p['filamento'])) + Decimal(str(p['falha']))).quantize(Decimal('0.01'))
    embalagem = Decimal(str(p['insumos'])).quantize(Decimal('0.01'))
    horas_peca = Decimal(str(calculo.get('horas_peca', 0)))
    horas = int(horas_peca.to_integral_value(rounding=ROUND_FLOOR))
    acessorios = custo - horas * 2 - filamento - embalagem
    if acessorios < 0:
        horas = 0
        acessorios = custo - filamento - embalagem
    return {
        'impressao': horas,
        'filament': filamento,
        'embalagem': embalagem,
        'acessorios': acessorios.quantize(Decimal('0.01')),
        'vanda': Decimal(str(calculo['preco_peca'])).quantize(Decimal('0.01')),
    }
