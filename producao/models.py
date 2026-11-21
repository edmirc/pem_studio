"""Impressão (fila das impressoras) e estoque de peças prontas."""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from cadastro.models import Product


class ConfigEstoque(models.Model):
    """Um registro só. Vendas anteriores a `inicio` não mexem no estoque."""
    inicio = models.DateField('O estoque conta vendas a partir de', default=timezone.localdate)

    class Meta:
        verbose_name = 'Configuração do estoque'
        verbose_name_plural = 'Configuração do estoque'

    def __str__(self):
        return f'Estoque desde {self.inicio:%d/%m/%Y}'

    @classmethod
    def atual(cls):
        return cls.objects.order_by('pk').first() or cls.objects.create()


class EstoqueMinimo(models.Model):
    produto = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='estoque_minimo', verbose_name='Produto')
    minimo = models.PositiveIntegerField('Estoque mínimo', default=0)

    class Meta:
        verbose_name = 'Estoque mínimo'
        verbose_name_plural = 'Estoques mínimos'

    def __str__(self):
        return f'{self.produto}: {self.minimo}'


# ---------------------------------------------------------------------------
# Impressões
# ---------------------------------------------------------------------------
class StatusImpressao(models.TextChoices):
    FILA = 'FILA', 'Na fila'
    IMPRIMINDO = 'IMPRIMINDO', 'Imprimindo'
    IMPRESSO = 'IMPRESSO', 'Impresso'
    PRONTA = 'PRONTA', 'Pronta'
    FALHOU = 'FALHOU', 'Falhou'
    CANCELADA = 'CANCELADA', 'Cancelada'


EM_ANDAMENTO = [StatusImpressao.FILA, StatusImpressao.IMPRIMINDO, StatusImpressao.IMPRESSO]


