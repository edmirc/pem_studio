from django.db import models
from cadastro.models import Contas

class Compras(models.Model):
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    date = models.DateField(verbose_name='Data')
    saida = models.CharField(max_length=250, verbose_name='Saída')
    pagamento = models.ForeignKey(Contas, on_delete=models.CASCADE, verbose_name='Forma de pagamento')
    parcela = models.CharField(max_length=100, verbose_name='Parcelas') 
    fornecedor = models.CharField(max_length=250, verbose_name='Fornecedor')
 

    class Meta:
        verbose_name = 'Saída'
        verbose_name_plural = "Saídas"
        ordering = ('date',)

        
    def __str__(self):
        return self.saida

