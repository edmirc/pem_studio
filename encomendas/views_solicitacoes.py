from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import servicos
from .arquivos import ArquivoInvalido, salvar_anexo
from .forms import SolicitacaoForm
from .models import (ABERTAS, Anexo, Anotacao, Configuracao, ItemOrcamento, Orcamento, Solicitacao,
                     StatusSolicitacao)

MATERIAIS = ['PLA', 'PLA Silk', 'PLA Matte', 'PETG', 'TPU (flexível)', 'ABS', 'ASA', 'PLA-CF', 'Resina']


def _anexar(request, solicitacao, anotacao=None):
    ok = 0
    for f in request.FILES.getlist('arquivos'):
        try:
            salvar_anexo(solicitacao, f, anotacao)
            ok += 1
        except ArquivoInvalido as e:
            messages.error(request, str(e))
        except OSError as e:
            messages.error(request, f'Não consegui gravar {f.name} na pasta de imagens ({e.strerror}). '
                                    'Confira se o HD externo está montado e com permissão de escrita.')
            break
    return ok


@login_required
def solicitacoes(request):
    status = request.GET.get('status', 'abertas')
    q = request.GET.get('q', '').strip()
    qs = Solicitacao.objects.select_related('cliente').prefetch_related('anexos') \
        .annotate(n_anexos=Count('anexos', distinct=True))
    if status == 'abertas':
        qs = qs.filter(status__in=ABERTAS)
    elif status != 'todas':
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(titulo__icontains=q) | Q(descricao__icontains=q) | Q(nome_cliente__icontains=q)
                       | Q(cliente__name__icontains=q) | Q(telefone__icontains=q))
    contagem = dict(Solicitacao.objects.order_by().values_list('status').annotate(n=Count('id')))
    return render(request, 'encomendas/solicitacoes.html', {
        'menu': 'solicitacoes', 'lista': qs[:200], 'status': status, 'q': q,
        'situacoes': StatusSolicitacao.choices, 'contagem': contagem,
        'abertas': sum(contagem.get(s, 0) for s in ABERTAS),
    })


@login_required
def solicitacao_editar(request, pk=None):
    obj = get_object_or_404(Solicitacao, pk=pk) if pk else None
    form = SolicitacaoForm(request.POST or None, instance=obj)
    if request.method == 'POST':
        if form.is_valid():
            novo = form.save()
            n = _anexar(request, novo)
            messages.success(request, f'Solicitação {novo.numero} salva' + (f' com {n} arquivo{"s" if n > 1 else ""}.' if n else '.'))
            return redirect('encomendas:solicitacao', pk=novo.pk)
        messages.error(request, 'Confira os campos destacados.')
    return render(request, 'encomendas/solicitacao_form.html', {
        'menu': 'solicitacoes', 'form': form, 'obj': obj, 'materiais': MATERIAIS,
    })


@login_required
def solicitacao(request, pk):
    s = get_object_or_404(Solicitacao.objects.select_related('cliente'), pk=pk)
    anexos = list(s.anexos.all())
    anotacoes = list(s.anotacoes.prefetch_related('anexos'))
    return render(request, 'encomendas/solicitacao.html', {
        'menu': 'solicitacoes', 's': s,
        'imagens': [a for a in anexos if a.e_imagem],
        'arquivos': [a for a in anexos if not a.e_imagem],
        'anotacoes': anotacoes,
        'orcamentos': s.orcamentos.all(),
        'situacoes': StatusSolicitacao.choices,
        'whatsapp': servicos.link_whatsapp(s.telefone_exibicao, '') if s.telefone_exibicao else '',
    })


@login_required
@require_POST
def solicitacao_acao(request, pk, acao):
    s = get_object_or_404(Solicitacao, pk=pk)
    if acao == 'status':
        novo = request.POST.get('status')
        if novo in dict(StatusSolicitacao.choices):
            s.status = novo
            s.save(update_fields=['status', 'atualizado_em'])
    elif acao == 'anotar':
        texto = request.POST.get('texto', '').strip()
        if not texto and not request.FILES.getlist('arquivos'):
            messages.error(request, 'Escreva algo ou anexe um arquivo.')
        else:
            nota = Anotacao.objects.create(solicitacao=s, texto=texto,
                                           autor=request.user.get_full_name() or request.user.username)
            _anexar(request, s, nota)
            Solicitacao.objects.filter(pk=s.pk).update(atualizado_em=timezone.now())
    elif acao == 'anexar':
        n = _anexar(request, s)
        if n:
            messages.success(request, f'{n} arquivo{"s" if n > 1 else ""} anexado{"s" if n > 1 else ""}.')
    elif acao == 'apagar-anexo':
        a = get_object_or_404(Anexo, pk=request.POST.get('anexo'), solicitacao=s)
        a.delete()
        messages.info(request, 'Arquivo apagado.')
    elif acao == 'apagar-anotacao':
        get_object_or_404(Anotacao, pk=request.POST.get('anotacao'), solicitacao=s).delete()
    elif acao == 'orcamento':
        cfg = Configuracao.atual()
        hoje = timezone.localdate()
        orc = Orcamento.objects.create(
            solicitacao=s, cliente=s.cliente, nome_cliente=s.nome_cliente, telefone=s.telefone,
            validade=hoje + timedelta(days=cfg.validade_dias), prazo_dias=cfg.prazo_dias,
            sinal_percentual=cfg.sinal_percentual)
        ItemOrcamento.objects.create(orcamento=orc, descricao=s.titulo, qnt=s.quantidade or 1, preco_unitario=0)
        s.status = StatusSolicitacao.ORCADA
        s.save(update_fields=['status', 'atualizado_em'])
        messages.info(request, f'Orçamento {orc.numero} criado a partir da solicitação. Use 🧮 para calcular o preço.')
        return redirect('encomendas:orcamento_editar', pk=orc.pk)
    elif acao == 'apagar':
        if s.orcamentos.exists():
            messages.error(request, 'Esta solicitação tem orçamento; marque como Descartada em vez de apagar.')
        else:
            for a in s.anexos.all():
                a.delete()
            s.delete()
            messages.success(request, 'Solicitação apagada.')
            return redirect('encomendas:solicitacoes')
    return redirect('encomendas:solicitacao', pk=pk)


@login_required
def arquivo(request, pk, tipo='arquivo'):
    a = get_object_or_404(Anexo, pk=pk)
    f = a.miniatura if (tipo == 'mini' and a.miniatura) else a.arquivo
    try:
        arq = f.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('Arquivo não encontrado na pasta de imagens.')
    baixar = request.GET.get('baixar') == '1' or not a.e_imagem
    nome = a.nome_original
    if a.e_imagem and tipo != 'mini' and baixar:
        nome = nome.rsplit('.', 1)[0] + '.' + f.name.rsplit('.', 1)[-1]
    resp = FileResponse(arq, as_attachment=baixar, filename=nome)
    resp['Cache-Control'] = 'private, max-age=86400'
    return resp
