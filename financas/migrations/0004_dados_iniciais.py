"""
- Cadastra as despesas fixas citadas (sem valor: ficam inativas até você preencher).
- Gera as contas a pagar das compras que já existem. Parcelas com vencimento já passado
  são marcadas como pagas; as futuras (faturas que ainda vão chegar) ficam em aberto.
"""
import re
from datetime import date

from django.db import migrations

FIXAS = [
    ('Água', 'CONTAS', 10),
    ('Energia elétrica', 'CONTAS', 10),
    ('Internet', 'CONTAS', 10),
    ('Telefone', 'CONTAS', 10),
    ('Assinatura Claude', 'ASSINATURA', 10),
    ('Assinatura Microsoft', 'ASSINATURA', 10),
    ('DAS do MEI', 'IMPOSTO', 20),
]


def _n(texto):
    if isinstance(texto, int):
        return max(1, texto)
    m = re.search(r'\d+', str(texto or ''))
    return max(1, min(int(m.group()) if m else 1, 48))


def criar(apps, schema_editor):
    from financas.servicos import dividir, somar_meses, vencimento_fatura
    DespesaFixa = apps.get_model('financas', 'DespesaFixa')
    Lancamento = apps.get_model('financas', 'Lancamento')
    if not DespesaFixa.objects.exists():
        for desc, cat, dia in FIXAS:
            DespesaFixa.objects.create(descricao=desc, categoria=cat, dia_vencimento=dia, ativa=False,
                                       observacao='Preencha o valor e ative.')

    hoje = date.today()
    fontes = [
        ('CompraFilamento', 'compra_filamento', 'FILAMENTO',
         lambda o: f'Filamento: {o.qnt}× {o.filamento.name} {o.filamento.color}', lambda o: o.parcelas),
        ('CompraInsumo', 'compra_insumo', 'INSUMOS', lambda o: f'Insumo: {o.insumo.name}', lambda o: o.parcelas),
        ('Compras', 'despesa', 'OUTROS', lambda o: o.saida, lambda o: o.parcela),
    ]
    for modelo, campo, cat, desc, parc in fontes:
        for obj in apps.get_model('financas', modelo).objects.all():
            if not obj.valor or Lancamento.objects.filter(**{campo: obj}).exists():
                continue
            conta = obj.pagamento
            n = _n(parc(obj))
            credito = bool(conta and conta.operacao == 'CREDITO')
            if not credito and n == 1:
                vencs = [obj.date]
            elif credito:
                vencs = [vencimento_fatura(conta, obj.date, i) for i in range(n)]
            else:
                vencs = [somar_meses(obj.date, i) for i in range(n)]
            for i, (v, valor) in enumerate(zip(vencs, dividir(obj.valor, n)), start=1):
                pago = v < hoje or (not credito and v <= hoje)
                Lancamento.objects.create(tipo='PAGAR', descricao=desc(obj)[:200], categoria=cat, valor=valor,
                                          vencimento=v, conta=conta, parcela=i, parcelas=n,
                                          pago_em=v if pago else None, baixa_automatica=pago, **{campo: obj})


class Migration(migrations.Migration):
    dependencies = [
        ('financas', '0003_saldocaixa_despesafixa_lancamento'),
        ('cadastro', '0007_contas_dia_fechamento_contas_dia_vencimento'),
    ]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
