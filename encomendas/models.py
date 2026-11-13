from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from cadastro.models import CadClientes, Product
from vendas.models import FormaPagamento

D0 = Decimal('0')


def _dec(v):
    return Decimal(v) if v is not None else D0


# ---------------------------------------------------------------------------
# Configurações gerais (um registro só)
# ---------------------------------------------------------------------------
class Configuracao(models.Model):
    nome_empresa = models.CharField('Nome da empresa', max_length=100, default='PEM Studio')
    telefone_empresa = models.CharField('Telefone / WhatsApp', max_length=30, blank=True)
    preco_kwh = models.DecimalField('Preço do kWh (R$)', max_digits=6, decimal_places=3, default=Decimal('0.950'))
    valor_hora_trabalho = models.DecimalField('Valor da sua hora de trabalho (R$)', max_digits=8, decimal_places=2, default=Decimal('20.00'),
                                              help_text='Usado no acabamento, pintura e montagem.')
    taxa_falha = models.DecimalField('Taxa de falha (%)', max_digits=5, decimal_places=2, default=Decimal('10.00'),
                                     help_text='Acrescentado ao custo de máquina e filamento para cobrir impressões perdidas.')
    lucro_padrao = models.DecimalField('Lucro padrão sobre o custo (%)', max_digits=6, decimal_places=2, default=Decimal('100.00'),
                                       help_text='100% = preço é o dobro do custo (como na precificação antiga).')
    custo_kg_padrao = models.DecimalField('Custo do filamento por kg, se não houver compras (R$)', max_digits=8, decimal_places=2,
                                          default=Decimal('100.00'))
    sinal_percentual = models.DecimalField('Sinal padrão (%)', max_digits=5, decimal_places=2, default=Decimal('50.00'))
    validade_dias = models.PositiveIntegerField('Validade do orçamento (dias)', default=7)
    prazo_dias = models.PositiveIntegerField('Prazo de produção padrão (dias)', default=7)
    taxa_debito = models.DecimalField('Taxa débito (%)', max_digits=5, decimal_places=2, default=Decimal('0.89'))
    taxa_credito_1x = models.DecimalField('Crédito 1x (%)', max_digits=5, decimal_places=2, default=Decimal('3.15'))
    taxa_credito_2x = models.DecimalField('Crédito 2x (%)', max_digits=5, decimal_places=2, default=Decimal('5.39'))
    taxa_credito_3x = models.DecimalField('Crédito 3x (%)', max_digits=5, decimal_places=2, default=Decimal('6.12'))
    taxa_credito_4x = models.DecimalField('Crédito 4x (%)', max_digits=5, decimal_places=2, default=Decimal('6.85'))
    taxa_credito_5x = models.DecimalField('Crédito 5x (%)', max_digits=5, decimal_places=2, default=Decimal('7.57'))
    taxa_credito_6x = models.DecimalField('Crédito 6x (%)', max_digits=5, decimal_places=2, default=Decimal('8.28'))

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return 'Configurações'

    @classmethod
    def atual(cls):
        obj = cls.objects.order_by('pk').first()
        return obj or cls.objects.create()

    def taxas(self):
        """[(rótulo, parcelas, taxa%)] na ordem de exibição."""
        t = [('Débito', 1, self.taxa_debito)]
        for n in range(1, 7):
            t.append((f'Crédito {n}x', n, getattr(self, f'taxa_credito_{n}x')))
        return t

    def tabela_cartao(self, valor):
        """Preço a cobrar em cada forma para receber `valor` líquido."""
        valor = _dec(valor)
        linhas = [{'nome': 'Pix / dinheiro', 'parcelas': 1, 'taxa': D0, 'total': valor, 'parcela': valor}]
        for nome, n, taxa in self.taxas():
            total = (valor / (1 - _dec(taxa) / 100)).quantize(Decimal('0.01')) if taxa < 100 else valor
            linhas.append({'nome': nome, 'parcelas': n, 'taxa': taxa, 'total': total,
                           'parcela': (total / n).quantize(Decimal('0.01'))})
        return linhas


