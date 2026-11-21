from django import template

from painel.utils import brl as _brl, num as _num, data_br as _data_br

register = template.Library()


@register.filter
def brl(valor):
    return _brl(valor)


@register.filter
def num(valor, casas=0):
    return _num(valor, casas)


@register.filter
def data_br(valor):
    return _data_br(valor)


@register.filter
def pct(parte, total):
    try:
        if not total:
            return 0
        return round(float(parte) * 100 / float(total), 1)
    except (TypeError, ValueError):
        return 0


@register.simple_tag(takes_context=True)
def ativo(context, *nomes):
    """Retorna 'ativo' se a página atual pertence a algum dos nomes de menu."""
    atual = context.get('menu', '')
    return 'ativo' if atual in nomes else ''


@register.filter
def get_campo(form, nome):
    return form[nome]


@register.filter
def get_item(d, chave):
    try:
        return d.get(chave)
    except AttributeError:
        return None


@register.inclusion_tag('painel/parciais/arquivo3d.html')
def arquivo3d(produto, impressora=None, compacto=False):
    """Caminho do arquivo 3D do produto com botões para abrir no Windows."""
    from painel.produtos import links_arquivo
    caminho = getattr(produto, 'arquivo', '') if produto else ''
    return {'arq': links_arquivo(caminho, impressora), 'compacto': compacto}


@register.filter
def com_foto(produto, nome=None):
    """Nome do produto com a miniatura da foto ao lado.

    Aceita um Product, um dicionário com 'produto' e 'mini' (relatórios) ou None (usa só o `nome`).
    Uso: {{ venda.product|com_foto }}   {{ item.produto|com_foto:item.nome }}   {{ linha|com_foto }}
    """
    from django.utils.html import format_html
    if isinstance(produto, dict):
        texto, url = produto.get('produto', ''), produto.get('mini', '')
    elif produto is None or produto == '':
        return nome or ''
    else:
        texto = nome if nome not in (None, '') else getattr(produto, 'product', str(produto))
        url = produto.url_mini if getattr(produto, 'miniatura', None) or getattr(produto, 'imagem', None) else ''
    if url:
        return format_html('<span class="com-foto"><img src="{}" alt="" loading="lazy"><span>{}</span></span>', url, texto)
    return format_html('<span class="com-foto"><span class="sem-foto" aria-hidden="true"></span><span>{}</span></span>', texto)
