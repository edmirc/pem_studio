from decimal import Decimal

from django.db import migrations


def criar(apps, schema_editor):
    Impressora = apps.get_model('encomendas', 'Impressora')
    if not Impressora.objects.filter(modelo__icontains='U1').exists():
        Impressora.objects.create(nome='U1', modelo='Snapmaker U1', potencia_media_w=200, custo_hora=Decimal('2.00'))


def desfazer(apps, schema_editor):
    apps.get_model('encomendas', 'Impressora').objects.filter(nome='U1', modelo='Snapmaker U1').delete()


class Migration(migrations.Migration):
    dependencies = [('encomendas', '0003_solicitacoes')]
    operations = [migrations.RunPython(criar, desfazer)]
