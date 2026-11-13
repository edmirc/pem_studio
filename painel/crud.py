"""
Telas genéricas de lista / novo / editar / apagar.

Cada cadastro é descrito por um dicionário em CADASTROS. Para criar uma tela
nova basta acrescentar uma entrada aqui; a URL fica /<slug>/.
"""
from django.utils import timezone
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.contrib.admin.utils import NestedObjects
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from cadastro.models import (CadClientes, CadFeiras, Category, Contas, FilamentBrand,
                             FilametType, Filment, Insumo, Product)
from financas.models import CompraFilamento, CompraInsumo, Compras
from vendas.models import Feiras, Precificacao, VendasFeiras, VendasInternas

from .utils import brl, data_br, ler_mes, mes_anterior, mes_seguinte, nome_mes, num


# --------------------------------------------------------------------------
# Formatação das colunas
# --------------------------------------------------------------------------
def _valor(obj, caminho):
    for parte in caminho.split('.'):
        obj = getattr(obj, parte, None)
        if callable(obj):
            obj = obj()
        if obj is None:
            return None
    return obj


def _formatar(valor, tipo):
    if valor is None or valor == '':
        return '—'
    if tipo == 'brl':
        return brl(valor)
    if tipo == 'data':
        return data_br(valor)
    if tipo == 'num':
        return num(valor, 0 if Decimal(valor) == int(valor) else 2)
    return str(valor)


def margem(obj):
    if obj.vanda and obj.custo:
        return f'{num((obj.vanda - obj.custo) * 100 / obj.vanda, 0)}%'
    return None


def preco_venda(obj):
    pr = obj.precificacao_set.first()
    return brl(pr.vanda) if pr and pr.vanda else None


def preco_kg(obj):
    return brl(obj.preco_kg) if obj.preco_kg else None


