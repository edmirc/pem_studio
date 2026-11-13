from django.utils import timezone
from datetime import date
from decimal import Decimal


MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
         'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
MESES_CURTOS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def brl(valor):
    """Formata um número como moeda brasileira: R$ 1.234,56"""
    if valor is None or valor == '':
        return '—'
    valor = Decimal(valor).quantize(Decimal('0.01'))
    sinal = '-' if valor < 0 else ''
    inteiro, centavos = f'{abs(valor):.2f}'.split('.')
    inteiro = f'{int(inteiro):,}'.replace(',', '.')
    return f'{sinal}R$ {inteiro},{centavos}'


def num(valor, casas=0):
    if valor is None:
        return '—'
    texto = f'{Decimal(valor):,.{casas}f}'
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(d):
    return d.strftime('%d/%m/%Y') if d else '—'


def ler_mes(texto, padrao=None):
    """Recebe 'AAAA-MM' e devolve (ano, mes). Usa o mês atual se inválido."""
    hoje = padrao or timezone.localdate()
    try:
        ano, mes = (int(p) for p in (texto or '').split('-')[:2])
        if 1 <= mes <= 12 and 2000 <= ano <= 2100:
            return ano, mes
    except (ValueError, TypeError):
        pass
    return hoje.year, hoje.month


def mes_anterior(ano, mes):
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def mes_seguinte(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def nome_mes(ano, mes):
    return f'{MESES[mes - 1]} de {ano}'
