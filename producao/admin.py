from django.contrib import admin

from .models import ConfigEstoque, EstoqueMinimo, Impressao, Kit, KitPeca, MovimentoEstoque


@admin.register(Impressao)
class ImpressaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'produto', 'descricao', 'impressora', 'qnt', 'qnt_boas', 'status', 'criado_em', 'concluido_em')
    list_filter = ('status', 'impressora')
    search_fields = ('produto__product', 'descricao')
    raw_id_fields = ('item_pedido',)


@admin.register(MovimentoEstoque)
class MovimentoEstoqueAdmin(admin.ModelAdmin):
    list_display = ('data', 'produto', 'tipo', 'qnt', 'observacao', 'usuario')
    list_filter = ('tipo', 'data')
    search_fields = ('produto__product', 'observacao')
    raw_id_fields = ('impressao', 'venda_feira', 'venda_interna')


admin.site.register(EstoqueMinimo)
admin.site.register(ConfigEstoque)


class KitPecaInline(admin.TabularInline):
    model = KitPeca
    extra = 1


@admin.register(Kit)
class KitAdmin(admin.ModelAdmin):
    list_display = ('produto', 'embalagem', 'outros', 'minutos_montagem')
    inlines = [KitPecaInline]
