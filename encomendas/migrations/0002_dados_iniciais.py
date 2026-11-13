from django.db import migrations

IMPRESSORAS = [
    # nome, modelo, consumo médio estimado imprimindo PLA (W)
    ('K2 Plus', 'Creality K2 Plus', 250),
    ('K2 Pro 1', 'Creality K2 Pro', 200),
    ('K2 Pro 2', 'Creality K2 Pro', 200),
    ('A1', 'Bambu Lab A1', 95),
    ('SparkX i7', 'Creality SparkX i7', 120),
]


def criar(apps, schema_editor):
    Impressora = apps.get_model('encomendas', 'Impressora')
    Configuracao = apps.get_model('encomendas', 'Configuracao')
    if not Impressora.objects.exists():
        for nome, modelo, w in IMPRESSORAS:
            Impressora.objects.create(nome=nome, modelo=modelo, potencia_media_w=w)
    if not Configuracao.objects.exists():
        Configuracao.objects.create()


class Migration(migrations.Migration):
    dependencies = [('encomendas', '0001_initial')]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
