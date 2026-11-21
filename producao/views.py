import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cadastro.models import Category, Product
from encomendas.calc import campos_precificacao, dados_calculadora
from encomendas.models import ETAPAS, Impressora, ItemPedido
from painel.produtos import fatiador_da_impressora, links_arquivo
from painel.utils import destino_seguro
from vendas.models import Precificacao

from . import servicos
from .models import (ConfigEstoque, EstoqueMinimo, Impressao, Kit, MovimentoEstoque, StatusImpressao as S,
                     TipoMovimento)
from .servicos import CATEGORIA_GENERICA, ErroProducao


def _int(v, padrao=None):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return padrao


def _num(v):
    try:
        return Decimal(str(v if v not in (None, '') else 0).replace(',', '.'))
    except InvalidOperation:
        return Decimal('0')


def _produtos_estoque():
    """Produtos com estoque próprio (kits e genéricos de encomenda ficam de fora)."""
    return (Product.objects.exclude(category__category=CATEGORIA_GENERICA).filter(kit__isnull=True)
            .select_related('category'))


def _usuario(request):
    return request.user.get_full_name() or request.user.username


# ---------------------------------------------------------------------------
# Painel das impressoras
# ---------------------------------------------------------------------------
@login_required
def painel(request):
    ativas = (Impressao.objects.filter(status__in=[S.FILA, S.IMPRIMINDO, S.IMPRESSO])
              .select_related('produto__category', 'impressora', 'item_pedido__pedido__cliente'))
    ativas = list(ativas)
    impressoras = list(Impressora.objects.filter(ativa=True))
    for i in impressoras:
        i.atual = next((x for x in ativas if x.status == S.IMPRIMINDO and x.impressora_id == i.pk), None)
        i.proximas = [x for x in ativas if x.status == S.FILA and x.impressora_id == i.pk]
    # impressão em máquina desativada continua aparecendo
    soltas = [x for x in ativas if x.status == S.IMPRIMINDO and x.impressora_id not in {i.pk for i in impressoras}]

    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    do_mes = Impressao.objects.filter(concluido_em__date__gte=inicio_mes)
    prontas = do_mes.filter(status=S.PRONTA)
    falhas = do_mes.filter(status=S.FALHOU)
    perdidas = sum(i.perdidas for i in do_mes.filter(status__in=[S.PRONTA, S.FALHOU]))
    horas = do_mes.filter(status__in=[S.PRONTA, S.FALHOU]).aggregate(t=Sum('horas'))['t'] or 0

    recentes = (Impressao.objects.filter(status__in=[S.PRONTA, S.FALHOU, S.CANCELADA])
                .select_related('produto__category', 'impressora', 'item_pedido__pedido').order_by('-concluido_em', '-id')[:15])
    return render(request, 'producao/painel.html', {
        'menu': 'producao',
        'impressoras': impressoras, 'soltas': soltas,
        'fila': [x for x in ativas if x.status == S.FILA],
        'acabamento': [x for x in ativas if x.status == S.IMPRESSO],
        'recentes': recentes,
        'k': {'prontas': prontas.aggregate(t=Sum('qnt_boas'))['t'] or 0, 'falhas': falhas.count(),
              'perdidas': perdidas, 'horas': horas,
              'imprimindo': sum(1 for x in ativas if x.status == S.IMPRIMINDO)},
        'precisa': servicos.precisa_imprimir(limite=8),
        'livres': [i for i in impressoras if not i.atual],
        'hoje_ymd': timezone.localtime().strftime('%Y%m%d'),
    })


