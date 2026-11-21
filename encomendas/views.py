import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cadastro.models import Product
from vendas.models import FormaPagamento, Precificacao

from . import servicos
from .calc import campos_precificacao, dados_calculadora
from .forms import (ConfiguracaoForm, ImpressoraForm, ItensOrcamento, ItensPedido, OrcamentoForm,
                    PedidoForm)
from .models import (ETAPAS, Configuracao, Impressora, ItemOrcamento, Orcamento, Pedido,
                     StatusOrcamento, StatusPedido)


def _precos_produtos():
    return {str(p.product_id): str(p.vanda or p.sugerido or '') for p in Precificacao.objects.all()}


def _ler_calculo(request):
    try:
        c = json.loads(request.POST.get('calculo') or '{}')
        assert isinstance(c, dict) and 'preco_peca' in c and 'partes' in c
        return c
    except (ValueError, AssertionError):
        return None


# ---------------------------------------------------------------------------
# Configurações e impressoras
# ---------------------------------------------------------------------------
@login_required
def configuracoes(request):
    cfg = Configuracao.atual()
    form = ConfiguracaoForm(request.POST or None, instance=cfg)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Configurações salvas.')
        return redirect('encomendas:configuracoes')
    impressoras = list(Impressora.objects.all())
    for i in impressoras:
        i.energia = i.energia_hora(cfg.preco_kwh)
    grupos = [
        ('Custos e preço', '', ['preco_kwh', 'valor_hora_trabalho', 'taxa_falha', 'lucro_padrao', 'custo_kg_padrao']),
        ('Orçamentos', '', ['nome_empresa', 'telefone_empresa', 'sinal_percentual', 'validade_dias', 'prazo_dias']),
        ('Taxas da maquininha', 'Coloque as taxas que a sua maquininha cobra. Os valores iniciais são só um exemplo.',
         ['taxa_debito'] + [f'taxa_credito_{i}x' for i in range(1, 7)]),
    ]
    return render(request, 'encomendas/configuracoes.html', {
        'menu': 'config', 'form': form, 'impressoras': impressoras, 'cfg': cfg,
        'grupos': [{'titulo': t, 'dica': d, 'campos': [form[n] for n in ns]} for t, d, ns in grupos],
        'exemplo': cfg.tabela_cartao(Decimal('100')),
    })


@login_required
def impressora_editar(request, pk=None):
    obj = get_object_or_404(Impressora, pk=pk) if pk else None
    form = ImpressoraForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Impressora salva.')
        return redirect('encomendas:configuracoes')
    return render(request, 'encomendas/impressora_form.html', {'menu': 'config', 'form': form, 'obj': obj})


# ---------------------------------------------------------------------------
# Calculadora
# ---------------------------------------------------------------------------
@login_required
def calculadora(request):
    return render(request, 'encomendas/calculadora.html', {
        'menu': 'calculadora', 'dados': dados_calculadora(),
        'produtos': Product.objects.order_by('product'),
    })


@login_required
@require_POST
def calc_precificacao(request):
    calc = _ler_calculo(request)
    produto = get_object_or_404(Product, pk=request.POST.get('produto'))
    if not calc:
        messages.error(request, 'Cálculo inválido.')
        return redirect('encomendas:calculadora')
    campos = campos_precificacao(calc)
    pr = Precificacao.objects.filter(product=produto).first() or Precificacao(product=produto)
    for k, v in campos.items():
        setattr(pr, k, v)
    pr.save()
    messages.success(request, f'Precificação de "{produto}" atualizada: custo {pr.custo} e preço de venda {pr.vanda}.')
    return redirect('painel:lista', slug='precificacao')


@login_required
@require_POST
def orcamento_da_calc(request):
    calc = _ler_calculo(request)
    if not calc:
        messages.error(request, 'Cálculo inválido.')
        return redirect('encomendas:calculadora')
    cfg = Configuracao.atual()
    hoje = timezone.localdate()
    orc = Orcamento.objects.create(nome_cliente='', validade=hoje + timedelta(days=cfg.validade_dias),
                                   prazo_dias=cfg.prazo_dias, sinal_percentual=cfg.sinal_percentual)
    ItemOrcamento.objects.create(orcamento=orc, descricao=calc.get('nome') or 'Peça personalizada',
                                 qnt=max(1, int(calc.get('pecas') or 1)),
                                 preco_unitario=Decimal(str(calc['preco_peca'])), calculo=calc)
    messages.info(request, 'Orçamento criado com a peça calculada. Complete os dados do cliente.')
    return redirect('encomendas:orcamento_editar', pk=orc.pk)


# ---------------------------------------------------------------------------
# Orçamentos
# ---------------------------------------------------------------------------
@login_required
def orcamentos(request):
    qs = Orcamento.objects.select_related('cliente').prefetch_related('itens__produto')
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(nome_cliente__icontains=q) | Q(cliente__name__icontains=q) | Q(telefone__icontains=q)
                       | Q(itens__descricao__icontains=q)).distinct()
    lista = list(qs[:200])
    return render(request, 'encomendas/orcamentos.html', {
        'menu': 'orcamentos', 'orcamentos': lista, 'status': status, 'q': q,
        'situacoes': StatusOrcamento.choices,
    })