# --------------------------------------------------------------------------
# Configuração dos cadastros
#   colunas: (caminho do atributo | função, título, tipo)
#   tipo: None, 'brl', 'data', 'num'
# --------------------------------------------------------------------------
CADASTROS = {
    # ---------------- Cadastros ----------------
    'clientes': dict(
        model=CadClientes, titulo='Clientes', singular='cliente', menu='clientes', grupo='Cadastros',
        campos=['name', 'telefone', 'cpf', 'date_nasc', 'endereco'],
        colunas=[('name', 'Nome', None), ('telefone', 'Telefone', None), ('cpf', 'CPF', None),
                 ('date_nasc', 'Nascimento', 'data'), ('endereco', 'Endereço', None)],
        busca=['name', 'telefone', 'cpf'],
        detalhe='painel:cliente',
    ),
    'produtos': dict(
        model=Product, titulo='Produtos', singular='produto', menu='produtos', grupo='Cadastros',
        campos=['product', 'category'], prefetch=['precificacao_set'],
        colunas=[('product', 'Produto', None), ('category', 'Categoria', None),
                 (preco_venda, 'Preço de venda', None)],
        busca=['product', 'category__category'],
        filtros=[('category', 'Categoria', Category.objects.all)],
    ),
    'categorias': dict(
        model=Category, titulo='Categorias', singular='categoria', fem=True, menu='categorias', grupo='Cadastros',
        campos=['category'], colunas=[('category', 'Categoria', None)], busca=['category'],
    ),
    'precificacao': dict(
        model=Precificacao, titulo='Precificação', singular='precificação', fem=True, menu='precificacao', grupo='Cadastros',
        campos=['product', 'impressao', 'filament', 'embalagem', 'acessorios', 'vanda'],
        colunas=[('product', 'Produto', None), ('impressao', 'Horas', 'num'), ('filament', 'Filamento', 'brl'),
                 ('custo', 'Custo', 'brl'), ('sugerido', 'Sugerido', 'brl'), ('vanda', 'Venda', 'brl'),
                 (margem, 'Margem', None)],
        busca=['product__product'],
        filtros=[('product__category', 'Categoria', Category.objects.all)],
        form_template='painel/form_precificacao.html',
        rotulos={'vanda': 'Preço de venda', 'filament': 'Custo do filamento (R$)',
                 'impressao': 'Horas de impressão'},
    ),
    'filamentos': dict(
        model=Filment, titulo='Filamentos', singular='filamento', menu='filamentos', grupo='Cadastros',
        campos=['name', 'color', 'filamentBrand', 'filamentType'],
        colunas=[('name', 'Filamento', None), ('color', 'Cor', None), ('filamentBrand', 'Marca', None),
                 ('filamentType', 'Tipo', None)],
        busca=['name', 'color', 'filamentBrand__name'],
        filtros=[('filamentBrand', 'Marca', FilamentBrand.objects.all),
                 ('filamentType', 'Tipo', FilametType.objects.all)],
    ),
    'marcas': dict(
        model=FilamentBrand, titulo='Marcas de filamento', singular='marca', fem=True, menu='marcas', grupo='Cadastros',
        campos=['name'], colunas=[('name', 'Marca', None)], busca=['name'],
    ),
    'tipos-filamento': dict(
        model=FilametType, titulo='Tipos de filamento', singular='tipo', menu='tipos', grupo='Cadastros',
        campos=['type'], colunas=[('type', 'Tipo', None)], busca=['type'], ordem=('type',),
    ),
    'insumos': dict(
        model=Insumo, titulo='Insumos', singular='insumo', menu='insumos', grupo='Cadastros',
        campos=['name', 'unidade', 'observacao'],
        colunas=[('name', 'Insumo', None), ('get_unidade_display', 'Unidade', None),
                 ('observacao', 'Observação', None)],
        busca=['name'],
    ),
    'feiras': dict(
        model=CadFeiras, titulo='Feiras', singular='feira', fem=True, menu='feiras', grupo='Cadastros',
        campos=['date', 'name', 'local'],
        colunas=[('date', 'Data', 'data'), ('name', 'Nome', None), ('local', 'Local', None)],
        busca=['name', 'local'], campo_data='date', ordem=('-date',),
    ),
    'contas': dict(
        model=Contas, titulo='Contas e cartões', singular='conta', fem=True, menu='contas', grupo='Cadastros',
        campos=['apelido', 'banco', 'name', 'operacao'],
        colunas=[('apelido', 'Nome do cartão', None), ('banco', 'Banco / cartão', None),
                 ('name', 'Titular', None), ('get_operacao_display', 'Operação', None)],
        busca=['apelido', 'banco', 'name'],
    ),

    # ---------------- Compras ----------------
    'compras-filamento': dict(
        model=CompraFilamento, titulo='Compras de filamento', singular='compra de filamento', fem=True,
        menu='compras-filamento', grupo='Compras',
        campos=['date', 'filamento', 'qnt', 'peso', 'valor', 'fornecedor', 'pagamento', 'parcelas'],
        colunas=[('date', 'Data', 'data'), ('filamento', 'Filamento', None), ('filamento.color', 'Cor', None),
                 ('qnt', 'Rolos', 'num'), ('valor', 'Valor', 'brl'), (preco_kg, 'R$/kg', None),
                 ('fornecedor', 'Fornecedor', None), ('pagamento', 'Pagamento', None), ('parcelas', 'Parc.', 'num')],
        busca=['filamento__name', 'filamento__color', 'fornecedor'],
        filtros=[('filamento__filamentBrand', 'Marca', FilamentBrand.objects.all)],
        campo_data='date', somar='valor', fornecedores=True,
    ),
    'compras-insumo': dict(
        model=CompraInsumo, titulo='Compras de insumos', singular='compra de insumo', fem=True,
        menu='compras-insumo', grupo='Compras',
        campos=['date', 'insumo', 'qnt', 'valor', 'fornecedor', 'pagamento', 'parcelas'],
        colunas=[('date', 'Data', 'data'), ('insumo', 'Insumo', None), ('qnt', 'Qtd.', 'num'),
                 ('valor', 'Valor', 'brl'), ('preco_unitario', 'Unitário', 'brl'),
                 ('fornecedor', 'Fornecedor', None), ('pagamento', 'Pagamento', None), ('parcelas', 'Parc.', 'num')],
        busca=['insumo__name', 'fornecedor'],
        filtros=[('insumo', 'Insumo', Insumo.objects.all)],
        campo_data='date', somar='valor', fornecedores=True,
    ),
    'despesas': dict(
        model=Compras, titulo='Outras despesas', singular='despesa', fem=True, menu='despesas', grupo='Compras',
        campos=['date', 'saida', 'valor', 'fornecedor', 'pagamento', 'parcela'],
        colunas=[('date', 'Data', 'data'), ('saida', 'Descrição', None), ('valor', 'Valor', 'brl'),
                 ('fornecedor', 'Fornecedor', None), ('pagamento', 'Pagamento', None), ('parcela', 'Parcelas', None)],
        busca=['saida', 'fornecedor'],
        campo_data='date', somar='valor', ordem=('-date', '-id'), fornecedores=True,
        rotulos={'saida': 'Descrição'},
    ),

    # ---------------- Vendas ----------------
    'vendas-internas': dict(
        model=VendasInternas, titulo='Vendas diretas', singular='venda', fem=True, menu='vendas-internas', grupo='Vendas',
        campos=['date', 'client', 'product', 'qnt', 'valor', 'pagment'],
        colunas=[('date', 'Data', 'data'), ('client', 'Cliente', None), ('product', 'Produto', None),
                 ('qnt', 'Qtd.', 'num'), ('valor', 'Valor', 'brl'), ('get_pagment_display', 'Pagamento', None)],
        busca=['client__name', 'product__product'],
        filtros=[('pagment', 'Pagamento', None)],
        campo_data='date', somar='valor',
        form_template='painel/form_venda.html',
        rotulos={'pagment': 'Forma de pagamento', 'valor': 'Valor total'},
    ),
    'vendas-feira': dict(
        model=Feiras, titulo='Vendas de feira', singular='venda de feira', fem=True, menu='vendas-feira', grupo='Vendas',
        campos=['nomeFeira', 'product', 'qnt', 'value', 'pagment'],
        colunas=[('nomeFeira.date', 'Data', 'data'), ('nomeFeira.name', 'Feira', None), ('product', 'Produto', None),
                 ('qnt', 'Qtd.', 'num'), ('value', 'Valor', 'brl'), ('get_pagment_display', 'Pagamento', None)],
        busca=['product__product', 'nomeFeira__name'],
        filtros=[('nomeFeira', 'Feira', lambda: CadFeiras.objects.order_by('-date')[:60]),
                 ('pagment', 'Pagamento', None)],
        campo_data='nomeFeira__date', somar='value', ordem=('-nomeFeira__date', '-id'),
        form_template='painel/form_venda.html',
        rotulos={'value': 'Valor total', 'pagment': 'Forma de pagamento'},
    ),
}


