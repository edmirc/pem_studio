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


# ===========================================================================
# Contas a pagar e a receber
# ===========================================================================
from django.utils import timezone  # noqa: E402

from cadastro.models import CadClientes, CadFeiras  # noqa: E402
from vendas.models import FormaPagamento, VendasInternas  # noqa: E402


class Categoria(models.TextChoices):
    FILAMENTO = 'FILAMENTO', 'Filamento'
    INSUMOS = 'INSUMOS', 'Insumos'
    CONTAS_CASA = 'CONTAS', 'Água, energia, internet e telefone'
    ASSINATURA = 'ASSINATURA', 'Assinaturas e programas'
    IMPOSTO = 'IMPOSTO', 'Impostos (DAS)'
    FEIRA = 'FEIRA', 'Feiras e eventos'
    EQUIPAMENTO = 'EQUIPAMENTO', 'Equipamentos e manutenção'
    RETIRADA = 'RETIRADA', 'Retirada (pró-labore)'
    VENDA = 'VENDA', 'Venda / encomenda'
    OUTROS = 'OUTROS', 'Outros'


class TipoLancamento(models.TextChoices):
    PAGAR = 'PAGAR', 'A pagar'
    RECEBER = 'RECEBER', 'A receber'


class DespesaFixa(models.Model):
    descricao = models.CharField('Descrição', max_length=150)
    categoria = models.CharField('Categoria', max_length=12, choices=Categoria.choices, default=Categoria.CONTAS_CASA)
    valor = models.DecimalField('Valor por mês (R$)', max_digits=10, decimal_places=2, null=True, blank=True,
                                help_text='Para contas que variam (energia, água), use a média; '
                                          'ajuste o valor de cada mês quando a conta chegar.')
    dia_vencimento = models.PositiveSmallIntegerField('Dia de vencimento', default=10)
    conta = models.ForeignKey(Contas, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Pago com',
                              help_text='Se for no cartão de crédito, entra na fatura dele.')
    ativa = models.BooleanField('Ativa', default=True)
    observacao = models.CharField('Observação', max_length=250, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Despesa fixa'
        verbose_name_plural = 'Despesas fixas'
        ordering = ('dia_vencimento', 'descricao')

    def __str__(self):
        return self.descricao


class Lancamento(models.Model):
    tipo = models.CharField('Tipo', max_length=8, choices=TipoLancamento.choices, default=TipoLancamento.PAGAR)
    descricao = models.CharField('Descrição', max_length=200)
    categoria = models.CharField('Categoria', max_length=12, choices=Categoria.choices, default=Categoria.OUTROS)
    valor = models.DecimalField('Valor (R$)', max_digits=10, decimal_places=2)
    vencimento = models.DateField('Vencimento')
    pago_em = models.DateField('Pago / recebido em', null=True, blank=True)
    conta = models.ForeignKey(Contas, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Conta / cartão')
    cliente = models.ForeignKey(CadClientes, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cliente')
    parcela = models.PositiveSmallIntegerField(null=True, blank=True)
    parcelas = models.PositiveSmallIntegerField(null=True, blank=True)
    observacao = models.CharField('Observação', max_length=250, blank=True)
    # de onde veio (lançamentos automáticos)
    compra_filamento = models.ForeignKey(CompraFilamento, on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    compra_insumo = models.ForeignKey(CompraInsumo, on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    despesa = models.ForeignKey(Compras, on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    recorrente = models.ForeignKey(DespesaFixa, on_delete=models.SET_NULL, null=True, blank=True, related_name='lancamentos')
    # recebimentos automáticos das vendas
    feira = models.ForeignKey(CadFeiras, on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    venda_interna = models.ForeignKey(VendasInternas, on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    forma = models.CharField('Forma de pagamento', max_length=20, choices=FormaPagamento.choices, blank=True)
    pedido = models.ForeignKey('encomendas.Pedido', on_delete=models.CASCADE, null=True, blank=True, related_name='lancamentos')
    competencia = models.DateField('Mês de referência', null=True, blank=True)
    baixa_automatica = models.BooleanField(default=False, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Contas a pagar e a receber'
        ordering = ('vencimento', 'id')
        indexes = [models.Index(fields=['tipo', 'pago_em', 'vencimento'])]

    def __str__(self):
        return f'{self.descricao} ({self.vencimento:%d/%m/%Y})'

    @property
    def automatico(self):
        return bool(self.compra_filamento_id or self.compra_insumo_id or self.despesa_id or self.da_venda)

    @property
    def da_venda(self):
        return bool(self.feira_id or self.venda_interna_id or self.pedido_id)

    @property
    def em_fatura(self):
        return bool(self.conta_id and self.conta.e_credito and self.tipo == TipoLancamento.PAGAR)

    @property
    def situacao(self):
        if self.pago_em:
            return 'pago'
        hoje = timezone.localdate()
        if self.vencimento < hoje:
            return 'atrasado'
        if self.vencimento == hoje:
            return 'hoje'
        return 'aberto'

    @property
    def nome_parcela(self):
        return f'{self.parcela}/{self.parcelas}' if self.parcelas and self.parcelas > 1 else ''


class SaldoCaixa(models.Model):
    """Saldo informado (soma das contas e dinheiro em caixa) — ponto de partida do fluxo de caixa."""
    data = models.DateField('Data', default=timezone.localdate)
    valor = models.DecimalField('Saldo (R$)', max_digits=12, decimal_places=2)
    observacao = models.CharField('Observação', max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-data', '-id')
        verbose_name = 'Saldo informado'
        verbose_name_plural = 'Saldos informados'