@login_required
@require_POST
def acao(request, pk, acao):
    imp = get_object_or_404(Impressao, pk=pk)
    try:
        if acao == 'iniciar':
            impressora = Impressora.objects.filter(pk=_int(request.POST.get('impressora'))).first()
            servicos.iniciar(imp, impressora)
            messages.success(request, f'{imp.nome} imprimindo na {imp.impressora}.')
        elif acao == 'impresso':
            servicos.marcar_impresso(imp)
            messages.success(request, f'{imp.nome}: impresso. Falta o acabamento.')
        elif acao == 'pronta':
            boas = _int(request.POST.get('boas'), imp.qnt)
            servicos.concluir(imp, boas, usuario=_usuario(request))
            if imp.vai_para_estoque and boas:
                messages.success(request, f'{boas} × {imp.nome} entrou no estoque.')
            else:
                messages.success(request, f'{imp.nome}: peça pronta.')
        elif acao == 'falhou':
            servicos.falhou(imp, (request.POST.get('motivo') or '').strip())
            if request.POST.get('reimprimir'):
                nova = servicos.repetir(imp)
                messages.warning(request, f'Falha registrada. {nova.nome} voltou para a fila.')
            else:
                messages.warning(request, 'Falha registrada.')
        elif acao == 'repetir':
            nova = servicos.repetir(imp)
            messages.success(request, f'{nova.nome} adicionada à fila.')
        elif acao == 'cancelar':
            servicos.cancelar(imp)
            messages.info(request, 'Impressão cancelada.')
        elif acao == 'voltar':
            servicos.voltar(imp)
            messages.info(request, f'{imp.nome} voltou para "{imp.get_status_display()}".')
        elif acao == 'editar':
            impressora = Impressora.objects.filter(pk=_int(request.POST.get('impressora'))).first()
            if imp.status == S.FILA:
                imp.impressora = impressora
                imp.qnt = max(1, _int(request.POST.get('qnt'), imp.qnt))
            imp.observacao = (request.POST.get('observacao') or '').strip()[:300]
            imp.save()
            messages.success(request, 'Impressão alterada.')
    except ErroProducao as e:
        messages.error(request, str(e))
    return redirect(destino_seguro(request.POST.get('voltar')) or 'producao:painel')


# ---------------------------------------------------------------------------
# Nova impressão (produto + precificação + mandar para a fila, numa página só)
# ---------------------------------------------------------------------------
def _itens_abertos():
    itens = (ItemPedido.objects.filter(pedido__status__in=ETAPAS).exclude(produto__kit__isnull=False)
             .select_related('pedido__cliente', 'produto').prefetch_related('impressoes').order_by('pedido__prazo', 'id'))
    lista = []
    for it in itens:
        a = servicos.andamento_item(it)
        lista.append({'item': it, 'falta': a['falta']})
    return lista


def _ultimo_calculo(produto_ids):
    """{produto_id: cálculo da impressão mais recente}"""
    r = {}
    for i in Impressao.objects.filter(produto_id__in=produto_ids, calculo__isnull=False).order_by('id'):
        r[i.produto_id] = i.calculo
    return r


@login_required
def nova(request):
    produtos = list(_produtos_estoque().order_by('product'))
    precos = {p.product_id: p for p in Precificacao.objects.all()}
    saldos = servicos.saldos()
    ultimo = _ultimo_calculo([p.pk for p in produtos])
    itens = _itens_abertos()
    cfg_imp = {i.pk: servicos.ocupada(i) for i in Impressora.objects.filter(ativa=True)}

    if request.method == 'POST':
        r = _salvar_nova(request)
        if r:
            return r

    # pré-preenchimento: ?produto=, ?item= (pedido) ou ?de= (repetir uma impressão)
    inicial = {'produto': '', 'item': '', 'calculo': None, 'mesas': 1}
    if request.method == 'POST':
        inicial.update(produto=request.POST.get('produto', ''), item=request.POST.get('item', ''),
                       mesas=request.POST.get('mesas', 1))
        try:
            inicial['calculo'] = json.loads(request.POST.get('calculo') or 'null')
        except ValueError:
            pass
    elif request.GET.get('de'):
        base = Impressao.objects.filter(pk=_int(request.GET['de'])).first()
        if base:
            inicial.update(produto=base.produto_id or '', item=base.item_pedido_id or '', calculo=base.calculo)
    elif request.GET.get('item'):
        it = ItemPedido.objects.filter(pk=_int(request.GET['item'])).select_related('produto').first()
        if it:
            calc = dict(it.calculo or {})
            falta = next((x['falta'] for x in itens if x['item'].pk == it.pk), it.qnt)
            if calc:
                calc['nome'] = it.nome
            else:
                calc = {'nome': it.nome, 'pecas': falta or it.qnt}
            inicial.update(item=it.pk, produto=it.produto_id or '', calculo=calc)
    elif request.GET.get('produto'):
        pid = _int(request.GET['produto'])
        inicial.update(produto=pid or '', calculo=ultimo.get(pid))
        if request.GET.get('qnt') and inicial['calculo'] is None:
            inicial['calculo'] = {'pecas': _int(request.GET['qnt'], 1)}

    info = {str(p.pk): {
        'nome': p.product, 'estoque': saldos.get(p.pk, 0),
        'custo': str(precos[p.pk].custo) if p.pk in precos and precos[p.pk].custo is not None else None,
        'venda': str(precos[p.pk].vanda or precos[p.pk].sugerido or '') if p.pk in precos else None,
        'calculo': ultimo.get(p.pk),
        'mini': p.url_mini if p.miniatura else '',
        'arquivo': links_arquivo(p.arquivo),
    } for p in produtos}
    info_itens = {str(x['item'].pk): {'produto': x['item'].produto_id, 'nome': x['item'].nome, 'falta': x['falta'],
                                      'calculo': x['item'].calculo} for x in itens}
    return render(request, 'producao/nova.html', {
        'menu': 'producao', 'produtos': produtos, 'categorias': Category.objects.exclude(category=CATEGORIA_GENERICA),
        'itens': itens, 'inicial': inicial, 'ocupadas': {str(k): v.nome for k, v in cfg_imp.items() if v},
        'dados': dados_calculadora(), 'info': info, 'info_itens': info_itens,
        'post': request.POST if request.method == 'POST' else {},
        'fatiador_por_impressora': {str(i.pk): fatiador_da_impressora(i) for i in Impressora.objects.all()},
    })