class Impressao(models.Model):
    produto = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='impressoes', verbose_name='Produto')
    item_pedido = models.ForeignKey('encomendas.ItemPedido', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='impressoes', verbose_name='Item do pedido')
    descricao = models.CharField('Descrição', max_length=200, blank=True)
    impressora = models.ForeignKey('encomendas.Impressora', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='impressoes', verbose_name='Impressora')
    qnt = models.PositiveIntegerField('Peças nesta impressão', default=1)
    qnt_boas = models.PositiveIntegerField('Peças boas', null=True, blank=True)
    horas = models.DecimalField('Tempo estimado (h)', max_digits=7, decimal_places=2, default=Decimal('0'))
    gramas = models.DecimalField('Filamento (g)', max_digits=9, decimal_places=1, null=True, blank=True)
    calculo = models.JSONField('Cálculo', null=True, blank=True)
    status = models.CharField('Etapa', max_length=12, choices=StatusImpressao.choices, default=StatusImpressao.FILA)
    observacao = models.CharField('Observação', max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    iniciado_em = models.DateTimeField('Começou em', null=True, blank=True)
    impresso_em = models.DateTimeField('Terminou de imprimir em', null=True, blank=True)
    concluido_em = models.DateTimeField('Concluída em', null=True, blank=True)

    class Meta:
        verbose_name = 'Impressão'
        verbose_name_plural = 'Impressões'
        ordering = ('criado_em', 'id')

    def __str__(self):
        return f'{self.numero} - {self.nome}'

    @property
    def numero(self):
        return f'IMP-{self.pk:04d}' if self.pk else 'IMP-nova'

    @property
    def nome(self):
        if self.produto_id:
            return self.produto.product
        if self.descricao:
            return self.descricao
        return self.item_pedido.nome if self.item_pedido_id else 'Peça'

    @property
    def pedido(self):
        return self.item_pedido.pedido if self.item_pedido_id else None

    @property
    def vai_para_estoque(self):
        return bool(self.produto_id) and not self.produto_generico

    @property
    def produto_generico(self):
        return bool(self.produto_id) and self.produto.category.category == 'Encomendas'

    @property
    def tempo_texto(self):
        if not self.horas:
            return ''
        minutos = int(round(float(self.horas) * 60))
        h, m = divmod(minutos, 60)
        return f'{h}h{m:02d}' if h else f'{m} min'

    @property
    def previsao_fim(self):
        if self.iniciado_em and self.horas:
            return self.iniciado_em + timedelta(minutes=float(self.horas) * 60)
        return None

    @property
    def progresso(self):
        """0–100 pelo tempo decorrido (só enquanto imprime)."""
        fim = self.previsao_fim
        if self.status != StatusImpressao.IMPRIMINDO or not fim:
            return None
        total = (fim - self.iniciado_em).total_seconds()
        feito = (timezone.now() - self.iniciado_em).total_seconds()
        return max(0, min(100, int(feito * 100 / total))) if total > 0 else 100

    @property
    def atrasada(self):
        fim = self.previsao_fim
        return bool(self.status == StatusImpressao.IMPRIMINDO and fim and timezone.now() > fim)

    @property
    def perdidas(self):
        if self.status == StatusImpressao.FALHOU:
            return self.qnt
        if self.status == StatusImpressao.PRONTA and self.qnt_boas is not None:
            return max(0, self.qnt - self.qnt_boas)
        return 0


# ---------------------------------------------------------------------------
# Estoque (extrato de entradas e saídas)
# ---------------------------------------------------------------------------
class TipoMovimento(models.TextChoices):
    IMPRESSAO = 'IMPRESSAO', 'Impressão'
    VENDA_FEIRA = 'VENDA_FEIRA', 'Venda na feira'
    VENDA_DIRETA = 'VENDA_DIRETA', 'Venda direta'
    ENTRADA = 'ENTRADA', 'Entrada manual'
    SAIDA = 'SAIDA', 'Saída manual'
    PERDA = 'PERDA', 'Perda / quebra'
    CONTAGEM = 'CONTAGEM', 'Contagem'


class MovimentoEstoque(models.Model):
    produto = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movimentos', verbose_name='Produto')
    data = models.DateField('Data', default=timezone.localdate)
    tipo = models.CharField('Tipo', max_length=14, choices=TipoMovimento.choices)
    qnt = models.IntegerField('Quantidade', help_text='Positivo entra, negativo sai.')
    impressao = models.OneToOneField(Impressao, on_delete=models.CASCADE, null=True, blank=True, related_name='movimento')
    # ForeignKey: a venda de um kit gera uma saída para cada peça
    venda_feira = models.ForeignKey('vendas.Feiras', on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='movimentos_estoque')
    venda_interna = models.ForeignKey('vendas.VendasInternas', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='movimentos_estoque')
    observacao = models.CharField('Observação', max_length=300, blank=True)
    usuario = models.CharField(max_length=150, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Movimento de estoque'
        verbose_name_plural = 'Movimentos de estoque'
        ordering = ('-data', '-id')

    def __str__(self):
        return f'{self.data:%d/%m/%Y} {self.produto} {self.qnt:+d}'

    @property
    def automatico(self):
        return bool(self.impressao_id or self.venda_feira_id or self.venda_interna_id)


# ---------------------------------------------------------------------------
# Kits: um produto vendido como conjunto de peças. Não tem estoque próprio:
# vender um kit tira do estoque cada peça.
# ---------------------------------------------------------------------------
class Kit(models.Model):
    produto = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='kit', verbose_name='Produto')
    embalagem = models.DecimalField('Embalagem do kit (R$)', max_digits=8, decimal_places=2, default=Decimal('0'))
    outros = models.DecimalField('Outros insumos (R$)', max_digits=8, decimal_places=2, default=Decimal('0'),
                                 help_text='Fita, laço, etiqueta, cartão…')
    minutos_montagem = models.PositiveIntegerField('Tempo de montagem (min)', default=0)
    observacao = models.CharField('Observação', max_length=300, blank=True)

    class Meta:
        verbose_name = 'Kit'
        verbose_name_plural = 'Kits'
        ordering = ('produto__product',)

    def __str__(self):
        return f'Kit {self.produto}'


class KitPeca(models.Model):
    kit = models.ForeignKey(Kit, on_delete=models.CASCADE, related_name='pecas')
    peca = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='em_kits', verbose_name='Peça')
    qnt = models.PositiveIntegerField('Quantidade', default=1)

    class Meta:
        verbose_name = 'Peça do kit'
        verbose_name_plural = 'Peças do kit'
        ordering = ('id',)
        constraints = [models.UniqueConstraint(fields=['kit', 'peca'], name='kit_peca_unica')]

    def __str__(self):
        return f'{self.qnt}× {self.peca}'
