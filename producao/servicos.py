"""Regras da fila de impressão e do estoque."""
from collections import defaultdict

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (ConfigEstoque, EstoqueMinimo, Impressao, KitPeca, MovimentoEstoque, StatusImpressao as S,
                     TipoMovimento)

CATEGORIA_GENERICA = 'Encomendas'  # "Peça personalizada", "Frete / entrega": não têm estoque


class ErroProducao(Exception):
    pass


# ---------------------------------------------------------------------------
# Saldos
# ---------------------------------------------------------------------------
def saldos():
    """{produto_id: quantidade em estoque}"""
    return {l['produto_id']: l['t'] or 0
            for l in MovimentoEstoque.objects.order_by().values('produto_id').annotate(t=Sum('qnt'))}


def saldo(produto):
    return MovimentoEstoque.objects.filter(produto=produto).aggregate(t=Sum('qnt'))['t'] or 0


def composicoes():
    """{produto_id do kit: [(peca_id, qnt), ...]}"""
    r = defaultdict(list)
    for kit_pid, peca_id, qnt in KitPeca.objects.values_list('kit__produto_id', 'peca_id', 'qnt'):
        r[kit_pid].append((peca_id, qnt))
    return dict(r)


def reservados():
    """{produto_id: peças separadas para pedidos ainda não entregues} (kits viram as peças deles)"""
    from encomendas.models import ETAPAS, ItemPedido
    comp = composicoes()
    r = defaultdict(int)
    for l in (ItemPedido.objects.filter(pedido__status__in=ETAPAS, produto__isnull=False)
              .exclude(produto__category__category=CATEGORIA_GENERICA)
              .order_by().values('produto_id').annotate(t=Sum('qnt'))):
        for pid, q in comp.get(l['produto_id'], [(l['produto_id'], 1)]):
            r[pid] += (l['t'] or 0) * q
    return dict(r)