def _salvar_nova(request):
    """Cria a(s) impressão(ões). Devolve o redirect, ou None se houver erro (a página é mostrada de novo)."""
    try:
        calc = json.loads(request.POST.get('calculo') or '{}')
        assert isinstance(calc, dict)
    except (ValueError, AssertionError):
        calc = {}
    item = ItemPedido.objects.filter(pk=_int(request.POST.get('item'))).select_related('produto', 'pedido').first()
    produto = Product.objects.filter(pk=_int(request.POST.get('produto'))).first()
    novo_nome = (request.POST.get('novo_produto') or '').strip()
    if request.POST.get('modo_produto') == 'novo' and novo_nome:
        existente = Product.objects.filter(product__iexact=novo_nome).first()
        if existente:
            produto = existente
            messages.info(request, f'O produto "{existente}" já existia e foi usado.')
        else:
            cat = Category.objects.filter(pk=_int(request.POST.get('nova_categoria'))).first()
            if not cat:
                messages.error(request, 'Escolha a categoria do produto novo.')
                return None
            produto = None  # criado abaixo, dentro da transação
    elif request.POST.get('modo_produto') == 'novo':
        messages.error(request, 'Digite o nome do produto novo.')
        return None
    if not produto and not novo_nome and not item:
        messages.error(request, 'Escolha o produto (ou o item de um pedido) que vai imprimir.')
        return None
    kit_escolhido = produto or (item.produto if item and item.produto_id else None)
    if kit_escolhido and Kit.objects.filter(produto=kit_escolhido).exists():
        messages.error(request, f'"{kit_escolhido}" é um kit: imprima as peças dele separadamente.')
        return None

    pecas = max(1, _int(calc.get('pecas'), 1) or 1)
    horas = (_num(calc.get('horas')) + _num(calc.get('minutos')) / 60).quantize(Decimal('0.01'))
    gramas = _num(calc.get('gramas')) or None
    impressora = Impressora.objects.filter(pk=_int(calc.get('impressora_id'))).first()
    mesas = min(20, max(1, _int(request.POST.get('mesas'), 1) or 1))
    obs = (request.POST.get('observacao') or '').strip()[:300]

    with transaction.atomic():
        if not produto and novo_nome and request.POST.get('modo_produto') == 'novo':
            produto = Product.objects.create(product=novo_nome[:200], category=cat)
            messages.success(request, f'Produto "{produto}" cadastrado.')
        if not produto and item and item.produto_id:
            produto = item.produto
        criadas = [Impressao.objects.create(
            produto=produto, item_pedido=item, descricao='' if produto else (item.nome if item else ''),
            impressora=impressora, qnt=pecas, horas=horas, gramas=gramas, calculo=calc or None, observacao=obs)
            for _ in range(mesas)]

        if request.POST.get('salvar_preco') and produto and calc.get('custo_peca'):
            try:
                campos = campos_precificacao(calc)
                pr = Precificacao.objects.filter(product=produto).first() or Precificacao(product=produto)
                for k, v in campos.items():
                    setattr(pr, k, v)
                pr.save()
                messages.success(request, f'Preço de "{produto}" salvo: custo {pr.custo} · venda {pr.vanda}.')
            except (KeyError, TypeError, InvalidOperation):
                messages.warning(request, 'Não deu para salvar o preço (cálculo incompleto).')

    nome = criadas[0].nome
    if request.POST.get('comecar') and impressora:
        try:
            servicos.iniciar(criadas[0])
            messages.success(request, f'{nome} imprimindo na {impressora}.')
        except ErroProducao as e:
            messages.warning(request, f'{e} A impressão ficou na fila.')
    else:
        messages.success(request, f'{mesas} impress{"ões" if mesas > 1 else "ão"} de {nome} na fila.')
    return redirect('producao:painel')


# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
@login_required
def estoque(request):
    s, r, p, m = servicos.saldos(), servicos.reservados(), servicos.em_producao(), servicos.minimos()
    precos = {x.product_id: x for x in Precificacao.objects.all()}
    q = request.GET.get('q', '').strip()
    cat = _int(request.GET.get('categoria'))
    filtro = request.GET.get('filtro', '')
    qs = _produtos_estoque().order_by('product')
    if q:
        qs = qs.filter(product__icontains=q)
    if cat:
        qs = qs.filter(category_id=cat)
    linhas, total_pecas, valor_venda, valor_custo, abaixo, negativos = [], 0, Decimal('0'), Decimal('0'), 0, 0
    for prod in qs:
        saldo, res, prod_n, minimo = s.get(prod.pk, 0), r.get(prod.pk, 0), p.get(prod.pk, 0), m.get(prod.pk, 0)
        disp = saldo - res
        pr = precos.get(prod.pk)
        venda = (pr.vanda or pr.sugerido) if pr else None
        situacao = 'negativo' if saldo < 0 else 'abaixo' if minimo and disp < minimo else 'zerado' if saldo == 0 else 'ok'
        l = {'p': prod, 'saldo': saldo, 'reservado': res, 'disponivel': disp, 'producao': prod_n, 'minimo': minimo,
             'venda': venda, 'situacao': situacao, 'sugestao': max(0, minimo - disp - prod_n) if minimo else 0}
        if saldo > 0:
            total_pecas += saldo
            valor_venda += (venda or 0) * saldo
            valor_custo += ((pr.custo if pr else None) or 0) * saldo
        abaixo += situacao == 'abaixo'
        negativos += situacao == 'negativo'
        if filtro == 'com' and saldo <= 0:
            continue
        if filtro == 'abaixo' and situacao not in ('abaixo', 'negativo'):
            continue
        if filtro == 'zerado' and saldo != 0:
            continue
        linhas.append(l)
    if filtro == 'abaixo':
        linhas.sort(key=lambda x: (x['disponivel'] - x['minimo']))
    return render(request, 'producao/estoque.html', {
        'menu': 'estoque', 'linhas': linhas, 'q': q, 'cat': cat, 'filtro': filtro,
        'categorias': Category.objects.exclude(category=CATEGORIA_GENERICA),
        'k': {'pecas': total_pecas, 'venda': valor_venda, 'custo': valor_custo, 'abaixo': abaixo, 'negativos': negativos,
              'producao': sum(p.values())},
        'inicio': ConfigEstoque.atual().inicio,
    })


