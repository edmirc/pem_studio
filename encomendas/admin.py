from django.contrib import admin

from .models import Configuracao, Impressora, ItemOrcamento, ItemPedido, Orcamento, Pedido


class ItemOrcamentoInline(admin.TabularInline):
    model = ItemOrcamento
    extra = 0


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'data', 'nome_cliente', 'cliente', 'status')
    list_filter = ('status',)
    inlines = [ItemOrcamentoInline]


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'data', 'cliente', 'prazo', 'status', 'sinal_recebido')
    list_filter = ('status',)
    inlines = [ItemPedidoInline]


admin.site.register(Impressora)
admin.site.register(Configuracao)
