from django.db import models
from cadastro.models import Product, CadFeiras
from decimal import Decimal
from django.db.models import Sum


class Precificacao(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name="ID")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Produto", unique=True)
    impressao = models.IntegerField(verbose_name="Hora de impressão")
    filament = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Filamento")
    embalagem = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Embalagem", null=True, blank=True)
    acessorios = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Acessórios", null=True, blank=True)
    custo  = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço de custo", null=True)
    sugerido = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="valor sugerido", null= True)
    vanda = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Venda", null= True)

    def save(self, *args, **kwargs):
        hrImpressão = Decimal('2.0')
        self.embalagem =  self.embalagem if self.embalagem is not None else Decimal('0.00')
        self.acessorios = self.acessorios if self.acessorios is not None else Decimal('0.00')
        self.custo = (self.impressao * hrImpressão) + self.filament + self.embalagem + self.acessorios
        self.sugerido = Decimal(self.custo * 2)
        super().save(*args, **kwargs)


    class Meta:
        verbose_name = "Precificação" 
        verbose_name_plural = "Precificação"
        ordering = ('product',)
        
    def __str__(self):
        return str(self.product)

class FormaPagamento(models.TextChoices):
    CREDITO = 'CREDITO', 'Crédito'
    DEBITO = 'DEBITO', 'Débito'
    DINHEIRO = 'DINHEIRO', 'Dinheiro'
    PIX = 'PIX', 'Pix'
    

class Feiras(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name="ID")
    qnt = models.IntegerField(verbose_name="Quantidade")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Produto")
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor")
    pagment = models.CharField(max_length=20, choices=FormaPagamento.choices, verbose_name='Forma de pagamento')
    nomeFeira = models.ForeignKey(CadFeiras, on_delete=models.CASCADE, verbose_name="Feira")    
    
    def __str__(self):
        return str(self.nomeFeira)

    def save(self, *args, **kwargs):
        if self.pagment == "DEBITO":
            self.value = self.value - (self.value * Decimal("0.0089"))
        return super().save(*args, **kwargs)
            

    def sumTotais(self, feira):
        total_geral = Feiras.objects.filter(nomeFeira=feira)
        pagamentos = {"DEBITO": Decimal(0.00), "CREDITO": Decimal(0.00), "PIX": Decimal(0.00), "DINHEIRO": Decimal(0.00), "total": Decimal(0.00)}
        for i in total_geral:
            pagamentos['total'] = Decimal(pagamentos["total"]) + Decimal(i.value)
            pagamentos[i.pagment] = Decimal(pagamentos[i.pagment]) + Decimal(i.value)
        return pagamentos


    class Meta:
        verbose_name = "Venda de feiras" 
        verbose_name_plural = "Venda de Feiras"
        ordering = ('nomeFeira', 'product')


class VendasFeiras(models.Model):
    feira = models.ForeignKey(CadFeiras, verbose_name="Feira", on_delete=models.CASCADE, primary_key=True)
    total_debito = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Débito', blank=True, null=True)
    total_credito = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Crédito', blank=True, null=True)
    total_pix = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='PIX', blank=True, null=True)
    total_dinheiro = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Dinheiro', blank=True, null=True)
    total_total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Total', blank=True, null=True)

    def __str__(self):
        return str(self.feira)

    def save(self, *args, **kwargs):
        dict = Feiras().sumTotais(self.feira)
        self.total_debito = dict['DEBITO']
        self.total_credito = dict['CREDITO']
        self.total_pix = dict['PIX']
        self.total_dinheiro = dict['DINHEIRO']
        self.total_total = dict['total']
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name="Total de Vendas Feiras"
        verbose_name_plural="Total de Vendas Feiras"
        ordering = ('feira',
    )


    class VendasInternas(models.Model):
        id = models.BigAutoField(primary_key=True, verbose_name="ID")
        date = models.DateField(verbose_name='Data')
        product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Produto')
        valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor')
        client = models.ForeignKey()
        pagment = models.CharField(max_length=50, choices=FormaPagamento, verbose_name='Formas de pagamento')
        

    