def kits_possiveis(s=None, r=None):
    """{produto_id do kit: quantos kits dá para montar com o estoque disponível}"""
    s = saldos() if s is None else s
    r = reservados() if r is None else r
    res = {}
    for kit_pid, pecas in composicoes().items():
        if pecas:
            res[kit_pid] = max(0, min((s.get(pid, 0) - r.get(pid, 0)) // q for pid, q in pecas))
    return res


def em_producao():
    """{produto_id: peças na fila, imprimindo ou em acabamento, indo para o estoque}"""
    r = defaultdict(int)
    for l in (Impressao.objects.filter(status__in=[S.FILA, S.IMPRIMINDO, S.IMPRESSO], produto__isnull=False)
              .order_by().values('produto_id').annotate(t=Sum('qnt'))):
        r[l['produto_id']] += l['t'] or 0
    return dict(r)


def minimos():
    return dict(EstoqueMinimo.objects.values_list('produto_id', 'minimo'))


def precisa_imprimir(limite=None):
    """Produtos com disponível (estoque − reservado) abaixo do mínimo, já contando o que está em produção."""
    from cadastro.models import Product
    mins = {k: v for k, v in minimos().items() if v}
    if not mins:
        return []
    s, r, p = saldos(), reservados(), em_producao()
    lista = []
    for prod in Product.objects.filter(pk__in=mins.keys()):
        disp = s.get(prod.pk, 0) - r.get(prod.pk, 0)
        falta = mins[prod.pk] - disp - p.get(prod.pk, 0)
        if disp < mins[prod.pk]:
            lista.append({'produto': prod, 'disponivel': disp, 'minimo': mins[prod.pk],
                          'producao': p.get(prod.pk, 0), 'falta': max(0, falta)})
    lista.sort(key=lambda x: (-x['falta'], x['disponivel'] - x['minimo']))
    return lista[:limite] if limite else lista


def _generico(produto):
    return produto.category.category == CATEGORIA_GENERICA


# ---------------------------------------------------------------------------
# Vendas -> saída do estoque (chamado pelos sinais)
# ---------------------------------------------------------------------------
def _sincronizar(campo, venda, produto, data, qnt, tipo, obs):
    """Refaz a(s) saída(s) de estoque de uma venda. Venda de kit tira cada peça do kit."""
    inicio = ConfigEstoque.atual().inicio
    filtro = {campo: venda}
    desejado = []
    if qnt and qnt > 0 and data >= inicio and not _generico(produto):
        pecas = list(KitPeca.objects.filter(kit__produto=produto).values_list('peca_id', 'qnt'))
        if pecas:
            obs = f'Kit {produto.product} · {obs}'[:300]
            desejado = [(pid, qnt * q) for pid, q in pecas]
        elif not hasattr(produto, 'kit'):
            desejado = [(produto.pk, qnt)]
    atuais = {(m.produto_id, -m.qnt): m for m in MovimentoEstoque.objects.filter(**filtro)}
    for pid, q in desejado:
        m = atuais.pop((pid, q), None)
        if m:
            if m.data != data or m.observacao != obs or m.tipo != tipo:
                m.data, m.observacao, m.tipo = data, obs, tipo
                m.save(update_fields=['data', 'observacao', 'tipo'])
        else:
            MovimentoEstoque.objects.create(produto_id=pid, data=data, tipo=tipo, qnt=-q, observacao=obs, **filtro)
    for m in atuais.values():
        m.delete()


def sincronizar_venda_feira(venda):
    feira = venda.nomeFeira
    _sincronizar('venda_feira', venda, venda.product, feira.date, venda.qnt, TipoMovimento.VENDA_FEIRA, feira.name)


def sincronizar_venda_interna(venda):
    _sincronizar('venda_interna', venda, venda.product, venda.date, venda.qnt or 0, TipoMovimento.VENDA_DIRETA,
                 str(venda.client))


def ressincronizar_vendas(desde=None):
    """Refaz as saídas de todas as vendas (usado quando muda a data de início do estoque)."""
    from vendas.models import Feiras, VendasInternas
    inicio = desde or ConfigEstoque.atual().inicio
    MovimentoEstoque.objects.filter(venda_feira__isnull=False, data__lt=inicio).delete()
    MovimentoEstoque.objects.filter(venda_interna__isnull=False, data__lt=inicio).delete()
    for v in Feiras.objects.filter(nomeFeira__date__gte=inicio).select_related('nomeFeira', 'product__category'):
        sincronizar_venda_feira(v)
    for v in VendasInternas.objects.filter(date__gte=inicio).select_related('client', 'product__category'):
        sincronizar_venda_interna(v)


# ---------------------------------------------------------------------------
# Ajustes manuais
# ---------------------------------------------------------------------------
def ajustar(produto, tipo, qnt, obs='', usuario='', data=None):
    if tipo not in (TipoMovimento.ENTRADA, TipoMovimento.SAIDA, TipoMovimento.PERDA):
        raise ErroProducao('Tipo de ajuste inválido.')
    if qnt <= 0:
        raise ErroProducao('Informe uma quantidade maior que zero.')
    sinal = 1 if tipo == TipoMovimento.ENTRADA else -1
    return MovimentoEstoque.objects.create(produto=produto, tipo=tipo, qnt=sinal * qnt, observacao=obs[:300],
                                           usuario=usuario, data=data or timezone.localdate())


def definir_contagem(produto, contado, usuario='', obs=''):
    """Lança a diferença para o saldo ficar igual ao que foi contado. Retorna a diferença."""
    dif = contado - saldo(produto)
    if dif:
        MovimentoEstoque.objects.create(produto=produto, tipo=TipoMovimento.CONTAGEM, qnt=dif, usuario=usuario,
                                        observacao=obs or f'Contagem: {contado} na prateleira')
    return dif


# ---------------------------------------------------------------------------
# Fila de impressão
# ---------------------------------------------------------------------------
def ocupada(impressora, exceto=None):
    qs = Impressao.objects.filter(impressora=impressora, status=S.IMPRIMINDO)
    if exceto:
        qs = qs.exclude(pk=exceto.pk)
    return qs.first()


@transaction.atomic
def iniciar(imp, impressora=None):
    if imp.status != S.FILA:
        raise ErroProducao('Esta impressão não está na fila.')
    impressora = impressora or imp.impressora
    if not impressora:
        raise ErroProducao('Escolha a impressora.')
    outra = ocupada(impressora, exceto=imp)
    if outra:
        raise ErroProducao(f'A {impressora} já está imprimindo {outra.nome}. Finalize aquela impressão antes.')
    imp.impressora = impressora
    imp.status = S.IMPRIMINDO
    imp.iniciado_em = timezone.now()
    imp.save()
    atualizar_pedido(imp)


@transaction.atomic
def marcar_impresso(imp):
    if imp.status != S.IMPRIMINDO:
        raise ErroProducao('Esta impressão não está imprimindo.')
    imp.status = S.IMPRESSO
    imp.impresso_em = timezone.now()
    imp.save()
    atualizar_pedido(imp)


@transaction.atomic
def concluir(imp, boas=None, usuario=''):
    if imp.status not in (S.IMPRIMINDO, S.IMPRESSO):
        raise ErroProducao('Esta impressão ainda não foi impressa.')
    boas = imp.qnt if boas is None else boas
    if boas < 0 or boas > imp.qnt:
        raise ErroProducao(f'As peças boas devem ficar entre 0 e {imp.qnt}.')
    agora = timezone.now()
    imp.impresso_em = imp.impresso_em or agora
    imp.status = S.PRONTA
    imp.qnt_boas = boas
    imp.concluido_em = agora
    imp.save()
    if imp.vai_para_estoque and boas:
        destino = f' · {imp.pedido.numero}' if imp.pedido else ''
        MovimentoEstoque.objects.update_or_create(
            impressao=imp, defaults={'produto': imp.produto, 'tipo': TipoMovimento.IMPRESSAO, 'qnt': boas,
                                     'data': timezone.localdate(), 'usuario': usuario,
                                     'observacao': f'{imp.numero}{" · " + str(imp.impressora) if imp.impressora else ""}{destino}'})
    atualizar_pedido(imp)


@transaction.atomic
def falhou(imp, obs=''):
    if imp.status not in (S.IMPRIMINDO, S.IMPRESSO):
        raise ErroProducao('Só dá para marcar falha em uma impressão começada.')
    imp.status = S.FALHOU
    imp.qnt_boas = 0
    imp.concluido_em = timezone.now()
    if obs:
        imp.observacao = (f'{imp.observacao} · Falha: {obs}' if imp.observacao else f'Falha: {obs}')[:300]
    imp.save()


def repetir(imp):
    """Nova impressão igual, na fila."""
    return Impressao.objects.create(produto=imp.produto, item_pedido=imp.item_pedido, descricao=imp.descricao,
                                    impressora=imp.impressora, qnt=imp.qnt, horas=imp.horas, gramas=imp.gramas,
                                    calculo=imp.calculo)


def cancelar(imp):
    if imp.status != S.FILA:
        raise ErroProducao('Só dá para cancelar o que ainda está na fila.')
    imp.status = S.CANCELADA
    imp.concluido_em = timezone.now()
    imp.save()


@transaction.atomic
def voltar(imp):
    """Desfaz o último passo (para corrigir um clique errado)."""
    if imp.status == S.PRONTA:
        MovimentoEstoque.objects.filter(impressao=imp).delete()
        imp.status, imp.qnt_boas, imp.concluido_em = S.IMPRESSO, None, None
    elif imp.status == S.FALHOU:
        imp.status = S.IMPRESSO if imp.impresso_em else S.IMPRIMINDO
        imp.qnt_boas, imp.concluido_em = None, None
    elif imp.status == S.IMPRESSO:
        imp.status, imp.impresso_em = S.IMPRIMINDO, None
    elif imp.status == S.IMPRIMINDO:
        imp.status, imp.iniciado_em = S.FILA, None
    elif imp.status == S.CANCELADA:
        imp.status, imp.concluido_em = S.FILA, None
    else:
        raise ErroProducao('Não há o que desfazer.')
    if imp.status == S.IMPRIMINDO and imp.impressora_id and ocupada(imp.impressora, exceto=imp):
        raise ErroProducao(f'A {imp.impressora} já está com outra impressão.')
    imp.save()


# ---------------------------------------------------------------------------
# Pedido acompanha a produção
# ---------------------------------------------------------------------------
def andamento_item(item):
    """Quantas peças do item já foram impressas / estão prontas pela fila."""
    impressas = prontas = 0
    andando = False
    for i in item.impressoes.all():
        if i.status == S.PRONTA:
            prontas += i.qnt_boas or 0
            impressas += i.qnt_boas or 0
        elif i.status == S.IMPRESSO:
            impressas += i.qnt
        if i.status in (S.FILA, S.IMPRIMINDO, S.IMPRESSO):
            andando = True
    return {'impressas': impressas, 'prontas': prontas, 'andando': andando,
            'falta': max(0, item.qnt - prontas - sum(i.qnt for i in item.impressoes.all()
                                                    if i.status in (S.FILA, S.IMPRIMINDO, S.IMPRESSO)))}


def atualizar_pedido(imp):
    """Move o pedido para frente conforme as impressões dele andam (nunca para trás)."""
    from encomendas.models import ETAPAS, StatusPedido
    pedido = imp.pedido
    if not pedido or pedido.status not in ETAPAS:
        return
    itens = list(pedido.itens.prefetch_related('impressoes'))
    if not itens:
        return
    andamentos = [andamento_item(i) for i in itens]
    comecou = any(i.status != S.FILA for it in itens for i in it.impressoes.all()
                  if i.status not in (S.CANCELADA,))
    if all(a['prontas'] >= it.qnt for a, it in zip(andamentos, itens)):
        nova = StatusPedido.PRONTO
    elif all(a['impressas'] >= it.qnt for a, it in zip(andamentos, itens)):
        nova = StatusPedido.ACABAMENTO
    elif comecou:
        nova = StatusPedido.IMPRIMINDO
    else:
        return
    if ETAPAS.index(nova) > ETAPAS.index(pedido.status):
        pedido.status = nova
        pedido.save(update_fields=['status'])
