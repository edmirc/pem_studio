"""Transforma as vendas que já existem (feiras e vendas diretas) e os sinais de encomendas
ainda não entregues em recebimentos no financeiro, com o valor líquido da maquininha."""
from django.db import migrations


def criar(apps, schema_editor):
    from financas.servicos import _liquido, _obs, gerar_da_feira, gerar_da_venda_interna, taxas_maquininha
    Lancamento = apps.get_model('financas', 'Lancamento')
    Feiras = apps.get_model('vendas', 'Feiras')
    taxas = taxas_maquininha(apps.get_model('encomendas', 'Configuracao'))

    ids_feiras = Feiras.objects.order_by().values_list('nomeFeira_id', flat=True).distinct()
    for feira in apps.get_model('cadastro', 'CadFeiras').objects.filter(pk__in=list(ids_feiras)):
        gerar_da_feira(feira, Lancamento=Lancamento, Feiras=Feiras, taxas=taxas)
    for venda in apps.get_model('vendas', 'VendasInternas').objects.select_related('product'):
        gerar_da_venda_interna(venda, Lancamento=Lancamento, taxas=taxas)
    for p in apps.get_model('encomendas', 'Pedido').objects.filter(vendas_geradas=False, sinal_recebido__gt=0):
        liquido, taxa = _liquido(p.sinal_recebido, p.sinal_forma, taxas)
        data = p.sinal_data or p.data
        Lancamento.objects.create(tipo='RECEBER', categoria='VENDA', valor=liquido, vencimento=data, pago_em=data,
                                  descricao=f'Sinal da encomenda PED-{p.pk:04d}', pedido_id=p.pk, cliente_id=p.cliente_id,
                                  forma=p.sinal_forma, observacao=_obs(p.sinal_recebido, taxa), baixa_automatica=True)


class Migration(migrations.Migration):
    dependencies = [
        ('financas', '0005_recebimentos_das_vendas'),
        ('encomendas', '0003_solicitacoes'),
        ('vendas', '0005_vendasinternas_qnt'),
    ]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
