"""Ao salvar uma compra, as contas a pagar dela são (re)geradas automaticamente."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cadastro.models import CadFeiras
from vendas.models import Feiras, VendasInternas

from .models import CompraFilamento, CompraInsumo, Compras
from .servicos import gerar_da_compra, gerar_da_feira, gerar_da_venda_interna


@receiver(post_save, sender=CompraFilamento)
@receiver(post_save, sender=CompraInsumo)
@receiver(post_save, sender=Compras)
def _compra_salva(sender, instance, raw=False, **kwargs):
    if not raw:
        gerar_da_compra(instance)


# Vendas: cada venda vira recebimento no financeiro (fluxo de caixa automático)
@receiver(post_save, sender=Feiras)
@receiver(post_delete, sender=Feiras)
def _venda_feira(sender, instance, raw=False, **kwargs):
    if raw:
        return
    feira = CadFeiras.objects.filter(pk=instance.nomeFeira_id).first()
    if feira:
        gerar_da_feira(feira)


@receiver(post_save, sender=CadFeiras)
def _feira_salva(sender, instance, raw=False, created=False, **kwargs):
    if not raw and not created:
        gerar_da_feira(instance)  # data ou nome da feira mudou


@receiver(post_save, sender=VendasInternas)
def _venda_interna(sender, instance, raw=False, **kwargs):
    if not raw:
        gerar_da_venda_interna(instance)
