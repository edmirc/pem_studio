from django.contrib import admin
from .models import Precificacao, Feiras, VendasFeiras
from django.db.models import Sum

@admin.register(Precificacao)
class PrecificacaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'custo', 'sugerido', 'vanda',)
    search_fields = ('product', 'product__category') # Permite buscar pelo produto se houver suporte
    list_filter = ('product', 'product__category')
    readonly_fields = ('custo', 'sugerido',)

@admin.register(Feiras)
class FeirasAdmin(admin.ModelAdmin):
    list_display = ('id', 'nomeFeira', 'product', 'qnt', 'value', 'pagment')
    list_filter = ('nomeFeira__date', 'pagment')
    search_fields = ('product__name', 'nomeFeira__name') # Ajuste os campos de texto conforme os models externos se necessário

@admin.register(VendasFeiras)
class VendasFeirasAdmin(admin.ModelAdmin):
    list_display = ('feira', 'total_debito', 'total_credito', 'total_pix', 'total_dinheiro', 'total_total')
    list_filter = ('feira__date', )
    search_fields = ('feira__date',)
    readonly_fields = ('total_debito', 'total_credito', 'total_pix', 'total_dinheiro', 'total_total',)
