"""Kits: cadastro, montagem (peças + embalagem + tempo) e preço."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cadastro.models import Category, Product
from encomendas.models import Configuracao
from painel.produtos import FotoInvalida, apagar_foto, salvar_foto
from vendas.models import Precificacao

from . import servicos
from .models import Kit, KitPeca
from .servicos import CATEGORIA_GENERICA

ZERO = Decimal('0')
CENT = Decimal('0.01')


def _dec(v):
    """Aceita 12,50 · 1.234,50 · 12.50. Negativo ou inválido vira zero."""
    s = str(v if v not in (None, '') else '0').strip().replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        d = Decimal(s).quantize(CENT)
    except InvalidOperation:
        return ZERO
    return d if d >= 0 else ZERO


def _precos():
    """{produto_id: (custo, preço de venda)}"""
    return {p.product_id: (p.custo, p.vanda or p.sugerido) for p in Precificacao.objects.all()}


def pecas_disponiveis():
    """Produtos que podem entrar num kit (não são kits nem genéricos)."""
    return (Product.objects.filter(kit__isnull=True).exclude(category__category=CATEGORIA_GENERICA)
            .select_related('category').order_by('product'))


def valor_hora():
    return Configuracao.atual().valor_hora_trabalho or ZERO


def calcular(pecas, embalagem, outros, minutos, preco, precos=None, hora=None):
    """pecas: [(produto_id, qnt)]. Devolve o resumo de custo e preço do kit."""
    precos = _precos() if precos is None else precos
    hora = valor_hora() if hora is None else hora
    custo_pecas = avulso = ZERO
    sem_custo, sem_preco = [], []
    for pid, q in pecas:
        custo, venda = precos.get(pid, (None, None))
        if custo is None:
            sem_custo.append(pid)
        else:
            custo_pecas += custo * q
        if venda is None:
            sem_preco.append(pid)
        else:
            avulso += venda * q
    mao = (Decimal(minutos) / 60 * hora).quantize(CENT)
    custo = (custo_pecas + embalagem + outros + mao).quantize(CENT)
    r = {'custo_pecas': custo_pecas.quantize(CENT), 'mao': mao, 'embalagem': embalagem, 'outros': outros,
         'custo': custo, 'avulso': avulso.quantize(CENT), 'preco': preco,
         'sem_custo': sem_custo, 'sem_preco': sem_preco, 'lucro': None, 'margem': None, 'desconto': None}
    if preco:
        r['lucro'] = (preco - custo).quantize(CENT)
        r['margem'] = ((preco - custo) / custo * 100).quantize(Decimal('1')) if custo else None
        r['desconto'] = ((1 - preco / avulso) * 100).quantize(Decimal('1')) if avulso else None
    return r


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------
@login_required
def lista(request):
    kits = list(Kit.objects.select_related('produto__category').prefetch_related('pecas__peca'))
    precos, hora = _precos(), valor_hora()
    s, r = servicos.saldos(), servicos.reservados()
    possiveis = servicos.kits_possiveis(s, r)
    linhas = []
    for k in kits:
        pecas = list(k.pecas.all())
        venda = precos.get(k.produto_id, (None, None))[1]
        calc = calcular([(p.peca_id, p.qnt) for p in pecas], k.embalagem, k.outros, k.minutos_montagem, venda, precos, hora)
        limitante = None
        if pecas:
            limitante = min(pecas, key=lambda p: (s.get(p.peca_id, 0) - r.get(p.peca_id, 0)) // p.qnt)
        linhas.append({'k': k, 'pecas': pecas, 'calc': calc, 'possiveis': possiveis.get(k.produto_id, 0),
                       'limitante': limitante})
    return render(request, 'producao/kits.html', {'menu': 'kits', 'linhas': linhas})


# ---------------------------------------------------------------------------
# Cadastro / montagem
# ---------------------------------------------------------------------------
def _ler_pecas(request, kit_produto=None):
    """Lê as linhas peça/quantidade do formulário, somando peças repetidas."""
    ids, qnts = request.POST.getlist('peca'), request.POST.getlist('qnt')
    validos = set(pecas_disponiveis().values_list('pk', flat=True))
    soma, ordem = {}, []
    for pid, q in zip(ids, qnts):
        try:
            pid, q = int(pid), int(q)
        except (TypeError, ValueError):
            continue
        if q <= 0 or pid not in validos or (kit_produto and pid == kit_produto.pk):
            continue
        if pid not in soma:
            ordem.append(pid)
        soma[pid] = soma.get(pid, 0) + q
    return [(pid, soma[pid]) for pid in ordem]


@login_required
def editar(request, pk=None):
    kit = get_object_or_404(Kit.objects.select_related('produto'), pk=pk) if pk else None
    produto = kit.produto if kit else None
    erros = {}
    if request.method == 'POST':
        nome = (request.POST.get('nome') or '').strip()[:200]
        pecas = _ler_pecas(request, produto)
        cat = Category.objects.filter(pk=request.POST.get('categoria') or 0).first()
        embalagem, outros = _dec(request.POST.get('embalagem')), _dec(request.POST.get('outros'))
        try:
            minutos = max(0, int(request.POST.get('minutos') or 0))
        except ValueError:
            minutos = 0
        preco = _dec(request.POST.get('preco')) or None
        if not nome:
            erros['nome'] = 'Dê um nome para o kit.'
        elif Product.objects.filter(product__iexact=nome).exclude(pk=produto.pk if produto else None).exists():
            erros['nome'] = 'Já existe um produto com esse nome.'
        if not pecas:
            erros['pecas'] = 'Coloque pelo menos uma peça no kit.'
        if not erros:
            with transaction.atomic():
                if not cat:
                    cat, _ = Category.objects.get_or_create(category='Kits')
                if produto is None:
                    produto = Product.objects.create(product=nome, category=cat)
                    kit = Kit(produto=produto)
                else:
                    produto.product, produto.category = nome, cat
                    produto.save(update_fields=['product', 'category'])
                kit.embalagem, kit.outros, kit.minutos_montagem = embalagem, outros, minutos
                kit.observacao = (request.POST.get('observacao') or '').strip()[:300]
                kit.save()
                kit.pecas.all().delete()
                KitPeca.objects.bulk_create([KitPeca(kit=kit, peca_id=pid, qnt=q) for pid, q in pecas])
                calc = calcular(pecas, embalagem, outros, minutos, preco)
                pr = Precificacao.objects.filter(product=produto).first() or Precificacao(product=produto)
                pr.impressao, pr.filament, pr.embalagem = 0, ZERO, embalagem
                pr.acessorios = calc['custo_pecas'] + outros + calc['mao']
                pr.vanda = preco
                pr.save()
            if request.FILES.get('foto'):
                try:
                    salvar_foto(produto, request.FILES['foto'])
                except FotoInvalida as e:
                    messages.warning(request, str(e))
            elif request.POST.get('remover_foto'):
                apagar_foto(produto)
            messages.success(request, f'Kit "{produto}" salvo.')
            if calc['sem_custo']:
                messages.warning(request, f'{len(calc["sem_custo"])} peça(s) sem precificação: o custo do kit ficou incompleto.')
            return redirect('producao:kits')
        messages.error(request, ' '.join(erros.values()))

    precos = _precos()
    s, r = servicos.saldos(), servicos.reservados()
    info = {}
    for p in pecas_disponiveis():
        if produto and p.pk == produto.pk:
            continue
        custo, venda = precos.get(p.pk, (None, None))
        info[str(p.pk)] = {'nome': p.product, 'cat': p.category.category, 'mini': p.url_mini if (p.miniatura or p.imagem) else '',
                           'custo': str(custo) if custo is not None else None,
                           'venda': str(venda) if venda is not None else None,
                           'disp': s.get(p.pk, 0) - r.get(p.pk, 0)}
    if request.method == 'POST':
        linhas = [{'peca': pid, 'qnt': q} for pid, q in _ler_pecas(request, produto)]
        valores = {'nome': request.POST.get('nome', ''), 'categoria': request.POST.get('categoria', ''),
                   'embalagem': request.POST.get('embalagem', ''), 'outros': request.POST.get('outros', ''),
                   'minutos': request.POST.get('minutos', ''), 'preco': request.POST.get('preco', ''),
                   'observacao': request.POST.get('observacao', '')}
    elif kit:
        linhas = [{'peca': p.peca_id, 'qnt': p.qnt} for p in kit.pecas.all()]
        valores = {'nome': produto.product, 'categoria': str(produto.category_id), 'embalagem': kit.embalagem,
                   'outros': kit.outros, 'minutos': kit.minutos_montagem,
                   'preco': (precos.get(produto.pk, (None, None))[1] or ''), 'observacao': kit.observacao}
    else:
        linhas, valores = [], {'categoria': str(Category.objects.filter(category='Kits').values_list('pk', flat=True).first() or '')}
    cats = list(Category.objects.exclude(category=CATEGORIA_GENERICA).order_by('category'))
    return render(request, 'producao/kit_form.html', {
        'menu': 'kits', 'kit': kit, 'produto': produto, 'linhas': linhas, 'v': valores, 'erros': erros,
        'categorias': cats, 'tem_cat_kits': any(c.category == 'Kits' for c in cats),
        'info': info, 'hora': str(valor_hora()), 'hora_valor': valor_hora(),
    })


@login_required
@require_POST
def apagar(request, pk):
    kit = get_object_or_404(Kit.objects.select_related('produto'), pk=pk)
    produto = kit.produto
    nome = str(produto)
    from vendas.models import Feiras, VendasInternas
    vendido = Feiras.objects.filter(product=produto).exists() or VendasInternas.objects.filter(product=produto).exists()
    with transaction.atomic():
        kit.delete()
        if not vendido:
            apagar_foto(produto, salvar=False)
            try:
                produto.delete()
            except ProtectedError:
                vendido = True
    if vendido:
        messages.info(request, f'Kit "{nome}" desfeito. O produto continua cadastrado porque já tem vendas.')
    else:
        messages.info(request, f'Kit "{nome}" apagado.')
    return redirect('producao:kits')