def get_config(slug):
    try:
        cfg = CADASTROS[slug]
    except KeyError:
        raise Http404('Cadastro não encontrado')
    fem = cfg.get('fem', False)
    return dict(cfg, slug=slug, novo='Nova' if fem else 'Novo',
                salvo='salva' if fem else 'salvo', apagado='apagada' if fem else 'apagado')


# --------------------------------------------------------------------------
# Formulários
# --------------------------------------------------------------------------
class FormBase(forms.ModelForm):
    def __init__(self, *args, rotulos=None, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if rotulos and nome in rotulos:
                campo.label = rotulos[nome]
            campo.widget.attrs.setdefault('class', 'campo')


def _widget(campo_model, **kwargs):
    if isinstance(campo_model, models.DateField):
        return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
    if isinstance(campo_model, models.DecimalField):
        return forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'})
    if isinstance(campo_model, (models.IntegerField, models.PositiveIntegerField)):
        return forms.NumberInput(attrs={'step': '1', 'min': '0', 'inputmode': 'numeric'})
    return campo_model.formfield(**kwargs)


def form_para(cfg):
    model = cfg['model']
    widgets = {}
    for nome in cfg['campos']:
        campo = model._meta.get_field(nome)
        if isinstance(campo, (models.DateField, models.DecimalField, models.IntegerField)) and not campo.choices \
                and not isinstance(campo, models.ForeignKey):
            widgets[nome] = _widget(campo)
        if nome == 'fornecedor':
            widgets[nome] = forms.TextInput(attrs={'list': 'lista-fornecedores', 'autocomplete': 'off'})
        if nome == 'telefone':
            widgets[nome] = forms.TextInput(attrs={'inputmode': 'tel', 'placeholder': '(65) 99999-9999'})
    return forms.modelform_factory(model, form=FormBase, fields=cfg['campos'], widgets=widgets)


def _fornecedores():
    nomes = set()
    for m, campo in ((CompraFilamento, 'fornecedor'), (CompraInsumo, 'fornecedor'), (Compras, 'fornecedor')):
        nomes.update(v for v in m.objects.values_list(campo, flat=True).distinct() if v)
    return sorted(nomes, key=str.lower)


def _depois_de_salvar(obj):
    """Mantém a tabela de totais da feira (usada no Admin) atualizada."""
    if isinstance(obj, Feiras):
        atualizar_totais_feira(obj.nomeFeira)


def atualizar_totais_feira(feira):
    if feira is None:
        return
    if Feiras.objects.filter(nomeFeira=feira).exists():
        VendasFeiras(feira=feira).save()  # o save() do model recalcula os totais
    else:
        VendasFeiras.objects.filter(feira=feira).delete()


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------
@login_required
def lista(request, slug):
    cfg = get_config(slug)
    model = cfg['model']
    qs = model.objects.all()
    if cfg.get('prefetch'):
        qs = qs.prefetch_related(*cfg['prefetch'])
    if cfg.get('ordem'):
        qs = qs.order_by(*cfg['ordem'])

    # busca
    q = request.GET.get('q', '').strip()
    if q:
        filtro = Q()
        for campo in cfg.get('busca', []):
            filtro |= Q(**{f'{campo}__icontains': q})
        qs = qs.filter(filtro)

    # filtros por campo
    filtros_ctx = []
    for campo, rotulo, opcoes in cfg.get('filtros', []):
        valor = request.GET.get(campo, '')
        if opcoes is None:  # choices do model
            escolhas = [(str(k), v) for k, v in model._meta.get_field(campo).choices]
        else:
            escolhas = [(str(o.pk), str(o)) for o in opcoes()]
        if valor:
            qs = qs.filter(**{campo: valor})
        filtros_ctx.append({'campo': campo, 'rotulo': rotulo, 'opcoes': escolhas, 'valor': valor})

    # filtro por mês
    mes_ctx = None
    campo_data = cfg.get('campo_data')
    if campo_data:
        mes_txt = request.GET.get('mes', '')
        if mes_txt == 'todos' or (not mes_txt and slug in ('feiras',)):
            mes_ctx = {'todos': True, 'valor': 'todos'}
        else:
            ano, mes = ler_mes(mes_txt)
            qs = qs.filter(**{f'{campo_data}__year': ano, f'{campo_data}__month': mes})
            pa, pm = mes_anterior(ano, mes)
            sa, sm = mes_seguinte(ano, mes)
            mes_ctx = {'todos': False, 'valor': f'{ano}-{mes:02d}', 'nome': nome_mes(ano, mes),
                       'anterior': f'{pa}-{pm:02d}', 'seguinte': f'{sa}-{sm:02d}'}

    total = None
    if cfg.get('somar'):
        total = qs.aggregate(t=Sum(cfg['somar']))['t'] or Decimal('0')

    pagina = Paginator(qs, 50).get_page(request.GET.get('pagina'))
    linhas = []
    for obj in pagina:
        celulas = []
        for caminho, _, tipo in cfg['colunas']:
            valor = caminho(obj) if callable(caminho) else _valor(obj, caminho)
            celulas.append({'texto': _formatar(valor, tipo), 'num': tipo in ('brl', 'num')})
        link = reverse(cfg['detalhe'], args=[obj.pk]) if cfg.get('detalhe') else None
        linhas.append({'obj': obj, 'celulas': celulas, 'link': link})

    params = request.GET.copy()
    params.pop('pagina', None)

    return render(request, 'painel/lista.html', {
        'cfg': cfg, 'menu': cfg['menu'], 'linhas': linhas, 'pagina': pagina, 'q': q,
        'colunas': [{'titulo': c[1], 'num': c[2] in ('brl', 'num')} for c in cfg['colunas']],
        'filtros': filtros_ctx, 'mes': mes_ctx, 'total': total, 'qtd': pagina.paginator.count,
        'params': params.urlencode(),
    })


@login_required
def editar(request, slug, pk=None):
    cfg = get_config(slug)
    Form = form_para(cfg)
    obj = get_object_or_404(cfg['model'], pk=pk) if pk else None

    if request.method == 'POST':
        form = Form(request.POST, instance=obj, rotulos=cfg.get('rotulos'))
        if form.is_valid():
            novo = form.save()
            _depois_de_salvar(novo)
            messages.success(request, f'{cfg["singular"].capitalize()} {cfg["salvo"]} com sucesso.')
            if 'salvar_e_novo' in request.POST:
                return redirect('painel:novo', slug=slug)
            proximo = request.POST.get('proximo')
            if proximo and proximo.startswith('/'):
                return redirect(proximo)
            return redirect('painel:lista', slug=slug)
    else:
        inicial = {}
        for nome in cfg['campos']:
            if nome == 'date':
                inicial['date'] = timezone.localdate()
            if nome in request.GET:
                inicial[nome] = request.GET[nome]
        form = Form(instance=obj, initial=inicial, rotulos=cfg.get('rotulos'))

    ctx = {'cfg': cfg, 'menu': cfg['menu'], 'form': form, 'obj': obj,
           'proximo': request.GET.get('proximo', '')}
    if cfg.get('fornecedores'):
        ctx['fornecedores'] = _fornecedores()
    if cfg.get('form_template') == 'painel/form_venda.html' or slug == 'precificacao':
        ctx['precos'] = {str(p.product_id): str(p.vanda or p.sugerido or '')
                         for p in Precificacao.objects.all()}
    return render(request, cfg.get('form_template', 'painel/form.html'), ctx)


@login_required
def apagar(request, slug, pk):
    cfg = get_config(slug)
    obj = get_object_or_404(cfg['model'], pk=pk)

    coletor = NestedObjects(using='default')
    coletor.collect([obj])
    relacionados = [f'{len(objs)} {m._meta.verbose_name_plural}'
                    for m, objs in coletor.model_objs.items() if m is not cfg['model'] and objs]
    bloqueado = None
    if coletor.protected:
        bloqueado = (f'Não é possível apagar: existem {len(coletor.protected)} registro(s) usando este item '
                     f'(ex.: {next(iter(coletor.protected))}).')

    if request.method == 'POST' and not bloqueado:
        feira = obj.nomeFeira if isinstance(obj, Feiras) else None
        obj.delete()
        atualizar_totais_feira(feira)
        messages.success(request, f'{cfg["singular"].capitalize()} {cfg["apagado"]}.')
        proximo = request.POST.get('proximo')
        if proximo and proximo.startswith('/'):
            return redirect(proximo)
        return redirect('painel:lista', slug=slug)

    return render(request, 'painel/apagar.html', {
        'cfg': cfg, 'menu': cfg['menu'], 'obj': obj, 'relacionados': relacionados,
        'bloqueado': bloqueado, 'proximo': request.GET.get('proximo', ''),
    })