def _form_itens(request, obj, Form, FormSet, template, ctx_extra):
    form = Form(request.POST or None, instance=obj)
    itens = FormSet(request.POST or None, instance=obj, prefix='itens')
    if request.method == 'POST':
        if form.is_valid() and itens.is_valid():
            vivos = [f for f in itens.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
            if not vivos:
                messages.error(request, 'Adicione pelo menos um item.')
            else:
                with transaction.atomic():
                    salvo = form.save()
                    itens.instance = salvo
                    for f in itens.forms:  # descrição automática a partir do produto
                        if f.cleaned_data and not f.cleaned_data.get('DELETE') and not f.cleaned_data.get('descricao') \
                                and f.cleaned_data.get('produto'):
                            f.instance.descricao = ''
                    itens.save()
                return salvo
        else:
            messages.error(request, 'Confira os campos destacados.')
    ctx = {'form': form, 'itens': itens, 'obj': obj, 'precos': _precos_produtos(), 'dados': dados_calculadora()}
    ctx.update(ctx_extra)
    return render(request, template, ctx)


@login_required
def orcamento_editar(request, pk=None):
    cfg = Configuracao.atual()
    if pk:
        obj = get_object_or_404(Orcamento, pk=pk)
    else:
        hoje = timezone.localdate()
        obj = Orcamento(validade=hoje + timedelta(days=cfg.validade_dias), prazo_dias=cfg.prazo_dias,
                        sinal_percentual=cfg.sinal_percentual)
    r = _form_itens(request, obj, OrcamentoForm, ItensOrcamento, 'encomendas/orcamento_form.html',
                    {'menu': 'orcamentos', 'tipo': 'orcamento'})
    if isinstance(r, Orcamento):
        if 'aprovar' in request.POST:
            try:
                pedido = servicos.aprovar_orcamento(r)
                messages.success(request, f'Orçamento aprovado. Pedido {pedido.numero} criado.')
                return redirect('encomendas:pedido', pk=pedido.pk)
            except servicos.ErroNegocio as e:
                messages.error(request, str(e))
        else:
            messages.success(request, f'Orçamento {r.numero} salvo.')
        return redirect('encomendas:orcamento', pk=r.pk)
    return r


@login_required
def orcamento(request, pk):
    orc = get_object_or_404(Orcamento.objects.select_related('cliente'), pk=pk)
    cfg = Configuracao.atual()
    texto = servicos.texto_orcamento(orc, cfg)
    return render(request, 'encomendas/orcamento.html', {
        'menu': 'orcamentos', 'o': orc, 'cfg': cfg, 'itens': orc.itens.select_related('produto'),
        'cartao': cfg.tabela_cartao(orc.total), 'texto': texto,
        'whatsapp': servicos.link_whatsapp(orc.telefone_exibicao, texto),
        'pedido': getattr(orc, 'pedido', None),
    })


@login_required
@require_POST
def orcamento_acao(request, pk, acao):
    orc = get_object_or_404(Orcamento, pk=pk)
    if acao == 'enviado' and orc.status == StatusOrcamento.RASCUNHO:
        orc.status = StatusOrcamento.ENVIADO
        orc.save(update_fields=['status'])
        if request.headers.get('HX-Request'):
            from django.http import HttpResponse
            return HttpResponse(status=204)
    elif acao == 'recusado':
        orc.status = StatusOrcamento.RECUSADO
        orc.save(update_fields=['status'])
        messages.info(request, 'Orçamento marcado como recusado.')
    elif acao == 'reabrir':
        orc.status = StatusOrcamento.ENVIADO
        orc.save(update_fields=['status'])
    elif acao == 'aprovar':
        try:
            pedido = servicos.aprovar_orcamento(orc)
            messages.success(request, f'Orçamento aprovado. Pedido {pedido.numero} criado.')
            return redirect('encomendas:pedido', pk=pedido.pk)
        except servicos.ErroNegocio as e:
            messages.error(request, str(e))
    elif acao == 'duplicar':
        itens = list(orc.itens.all())
        orc.pk = None
        orc.status = StatusOrcamento.RASCUNHO
        orc.data = timezone.localdate()
        orc.validade = orc.data + timedelta(days=Configuracao.atual().validade_dias)
        orc.save()
        for i in itens:
            i.pk = None
            i.orcamento = orc
            i.save()
        messages.success(request, f'Cópia criada: {orc.numero}.')
        return redirect('encomendas:orcamento_editar', pk=orc.pk)
    elif acao == 'apagar':
        if hasattr(orc, 'pedido') and orc.pedido:
            messages.error(request, 'Este orçamento já virou pedido; não pode ser apagado.')
        else:
            orc.delete()
            messages.success(request, 'Orçamento apagado.')
            return redirect('encomendas:orcamentos')
    return redirect('encomendas:orcamento', pk=pk)


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
@login_required
def pedidos(request):
    ativos = list(Pedido.objects.filter(status__in=ETAPAS).select_related('cliente', 'orcamento__solicitacao')
                  .prefetch_related('itens__produto', 'orcamento__solicitacao__anexos'))
    colunas = [{'status': s, 'nome': s.label, 'pedidos': [p for p in ativos if p.status == s]} for s in ETAPAS]
    hoje = timezone.localdate()
    entregues = Pedido.objects.filter(status=StatusPedido.ENTREGUE, entregue_em__gte=hoje - timedelta(days=30)) \
        .select_related('cliente').order_by('-entregue_em')[:15]
    return render(request, 'encomendas/pedidos.html', {
        'menu': 'pedidos', 'colunas': colunas, 'entregues': entregues,
        'atrasados': sum(1 for p in ativos if p.atrasado),
    })


@login_required
def pedido(request, pk):
    p = get_object_or_404(Pedido.objects.select_related('cliente', 'orcamento'), pk=pk)
    from producao.servicos import andamento_item
    itens = list(p.itens.select_related('produto').prefetch_related('impressoes'))
    for i in itens:
        i.producao = andamento_item(i)
    return render(request, 'encomendas/pedido.html', {
        'menu': 'pedidos', 'p': p, 'itens': itens, 'em_producao': p.status in ETAPAS,
        'etapas': [{'s': s, 'nome': s.label, 'feito': ETAPAS.index(s) <= ETAPAS.index(p.status)
                    if p.status in ETAPAS else p.status == StatusPedido.ENTREGUE} for s in ETAPAS],
        'formas': FormaPagamento.choices, 'hoje': timezone.localdate(),
        'cartao': Configuracao.atual().tabela_cartao(p.falta_receber),
    })


@login_required
def pedido_editar(request, pk):
    obj = get_object_or_404(Pedido, pk=pk)
    if obj.vendas_geradas:
        messages.error(request, 'Pedido entregue não pode ser alterado (as vendas já foram lançadas).')
        return redirect('encomendas:pedido', pk=pk)
    r = _form_itens(request, obj, PedidoForm, ItensPedido, 'encomendas/orcamento_form.html',
                    {'menu': 'pedidos', 'tipo': 'pedido'})
    if isinstance(r, Pedido):
        messages.success(request, 'Pedido salvo.')
        return redirect('encomendas:pedido', pk=r.pk)
    return r


@login_required
@require_POST
def pedido_acao(request, pk, acao):
    p = get_object_or_404(Pedido, pk=pk)
    voltar = request.POST.get('voltar') or ''
    if acao == 'etapa':
        nova = request.POST.get('status')
        if nova in ETAPAS and not p.vendas_geradas:
            p.status = nova
            p.save(update_fields=['status'])
    elif acao == 'sinal':
        try:
            valor = Decimal(request.POST.get('valor', '0').replace(',', '.'))
        except Exception:
            valor = Decimal('-1')
        forma = request.POST.get('forma')
        if valor < 0 or forma not in dict(FormaPagamento.choices) or p.vendas_geradas:
            messages.error(request, 'Informe o valor e a forma de pagamento do sinal.')
        else:
            p.sinal_recebido = valor
            p.sinal_forma = forma
            p.sinal_data = timezone.localdate()
            p.save(update_fields=['sinal_recebido', 'sinal_forma', 'sinal_data'])
            from financas.servicos import gerar_do_sinal
            gerar_do_sinal(p)
            messages.success(request, 'Sinal registrado (já entrou no caixa).')
    elif acao == 'entregar':
        forma = request.POST.get('forma')
        if forma not in dict(FormaPagamento.choices):
            messages.error(request, 'Escolha a forma de pagamento do restante.')
        else:
            try:
                servicos.entregar_pedido(p, forma)
                messages.success(request, f'Pedido {p.numero} entregue. A venda entrou em Vendas diretas e nos relatórios.')
            except servicos.ErroNegocio as e:
                messages.error(request, str(e))
    elif acao == 'cancelar':
        if not p.vendas_geradas:
            p.status = StatusPedido.CANCELADO
            p.save(update_fields=['status'])
            messages.info(request, 'Pedido cancelado.')
    elif acao == 'reativar':
        if p.status == StatusPedido.CANCELADO:
            p.status = StatusPedido.AGUARDANDO
            p.save(update_fields=['status'])
    if voltar == 'quadro':
        return redirect('encomendas:pedidos')
    return redirect('encomendas:pedido', pk=pk)


@login_required
def pedidos_historico(request):
    qs = Pedido.objects.select_related('cliente').prefetch_related('itens').order_by('-data', '-id')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'encomendas/pedidos_historico.html', {
        'menu': 'pedidos', 'pedidos': qs[:300], 'status': status, 'situacoes': StatusPedido.choices,
    })
