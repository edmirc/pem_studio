from collections import OrderedDict, defaultdict
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cadastro.models import Contas
from encomendas.models import ETAPAS, Configuracao, Pedido
from vendas.models import Feiras, VendasInternas

from .models import Categoria, DespesaFixa, Lancamento, SaldoCaixa, TipoLancamento
from .servicos import gerar_parcelas_manuais, gerar_recorrentes, somar_meses

D0 = Decimal('0')
DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


# ---------------------------------------------------------------------------
# Formulário de lançamento avulso
# ---------------------------------------------------------------------------
class LancamentoForm(forms.ModelForm):
    parcelas_qtd = forms.IntegerField(label='Parcelas', min_value=1, max_value=48, initial=1, required=False,
                                      widget=forms.NumberInput(attrs={'inputmode': 'numeric'}))
    ja_pago = forms.BooleanField(label='Já foi pago / recebido', required=False)

    class Meta:
        model = Lancamento
        fields = ['tipo', 'descricao', 'categoria', 'valor', 'vencimento', 'conta', 'cliente', 'observacao']
        widgets = {'vencimento': DATA, 'tipo': forms.HiddenInput(),
                   'valor': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            if not isinstance(f.widget, (forms.CheckboxInput, forms.HiddenInput)):
                f.widget.attrs.setdefault('class', 'campo')
        if self.instance.pk:
            self.fields.pop('parcelas_qtd')
            self.fields['ja_pago'].initial = bool(self.instance.pago_em)
        tipo = self.data.get('tipo') or self.initial.get('tipo') or (self.instance.tipo if self.instance.pk else 'PAGAR')
        if tipo == TipoLancamento.PAGAR:
            self.fields.pop('cliente')
            self.fields['conta'].label = 'Pago com (conta ou cartão)'
            self.fields['conta'].help_text = 'No cartão de crédito, as parcelas entram nas faturas.'
        else:
            self.fields['conta'].label = 'Recebido em (conta)'
            self.fields['categoria'].initial = Categoria.VENDA


def _contexto_base(request, **kw):
    gerar_recorrentes()
    kw.setdefault('menu', 'financeiro')
    return kw


# ---------------------------------------------------------------------------
# Painel de contas a pagar e a receber
# ---------------------------------------------------------------------------
PERIODOS = OrderedDict([
    ('abertas', 'Tudo em aberto'),
    ('atrasadas', 'Atrasadas'),
    ('7dias', 'Próximos 7 dias'),
    ('mes', 'Este mês'),
    ('proximo', 'Próximo mês'),
    ('pagas', 'Pagas no mês'),
])


def _pedidos_a_receber():
    """Restante a receber das encomendas em produção (vence no prazo de entrega)."""
    linhas = []
    for p in Pedido.objects.filter(status__in=ETAPAS).select_related('cliente').prefetch_related('itens'):
        if p.falta_receber > 0:
            linhas.append({'pedido': p, 'descricao': f'Encomenda {p.numero} · restante', 'cliente': p.cliente,
                           'valor': p.falta_receber, 'vencimento': p.prazo,
                           'situacao': 'atrasado' if p.prazo < timezone.localdate() else 'aberto'})
    return linhas


@login_required
def contas(request):
    ctx = _contexto_base(request)
    hoje = timezone.localdate()
    tipo = request.GET.get('tipo', 'PAGAR')
    if tipo not in ('PAGAR', 'RECEBER'):
        tipo = 'PAGAR'
    periodo = request.GET.get('periodo', 'abertas')
    ini_mes = hoje.replace(day=1)
    prox_mes = somar_meses(ini_mes, 1)

    qs = Lancamento.objects.filter(tipo=tipo).select_related('conta', 'cliente', 'recorrente')
    abertos = qs.filter(pago_em__isnull=True)
    filtros = {
        'abertas': abertos,
        'atrasadas': abertos.filter(vencimento__lt=hoje),
        '7dias': abertos.filter(vencimento__lte=hoje + timedelta(days=7)),
        'mes': qs.filter(vencimento__gte=ini_mes, vencimento__lt=prox_mes),
        'proximo': qs.filter(vencimento__gte=prox_mes, vencimento__lt=somar_meses(prox_mes, 1)),
        'pagas': qs.filter(pago_em__gte=ini_mes, pago_em__lt=prox_mes),
    }
    lista = list(filtros.get(periodo, abertos).order_by('vencimento', 'id'))

    # faturas de cartão viram uma linha só (com os itens dentro)
    linhas, faturas = [], OrderedDict()
    for l in lista:
        if l.em_fatura:
            chave = (l.conta_id, l.vencimento)
            if chave not in faturas:
                faturas[chave] = {'fatura': True, 'conta': l.conta, 'vencimento': l.vencimento, 'itens': [],
                                  'valor': D0, 'aberto': D0}
                linhas.append(faturas[chave])
            f = faturas[chave]
            f['itens'].append(l)
            f['valor'] += l.valor
            if not l.pago_em:
                f['aberto'] += l.valor
        else:
            linhas.append({'fatura': False, 'l': l, 'vencimento': l.vencimento, 'valor': l.valor})
    for f in faturas.values():
        f['pago'] = f['aberto'] == 0
        f['situacao'] = 'pago' if f['pago'] else ('atrasado' if f['vencimento'] < hoje else
                                                  'hoje' if f['vencimento'] == hoje else 'aberto')

    pedidos = []
    if tipo == 'RECEBER' and periodo in ('abertas', 'atrasadas', '7dias', 'mes', 'proximo'):
        limites = {'atrasadas': (None, hoje - timedelta(days=1)), '7dias': (None, hoje + timedelta(days=7)),
                   'mes': (ini_mes, prox_mes - timedelta(days=1)),
                   'proximo': (prox_mes, somar_meses(prox_mes, 1) - timedelta(days=1))}
        de, ate = limites.get(periodo, (None, None))
        pedidos = [p for p in _pedidos_a_receber()
                   if (de is None or p['vencimento'] >= de) and (ate is None or p['vencimento'] <= ate)]

    def soma(q):
        return q.aggregate(t=Sum('valor'))['t'] or D0
    pagar_abertos = Lancamento.objects.filter(tipo='PAGAR', pago_em__isnull=True)
    receber_abertos = Lancamento.objects.filter(tipo='RECEBER', pago_em__isnull=True)
    ped_30 = sum((p['valor'] for p in _pedidos_a_receber() if p['vencimento'] <= hoje + timedelta(days=30)), D0)
    ctx.update({
        'tipo': tipo, 'periodo': periodo, 'periodos': PERIODOS, 'linhas': linhas, 'pedidos': pedidos,
        'total': sum((x['valor'] for x in linhas), D0) + sum((p['valor'] for p in pedidos), D0),
        'k_atrasado': soma(pagar_abertos.filter(vencimento__lt=hoje)),
        'k_atrasado_n': pagar_abertos.filter(vencimento__lt=hoje).count(),
        'k_7dias': soma(pagar_abertos.filter(vencimento__gte=hoje, vencimento__lte=hoje + timedelta(days=7))),
        'k_mes': soma(pagar_abertos.filter(vencimento__gte=hoje, vencimento__lt=prox_mes)),
        'k_receber': soma(receber_abertos.filter(vencimento__lte=hoje + timedelta(days=30))) + ped_30,
        'contas_pgto': Contas.objects.all(), 'hoje': hoje,
        'fixas_sem_valor': DespesaFixa.objects.filter(ativa=False).count(),
        'cartoes_sem_dia': Contas.objects.filter(operacao='CREDITO').filter(Q(dia_fechamento__isnull=True) | Q(dia_vencimento__isnull=True)).count(),
    })
    return render(request, 'financas/contas.html', ctx)


@login_required
def lancamento_editar(request, pk=None):
    obj = get_object_or_404(Lancamento, pk=pk) if pk else None
    if obj and obj.automatico:
        messages.info(request, 'Este lançamento vem de uma compra: para mudar valor ou parcelas, edite a compra.')
    inicial = {'tipo': request.GET.get('tipo', 'PAGAR'), 'vencimento': timezone.localdate()}
    form = LancamentoForm(request.POST or None, instance=obj, initial=None if obj else inicial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        pago_em = timezone.localdate() if d.get('ja_pago') else None
        if obj:
            l = form.save(commit=False)
            if d.get('ja_pago') and not obj.pago_em:
                l.pago_em = timezone.localdate()
            elif not d.get('ja_pago'):
                l.pago_em = None
            l.baixa_automatica = False
            l.save()
            messages.success(request, 'Lançamento salvo.')
        else:
            n = d.get('parcelas_qtd') or 1
            dados = dict(d, pago_em=pago_em)
            gerar_parcelas_manuais(dados, n)
            messages.success(request, 'Lançamento criado' + (f' em {n} parcelas.' if n > 1 else '.'))
        return redirect(f"/financeiro/?tipo={d['tipo']}")
    tipo = (obj.tipo if obj else inicial['tipo'])
    return render(request, 'financas/lancamento_form.html', _contexto_base(request, form=form, obj=obj, tipo=tipo))


@login_required
@require_POST
def lancamento_acao(request, acao):
    hoje = timezone.localdate()
    ids = request.POST.getlist('id')
    qs = Lancamento.objects.filter(pk__in=ids)
    voltar = request.POST.get('voltar') or '/financeiro/'
    if acao == 'pagar':
        try:
            data = timezone.datetime.strptime(request.POST.get('data') or '', '%Y-%m-%d').date()
        except ValueError:
            data = hoje
        conta_id = request.POST.get('conta') or None
        n = 0
        for l in qs.filter(pago_em__isnull=True):
            l.pago_em = data
            l.baixa_automatica = False
            if conta_id and not l.em_fatura:
                l.conta_id = conta_id
            l.save()
            n += 1
        messages.success(request, f'{n} lançamento{"s" if n != 1 else ""} marcado{"s" if n != 1 else ""} como pago{"s" if n != 1 else ""}.')
    elif acao == 'reabrir':
        qs.update(pago_em=None, baixa_automatica=False)
        messages.info(request, 'Lançamento reaberto.')
    elif acao == 'apagar':
        auto = [l for l in qs if l.automatico]
        if auto:
            messages.error(request, 'Lançamentos de compras são apagados apagando a compra.')
        else:
            qs.delete()
            messages.success(request, 'Lançamento apagado.')
    if not voltar.startswith('/'):
        voltar = '/financeiro/'
    return redirect(voltar)


# ---------------------------------------------------------------------------
# Faturas dos cartões
# ---------------------------------------------------------------------------
@login_required
def faturas(request):
    ctx = _contexto_base(request, menu='faturas')
    hoje = timezone.localdate()
    cartoes = []
    for c in Contas.objects.filter(operacao='CREDITO').order_by('apelido'):
        itens = Lancamento.objects.filter(conta=c, tipo='PAGAR').order_by('vencimento', 'id')
        grupos = OrderedDict()
        for l in itens.filter(Q(pago_em__isnull=True) | Q(vencimento__gte=hoje - timedelta(days=45))):
            g = grupos.setdefault(l.vencimento, {'vencimento': l.vencimento, 'itens': [], 'total': D0, 'aberto': D0})
            g['itens'].append(l)
            g['total'] += l.valor
            if not l.pago_em:
                g['aberto'] += l.valor
        for g in grupos.values():
            g['pago'] = g['aberto'] == 0
            g['atrasada'] = not g['pago'] and g['vencimento'] < hoje
        cartoes.append({'c': c, 'faturas': list(grupos.values()),
                        'em_aberto': sum((g['aberto'] for g in grupos.values()), D0)})
    ctx.update({'cartoes': cartoes, 'hoje': hoje})
    return render(request, 'financas/faturas.html', ctx)


# ---------------------------------------------------------------------------
# Fluxo de caixa
# ---------------------------------------------------------------------------
def _vendas_liquidas(de, ate):
    """Entradas de vendas entre duas datas, já sem a taxa estimada da maquininha."""
    cfg = Configuracao.atual()
    taxa = {'DEBITO': cfg.taxa_debito, 'CREDITO': cfg.taxa_credito_1x}
    total = D0
    for qs, campo_data, campo_valor in ((Feiras.objects.all(), 'nomeFeira__date', 'value'),
                                        (VendasInternas.objects.all(), 'date', 'valor')):
        for l in qs.filter(**{f'{campo_data}__gt': de, f'{campo_data}__lte': ate}).order_by() \
                   .values('pagment').annotate(t=Sum(campo_valor)):
            bruto = l['t'] or D0
            total += bruto * (1 - taxa.get(l['pagment'], D0) / 100)
    return total.quantize(Decimal('0.01'))


@login_required
def fluxo(request):
    ctx = _contexto_base(request, menu='fluxo')
    hoje = timezone.localdate()
    if request.method == 'POST':
        texto = request.POST.get('valor', '').strip().replace('R$', '').strip()
        if ',' in texto:  # formato brasileiro: 1.520,50
            texto = texto.replace('.', '').replace(',', '.')
        try:
            valor = Decimal(texto)
            SaldoCaixa.objects.create(valor=valor, data=hoje, observacao=request.POST.get('observacao', '')[:200])
            messages.success(request, 'Saldo atualizado.')
        except Exception:
            messages.error(request, 'Digite o saldo em reais, ex.: 1520,50')
        return redirect('financas:fluxo')

    dias = int(request.GET.get('dias', 90)) if request.GET.get('dias', '90').isdigit() else 90
    dias = min(max(dias, 30), 180)
    saldo = SaldoCaixa.objects.first()
    base = saldo.valor if saldo else D0
    base_data = saldo.data if saldo else hoje

    # o que já aconteceu desde o saldo informado
    pagos = Lancamento.objects.filter(pago_em__gt=base_data, pago_em__lte=hoje)
    saidas_real = pagos.filter(tipo='PAGAR').aggregate(t=Sum('valor'))['t'] or D0
    entradas_real = (pagos.filter(tipo='RECEBER').aggregate(t=Sum('valor'))['t'] or D0) + _vendas_liquidas(base_data, hoje)
    saldo_hoje = base + entradas_real - saidas_real

    # o que está previsto daqui para frente (atrasados contam como hoje)
    fim = hoje + timedelta(days=dias)
    mov = defaultdict(lambda: {'entra': D0, 'sai': D0, 'itens': []})
    for l in Lancamento.objects.filter(pago_em__isnull=True, vencimento__lte=fim).select_related('conta'):
        d = max(l.vencimento, hoje)
        chave = 'sai' if l.tipo == 'PAGAR' else 'entra'
        mov[d][chave] += l.valor
        mov[d]['itens'].append(l)
    for p in _pedidos_a_receber():
        if p['vencimento'] <= fim:
            d = max(p['vencimento'], hoje)
            mov[d]['entra'] += p['valor']

    # semanas
    semanas, acumulado, serie, minimo = [], saldo_hoje, [], (saldo_hoje, hoje)
    d = hoje
    while d <= fim:
        ate = min(d + timedelta(days=6), fim)
        entra = sai = D0
        x = d
        while x <= ate:
            entra += mov[x]['entra'] if x in mov else D0
            sai += mov[x]['sai'] if x in mov else D0
            if x in mov:
                acumulado += mov[x]['entra'] - mov[x]['sai']
                if acumulado < minimo[0]:
                    minimo = (acumulado, x)
            x += timedelta(days=1)
        semanas.append({'de': d, 'ate': ate, 'entra': entra, 'sai': sai, 'saldo': acumulado})
        serie.append(float(acumulado))
        d = ate + timedelta(days=1)

    proximos = sorted(((dt, l) for dt, v in mov.items() for l in v['itens'] if dt <= hoje + timedelta(days=14)),
                      key=lambda t: (t[0], t[1].tipo))
    ctx.update({
        'saldo': saldo, 'saldo_hoje': saldo_hoje, 'entradas_real': entradas_real, 'saidas_real': saidas_real,
        'semanas': semanas, 'dias': dias, 'opcoes_dias': [30, 60, 90, 180], 'minimo': minimo, 'hoje': hoje,
        'final': acumulado, 'proximos': [l for _, l in proximos][:25],
        'grafico': {'rotulos': ['hoje'] + [f'{s["ate"]:%d/%m}' for s in semanas],
                    'saldo': [float(saldo_hoje)] + serie},
    })
    return render(request, 'financas/fluxo.html', ctx)
