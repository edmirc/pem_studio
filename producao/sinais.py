"""Vendeu, saiu do estoque: cada venda de feira ou direta gera (ou corrige) a saída."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from cadastro.models import CadFeiras
from vendas.models import Feiras, VendasInternas

from . import servicos


@receiver(post_save, sender=Feiras)
def _venda_feira(sender, instance, raw=False, **kwargs):
    if not raw:
        servicos.sincronizar_venda_feira(instance)


@receiver(post_save, sender=VendasInternas)
def _venda_interna(sender, instance, raw=False, **kwargs):
    if not raw:
        servicos.sincronizar_venda_interna(instance)


@receiver(post_save, sender=CadFeiras)
def _feira(sender, instance, raw=False, created=False, **kwargs):
    if raw or created:
        return
    for v in Feiras.objects.filter(nomeFeira=instance).select_related('product__category'):
        servicos.sincronizar_venda_feira(v)  # a data da feira mudou
