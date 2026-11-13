from django.contrib import admin
from .models import Compras, CompraFilamento, CompraInsumo


@admin.register(Compras)
class ComprasAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'saida', 'valor', 'fornecedor', 'pagamento', 'parcela')
    list_filter = ('date', 'pagamento')
    search_fields = ('saida', 'fornecedor')


@admin.register(CompraFilamento)
class CompraFilamentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'filamento', 'qnt', 'peso', 'valor', 'fornecedor', 'pagamento', 'parcelas')
    list_filter = ('date', 'filamento__filamentBrand', 'filamento__filamentType')
    search_fields = ('filamento__name', 'filamento__color', 'fornecedor')


@admin.register(CompraInsumo)
class CompraInsumoAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'insumo', 'qnt', 'valor', 'fornecedor', 'pagamento', 'parcelas')
    list_filter = ('date', 'insumo')
    search_fields = ('insumo__name', 'fornecedor')
