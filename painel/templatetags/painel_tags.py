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
