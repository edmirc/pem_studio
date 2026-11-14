"""Ao salvar uma compra, as contas a pagar dela são (re)geradas automaticamente."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CompraFilamento, CompraInsumo, Compras
from .servicos import gerar_da_compra


@receiver(post_save, sender=CompraFilamento)
@receiver(post_save, sender=CompraInsumo)
@receiver(post_save, sender=Compras)
def _compra_salva(sender, instance, raw=False, **kwargs):
    if not raw:
        gerar_da_compra(instance)