# ---------------------------------------------------------------------------
# Impressoras
# ---------------------------------------------------------------------------
class Impressora(models.Model):
    nome = models.CharField('Nome', max_length=60, help_text='Ex.: K2 Pro 1')
    modelo = models.CharField('Modelo', max_length=80, blank=True)
    potencia_media_w = models.PositiveIntegerField('Consumo médio imprimindo (W)', default=150)
    custo_hora = models.DecimalField('Custo por hora (R$)', max_digits=6, decimal_places=2, default=Decimal('2.00'),
                                     help_text='Energia + desgaste/manutenção da máquina.')
    ativa = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Impressora'
        verbose_name_plural = 'Impressoras'
        ordering = ('nome',)

    def __str__(self):
        return self.nome

    def energia_hora(self, preco_kwh):
        return (Decimal(self.potencia_media_w) / 1000 * _dec(preco_kwh)).quantize(Decimal('0.01'))


# ---------------------------------------------------------------------------
# Orçamentos
# ---------------------------------------------------------------------------
class StatusOrcamento(models.TextChoices):
    RASCUNHO = 'RASCUNHO', 'Rascunho'
    ENVIADO = 'ENVIADO', 'Enviado'
    APROVADO = 'APROVADO', 'Aprovado'
    RECUSADO = 'RECUSADO', 'Recusado'


class _ComItens(models.Model):
    desconto = models.DecimalField('Desconto (R$)', max_digits=10, decimal_places=2, default=D0)
    frete = models.DecimalField('Frete / entrega (R$)', max_digits=10, decimal_places=2, default=D0)
    observacoes = models.TextField('Observações', blank=True)

    class Meta:
        abstract = True

    @property
    def subtotal(self):
        return sum((i.total for i in self.itens.all()), D0)

    @property
    def total(self):
        return max(D0, self.subtotal - _dec(self.desconto) + _dec(self.frete))


