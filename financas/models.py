from django.db import models
from cadastro.models import Contas, Filment, Insumo


class Compras(models.Model):
    """Outras saídas / despesas gerais."""
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    date = models.DateField(verbose_name='Data')
    saida = models.CharField(max_length=250, verbose_name='Saída')
    pagamento = models.ForeignKey(Contas, on_delete=models.CASCADE, verbose_name='Forma de pagamento')
    parcela = models.CharField(max_length=100, verbose_name='Parcelas')
    fornecedor = models.CharField(max_length=250, verbose_name='Fornecedor')
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor', null=True, blank=True)

    class Meta:
        verbose_name = 'Saída'
        verbose_name_plural = "Saídas"
        ordering = ('date',)

    def __str__(self):
        return self.saida


class CompraFilamento(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    date = models.DateField(verbose_name='Data')
    filamento = models.ForeignKey(Filment, on_delete=models.PROTECT, verbose_name='Filamento')
    qnt = models.PositiveIntegerField(default=1, verbose_name='Qtd. de rolos')
    peso = models.PositiveIntegerField(default=1000, verbose_name='Peso por rolo (g)')
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor total')
    fornecedor = models.CharField(max_length=250, verbose_name='Fornecedor', blank=True)
    pagamento = models.ForeignKey(Contas, on_delete=models.PROTECT, verbose_name='Pagamento', null=True, blank=True)
    parcelas = models.PositiveIntegerField(default=1, verbose_name='Parcelas')

    @property
    def preco_kg(self):
        total_g = self.qnt * self.peso
        return (self.valor * 1000 / total_g) if total_g else None

    def __str__(self):
        return f'{self.date:%d/%m/%Y} - {self.filamento}'

    class Meta:
        verbose_name = 'Compra de filamento'
        verbose_name_plural = 'Compras de filamento'
        ordering = ('-date', '-id')


class CompraInsumo(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    date = models.DateField(verbose_name='Data')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, verbose_name='Insumo')
    qnt = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name='Quantidade')
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor total')
    fornecedor = models.CharField(max_length=250, verbose_name='Fornecedor', blank=True)
    pagamento = models.ForeignKey(Contas, on_delete=models.PROTECT, verbose_name='Pagamento', null=True, blank=True)
    parcelas = models.PositiveIntegerField(default=1, verbose_name='Parcelas')

    @property
    def preco_unitario(self):
        return (self.valor / self.qnt) if self.qnt else None

    def __str__(self):
        return f'{self.date:%d/%m/%Y} - {self.insumo}'

    class Meta:
        verbose_name = 'Compra de insumo'
        verbose_name_plural = 'Compras de insumos'
        ordering = ('-date', '-id')
