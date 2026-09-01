from django.contrib import admin
from .models import Category, Product, FilamentBrand, FilametType, Filment, CadFeiras, CadClientes


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "category")
    search_fields = ("category",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "category")
    search_fields = ("product",)
    list_filter = ("category",)


@admin.register(FilamentBrand)
class FilamentBrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(FilametType)
class FilametTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "type")
    search_fields = ("type",)


@admin.register(Filment)
class FilmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "color",
        "filamentType",
        "filamentBrand",
    )
    search_fields = ("name", "color")
    list_filter = ("filamentType", "filamentBrand")


@admin.register(CadFeiras)
class CadFeirasAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "name", 'local')
    search_fields = ("name", "date")


@admin.register(CadClientes)
class CadClientesAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "cpf", "telefone", "endereco")
    search_fields = ("name",)