class Orcamento(_ComItens):
    solicitacao = models.ForeignKey('Solicitacao', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='orcamentos', verbose_name='Solicitação')
    cliente = models.ForeignKey(CadClientes, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cliente cadastrado')
    nome_cliente = models.CharField('Nome do cliente', max_length=150, blank=True)
    telefone = models.CharField('Telefone / WhatsApp', max_length=30, blank=True)
    data = models.DateField('Data', default=timezone.localdate)
    validade = models.DateField('Válido até', null=True, blank=True)
    prazo_dias = models.PositiveIntegerField('Prazo de produção (dias)', default=7)
    sinal_percentual = models.DecimalField('Sinal (%)', max_digits=5, decimal_places=2, default=Decimal('50.00'))
    status = models.CharField('Situação', max_length=10, choices=StatusOrcamento.choices, default=StatusOrcamento.RASCUNHO)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Orçamento'
        verbose_name_plural = 'Orçamentos'
        ordering = ('-data', '-id')

    def __str__(self):
        return f'{self.numero} - {self.nome_exibicao}'

    @property
    def numero(self):
        return f'ORC-{self.pk:04d}' if self.pk else 'ORC-novo'

    @property
    def nome_exibicao(self):
        return self.cliente.name if self.cliente_id else (self.nome_cliente or 'Sem nome')

    @property
    def telefone_exibicao(self):
        return self.cliente.telefone if self.cliente_id else self.telefone

    @property
    def valor_sinal(self):
        return (self.total * _dec(self.sinal_percentual) / 100).quantize(Decimal('0.01'))

    @property
    def vencido(self):
        return bool(self.validade and self.validade < timezone.localdate()
                    and self.status in (StatusOrcamento.RASCUNHO, StatusOrcamento.ENVIADO))


class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Produto')
    descricao = models.CharField('Descrição', max_length=200, blank=True)
    qnt = models.PositiveIntegerField('Qtd.', default=1)
    preco_unitario = models.DecimalField('Preço unitário', max_digits=10, decimal_places=2, default=D0)
    calculo = models.JSONField('Cálculo', null=True, blank=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.nome

    @property
    def nome(self):
        return self.descricao or (self.produto.product if self.produto_id else 'Item')

    @property
    def total(self):
        return (_dec(self.preco_unitario) * (self.qnt or 0)).quantize(Decimal('0.01'))


# ---------------------------------------------------------------------------
# Pedidos (encomendas)
# ---------------------------------------------------------------------------
class StatusPedido(models.TextChoices):
    AGUARDANDO = 'AGUARDANDO', 'Aguardando'
    IMPRIMINDO = 'IMPRIMINDO', 'Imprimindo'
    ACABAMENTO = 'ACABAMENTO', 'Acabamento'
    PRONTO = 'PRONTO', 'Pronto'
    ENTREGUE = 'ENTREGUE', 'Entregue'
    CANCELADO = 'CANCELADO', 'Cancelado'


ETAPAS = [StatusPedido.AGUARDANDO, StatusPedido.IMPRIMINDO, StatusPedido.ACABAMENTO, StatusPedido.PRONTO]


class Pedido(_ComItens):
    orcamento = models.OneToOneField(Orcamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedido')
    cliente = models.ForeignKey(CadClientes, on_delete=models.PROTECT, verbose_name='Cliente')
    data = models.DateField('Data do pedido', default=timezone.localdate)
    prazo = models.DateField('Entregar até')
    status = models.CharField('Etapa', max_length=12, choices=StatusPedido.choices, default=StatusPedido.AGUARDANDO)
    sinal_combinado = models.DecimalField('Sinal combinado (R$)', max_digits=10, decimal_places=2, default=D0)
    sinal_recebido = models.DecimalField('Sinal recebido (R$)', max_digits=10, decimal_places=2, default=D0)
    sinal_forma = models.CharField('Forma do sinal', max_length=20, choices=FormaPagamento.choices, blank=True)
    sinal_data = models.DateField('Data do sinal', null=True, blank=True)
    forma_final = models.CharField('Forma do pagamento final', max_length=20, choices=FormaPagamento.choices, blank=True)
    entregue_em = models.DateField('Entregue em', null=True, blank=True)
    vendas_geradas = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ('prazo', 'id')

    def __str__(self):
        return f'{self.numero} - {self.cliente}'

    @property
    def numero(self):
        return f'PED-{self.pk:04d}' if self.pk else 'PED-novo'

    @property
    def falta_receber(self):
        return max(D0, self.total - _dec(self.sinal_recebido))

    @property
    def atrasado(self):
        return self.status in ETAPAS and self.prazo < timezone.localdate()

    @property
    def dias_para_prazo(self):
        return (self.prazo - timezone.localdate()).days

    @property
    def dias_atraso(self):
        return -self.dias_para_prazo

    @property
    def proxima_etapa(self):
        if self.status in ETAPAS:
            i = ETAPAS.index(self.status)
            return ETAPAS[i + 1] if i + 1 < len(ETAPAS) else None
        return None

    @staticmethod
    def prazo_padrao(dias):
        return timezone.localdate() + timedelta(days=dias)


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Produto')
    descricao = models.CharField('Descrição', max_length=200, blank=True)
    qnt = models.PositiveIntegerField('Qtd.', default=1)
    preco_unitario = models.DecimalField('Preço unitário', max_digits=10, decimal_places=2, default=D0)
    calculo = models.JSONField('Cálculo', null=True, blank=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.nome

    nome = ItemOrcamento.nome
    total = ItemOrcamento.total


# ---------------------------------------------------------------------------
# Solicitações (briefing do cliente antes do orçamento)
# ---------------------------------------------------------------------------
class StatusSolicitacao(models.TextChoices):
    NOVA = 'NOVA', 'Nova'
    ANALISE = 'ANALISE', 'Em análise'
    AGUARDANDO = 'AGUARDANDO', 'Aguardando cliente'
    ORCADA = 'ORCADA', 'Orçada'
    DESCARTADA = 'DESCARTADA', 'Descartada'


ABERTAS = [StatusSolicitacao.NOVA, StatusSolicitacao.ANALISE, StatusSolicitacao.AGUARDANDO]


class Canal(models.TextChoices):
    WHATSAPP = 'WHATSAPP', 'WhatsApp'
    INSTAGRAM = 'INSTAGRAM', 'Instagram'
    FEIRA = 'FEIRA', 'Feira'
    PRESENCIAL = 'PRESENCIAL', 'Presencial'
    OUTRO = 'OUTRO', 'Outro'


class Solicitacao(models.Model):
    cliente = models.ForeignKey(CadClientes, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cliente cadastrado')
    nome_cliente = models.CharField('Nome do cliente', max_length=150, blank=True)
    telefone = models.CharField('Telefone / WhatsApp', max_length=30, blank=True)
    canal = models.CharField('Chegou por', max_length=12, choices=Canal.choices, default=Canal.WHATSAPP)
    titulo = models.CharField('O que é', max_length=150, help_text='Ex.: Topo de bolo com nome, Miniatura do cachorro')
    descricao = models.TextField('Descrição / o que o cliente pediu', blank=True)
    largura = models.DecimalField('Largura (cm)', max_digits=7, decimal_places=1, null=True, blank=True)
    altura = models.DecimalField('Altura (cm)', max_digits=7, decimal_places=1, null=True, blank=True)
    profundidade = models.DecimalField('Profundidade (cm)', max_digits=7, decimal_places=1, null=True, blank=True)
    medidas_obs = models.CharField('Outras medidas / observações', max_length=250, blank=True)
    cores = models.CharField('Cores', max_length=150, blank=True)
    material = models.CharField('Material', max_length=60, blank=True)
    quantidade = models.PositiveIntegerField('Quantidade', default=1)
    prazo = models.DateField('Cliente precisa até', null=True, blank=True)
    verba = models.DecimalField('Quanto pretende gastar (R$)', max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField('Situação', max_length=12, choices=StatusSolicitacao.choices, default=StatusSolicitacao.NOVA)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Solicitação'
        verbose_name_plural = 'Solicitações'
        ordering = ('-criado_em',)

    def __str__(self):
        return f'{self.numero} - {self.titulo}'

    @property
    def numero(self):
        return f'SOL-{self.pk:04d}' if self.pk else 'SOL-nova'

    @property
    def nome_exibicao(self):
        return self.cliente.name if self.cliente_id else (self.nome_cliente or 'Sem nome')

    @property
    def telefone_exibicao(self):
        return self.cliente.telefone if self.cliente_id else self.telefone

    @property
    def medidas(self):
        dims = [d for d in (self.largura, self.altura, self.profundidade) if d]
        txt = ' × '.join(f'{d.normalize():f}'.replace('.', ',') for d in dims)
        return (txt + ' cm') if txt else ''

    @property
    def dias_para_prazo(self):
        return (self.prazo - timezone.localdate()).days if self.prazo else None

    @property
    def imagens(self):
        return [a for a in self.anexos.all() if a.e_imagem]

    @property
    def capa(self):
        imgs = self.imagens
        return imgs[0] if imgs else None


class Anotacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name='anotacoes')
    texto = models.TextField('Anotação', blank=True)
    autor = models.CharField(max_length=150, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-criado_em', '-id')


def _caminho_anexo(instance, filename):
    import uuid
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else 'bin').lower()[:8]
    return f'solicitacoes/{instance.solicitacao_id}/{uuid.uuid4().hex}.{ext}'


def _caminho_miniatura(instance, filename):
    import uuid
    return f'solicitacoes/{instance.solicitacao_id}/mini/{uuid.uuid4().hex}.jpg'


class Anexo(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name='anexos')
    anotacao = models.ForeignKey(Anotacao, on_delete=models.CASCADE, null=True, blank=True, related_name='anexos')
    arquivo = models.FileField(upload_to=_caminho_anexo, max_length=255)
    miniatura = models.FileField(upload_to=_caminho_miniatura, max_length=255, null=True, blank=True)
    nome_original = models.CharField(max_length=255)
    e_imagem = models.BooleanField(default=False)
    tamanho = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('criado_em', 'id')

    def __str__(self):
        return self.nome_original

    @property
    def extensao(self):
        return self.nome_original.rsplit('.', 1)[-1].upper() if '.' in self.nome_original else ''

    def apagar_arquivos(self):
        for f in (self.arquivo, self.miniatura):
            if f:
                try:
                    f.storage.delete(f.name)
                except OSError:
                    pass


# apagar os arquivos do disco quando o anexo for apagado
from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=Anexo)
def _apagar_arquivos_do_anexo(sender, instance, **kwargs):
    instance.apagar_arquivos()
