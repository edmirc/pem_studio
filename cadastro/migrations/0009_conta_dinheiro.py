"""Cria a forma de pagamento "Dinheiro (caixa)" para usar em compras, despesas e contas."""
from django.db import migrations


def criar(apps, schema_editor):
    Contas = apps.get_model('cadastro', 'Contas')
    if not Contas.objects.filter(operacao='DINHEIRO').exists():
        Contas.objects.create(apelido='Dinheiro (caixa)', banco='Dinheiro', name='Caixa da loja', operacao='DINHEIRO')


class Migration(migrations.Migration):
    dependencies = [('cadastro', '0008_dinheiro')]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
