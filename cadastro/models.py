from django.db import models

class Category(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name="ID")
    category = models.CharField(max_length=150, verbose_name= "Categoria", unique=True)

    def __str__(self):
         return self.category

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ("category",)


class Product(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name='ID', unique=True)
    product = models.CharField(max_length=200, verbose_name='Produto', unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name='Categoria')

    def __str__(self):
        return self.product

    class Meta:
        verbose_name="Produtos"
        verbose_name_plural = "Produtos"
        ordering = ("product",)

class FilamentBrand(models.Model):
    id = models.BigAutoField(primary_key= True, verbose_name="ID")
    name = models.CharField(max_length=150, verbose_name="Nome", unique=True)

    def __str__(self):
        return self.name
    

    class Meta:
            verbose_name="Marca de filamento"
            verbose_name_plural = "Marcas de filamento"
            ordering = ('name',)


class FilametType(models.Model):
     id = models.BigAutoField(primary_key=True, verbose_name="ID")
     type = models.CharField(max_length=50, unique=True, verbose_name='Tipo')

     def __str__(self):
        return self.type
    

     class Meta:
        verbose_name = "Tipo de filamento"
        verbose_name_plural ="Tipos de filamento"


class Filment(models.Model):
     id = models.BigAutoField(primary_key=True, verbose_name="ID")
     name = models.CharField(max_length=200, verbose_name="Filamento")
     color = models.CharField(max_length=100, verbose_name="Cor")
     filamentType = models.ForeignKey(FilametType, on_delete=models.CASCADE, verbose_name="Tipo")
     filamentBrand = models.ForeignKey(FilamentBrand, on_delete=models.CASCADE, verbose_name="Marca")

     class Meta:
          verbose_name = "FilamentoS"
          verbose_name_plural ="Filamentos"


class CadFeiras(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    date = models.DateField(verbose_name="data")
    name = models.CharField(max_length=200, verbose_name="Nome")
    local = models.CharField(max_length=200, verbose_name="Local")

    def __str__(self):
        return str(self.date)

    class Meta:
        verbose_name = 'Cadasro de feiras'
        verbose_name_plural = 'Cadastro de feiras'
        ordering = ('name', )