@login_required
def produto(request, pk):
    prod = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    kit = Kit.objects.filter(produto=prod).first()
    if kit:
        return redirect('producao:kit', pk=kit.pk)
    if request.method == 'POST':
        op = request.POST.get('op')
        try:
            if op == 'ajuste':
                servicos.ajustar(prod, request.POST.get('tipo'), _int(request.POST.get('qnt'), 0),
                                 (request.POST.get('observacao') or '').strip(), _usuario(request))
                messages.success(request, 'Estoque ajustado.')
            elif op == 'contagem':
                contado = _int(request.POST.get('contado'))
                if contado is None or contado < 0:
                    raise ErroProducao('Informe quantas peças você contou.')
                dif = servicos.definir_contagem(prod, contado, _usuario(request))
                messages.success(request, f'Estoque acertado para {contado}' + (f' ({dif:+d}).' if dif else ' (já estava certo).'))
            elif op == 'minimo':
                minimo = max(0, _int(request.POST.get('minimo'), 0) or 0)
                EstoqueMinimo.objects.update_or_create(produto=prod, defaults={'minimo': minimo})
                messages.success(request, f'Estoque mínimo: {minimo}.')
            elif op == 'apagar':
                mv = get_object_or_404(MovimentoEstoque, pk=_int(request.POST.get('mov')), produto=prod)
                if mv.automatico:
                    raise ErroProducao('Este lançamento é automático: corrija a venda ou a impressão de origem.')
                mv.delete()
                messages.info(request, 'Lançamento apagado.')
        except ErroProducao as e:
            messages.error(request, str(e))
        return redirect('producao:produto', pk=pk)

    movs = list(MovimentoEstoque.objects.filter(produto=prod).select_related('impressao', 'venda_feira__nomeFeira')
                .order_by('data', 'id'))
    acumulado = 0
    for mv in movs:
        acumulado += mv.qnt
        mv.saldo_apos = acumulado
    movs.reverse()
    pagina = Paginator(movs, 50).get_page(request.GET.get('pagina'))
    saldo = acumulado
    reservado = servicos.reservados().get(prod.pk, 0)
    minimo = servicos.minimos().get(prod.pk, 0)
    pr = Precificacao.objects.filter(product=prod).first()
    hoje = timezone.localdate()
    vendidos_90 = -(MovimentoEstoque.objects.filter(produto=prod, tipo__in=[TipoMovimento.VENDA_FEIRA, TipoMovimento.VENDA_DIRETA],
                                                    data__gte=hoje - timedelta(days=90)).aggregate(t=Sum('qnt'))['t'] or 0)
    return render(request, 'producao/produto.html', {
        'menu': 'estoque', 'prod': prod, 'pagina': pagina, 'saldo': saldo, 'reservado': reservado,
        'disponivel': saldo - reservado, 'minimo': minimo, 'pr': pr, 'vendidos_90': vendidos_90,
        'andamento': Impressao.objects.filter(produto=prod, status__in=[S.FILA, S.IMPRIMINDO, S.IMPRESSO])
                     .select_related('impressora'),
        'reservas': ItemPedido.objects.filter(produto=prod, pedido__status__in=ETAPAS).select_related('pedido__cliente'),
        'tipos_ajuste': [(TipoMovimento.ENTRADA, 'Entrada (+)'), (TipoMovimento.SAIDA, 'Saída (−)'),
                         (TipoMovimento.PERDA, 'Perda / quebra (−)')],
    })


@login_required
def contagem(request):
    cfg = ConfigEstoque.atual()
    cat = _int(request.GET.get('categoria') or request.POST.get('categoria'))
    if request.method == 'POST':
        if request.POST.get('op') == 'inicio':
            from datetime import date
            try:
                novo = date.fromisoformat(request.POST.get('inicio', ''))
            except ValueError:
                messages.error(request, 'Data inválida.')
                return redirect('producao:contagem')
            cfg.inicio = novo
            cfg.save()
            servicos.ressincronizar_vendas(novo)
            messages.success(request, f'O estoque agora conta as vendas a partir de {novo:%d/%m/%Y}.')
            return redirect('producao:contagem')
        n, usuario = 0, _usuario(request)
        with transaction.atomic():
            for chave, valor in request.POST.items():
                if not chave.startswith('c_') or str(valor).strip() == '':
                    continue
                contado = _int(valor)
                prod = Product.objects.filter(pk=_int(chave[2:])).first()
                if prod is None or contado is None or contado < 0:
                    continue
                if servicos.definir_contagem(prod, contado, usuario):
                    n += 1
        messages.success(request, f'Contagem salva: {n} produto{"s" if n != 1 else ""} acertado{"s" if n != 1 else ""}.'
                         if n else 'Contagem salva: tudo já batia com o sistema.')
        return redirect('producao:estoque')
    s = servicos.saldos()
    qs = _produtos_estoque().order_by('category__category', 'product')
    if cat:
        qs = qs.filter(category_id=cat)
    return render(request, 'producao/contagem.html', {
        'menu': 'estoque', 'linhas': [{'p': p, 'saldo': s.get(p.pk, 0)} for p in qs], 'cfg': cfg, 'cat': cat,
        'categorias': Category.objects.exclude(category=CATEGORIA_GENERICA),
    })
