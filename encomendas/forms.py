from django import forms
from django.forms import inlineformset_factory

from .models import Configuracao, Impressora, ItemOrcamento, ItemPedido, Orcamento, Pedido

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


def _dinheiro():
    return forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'})


class _Base(forms.ModelForm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            if not isinstance(f.widget, (forms.CheckboxInput, forms.HiddenInput)):
                f.widget.attrs.setdefault('class', 'campo')


class ConfiguracaoForm(_Base):
    class Meta:
        model = Configuracao
        fields = '__all__'
        widgets = {n: forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'})
                   for n in ['preco_kwh', 'valor_hora_trabalho', 'taxa_falha', 'lucro_padrao', 'custo_kg_padrao',
                             'sinal_percentual', 'taxa_debito'] + [f'taxa_credito_{i}x' for i in range(1, 7)]}


class ImpressoraForm(_Base):
    class Meta:
        model = Impressora
        fields = ['nome', 'modelo', 'potencia_media_w', 'custo_hora', 'ativa']
        widgets = {'custo_hora': _dinheiro()}


class OrcamentoForm(_Base):
    class Meta:
        model = Orcamento
        fields = ['cliente', 'nome_cliente', 'telefone', 'data', 'validade', 'prazo_dias', 'sinal_percentual',
                  'desconto', 'frete', 'observacoes']
        widgets = {'data': DATA, 'validade': DATA, 'desconto': _dinheiro(), 'frete': _dinheiro(),
                   'sinal_percentual': forms.NumberInput(attrs={'step': '1', 'min': '0', 'max': '100'}),
                   'observacoes': forms.Textarea(attrs={'rows': 3}),
                   'telefone': forms.TextInput(attrs={'inputmode': 'tel', 'placeholder': '(65) 99999-9999'})}
        help_texts = {'cliente': 'Ou preencha nome e telefone abaixo para um cliente novo.'}

    def clean(self):
        d = super().clean()
        if not d.get('cliente') and not (d.get('nome_cliente') or '').strip():
            self.add_error('nome_cliente', 'Escolha um cliente cadastrado ou digite o nome.')
        return d


class PedidoForm(_Base):
    class Meta:
        model = Pedido
        fields = ['cliente', 'data', 'prazo', 'sinal_combinado', 'desconto', 'frete', 'observacoes']
        widgets = {'data': DATA, 'prazo': DATA, 'desconto': _dinheiro(), 'frete': _dinheiro(),
                   'sinal_combinado': _dinheiro(), 'observacoes': forms.Textarea(attrs={'rows': 3})}


class _ItemForm(_Base):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields['calculo'].widget = forms.HiddenInput(attrs={'data-f': 'calculo'})
        self.fields['produto'].widget.attrs['data-f'] = 'produto'
        self.fields['descricao'].widget.attrs.update({'data-f': 'descricao', 'placeholder': 'Descrição (peça personalizada)'})
        self.fields['qnt'].widget.attrs.update({'data-f': 'qnt', 'min': '1', 'inputmode': 'numeric'})
        self.fields['preco_unitario'].widget.attrs.update({'data-f': 'preco', 'step': '0.01', 'min': '0', 'inputmode': 'decimal'})

    def clean(self):
        d = super().clean()
        if not self.cleaned_data.get('DELETE') and not d.get('produto') and not (d.get('descricao') or '').strip():
            if self.has_changed():
                self.add_error('descricao', 'Escolha um produto ou escreva a descrição.')
        return d


class ItemOrcamentoForm(_ItemForm):
    class Meta:
        model = ItemOrcamento
        fields = ['produto', 'descricao', 'qnt', 'preco_unitario', 'calculo']


class ItemPedidoForm(_ItemForm):
    class Meta:
        model = ItemPedido
        fields = ['produto', 'descricao', 'qnt', 'preco_unitario', 'calculo']


ItensOrcamento = inlineformset_factory(Orcamento, ItemOrcamento, form=ItemOrcamentoForm, extra=0, can_delete=True)
ItensPedido = inlineformset_factory(Pedido, ItemPedido, form=ItemPedidoForm, extra=0, can_delete=True)


from .models import Solicitacao  # noqa: E402


class SolicitacaoForm(_Base):
    class Meta:
        model = Solicitacao
        fields = ['cliente', 'nome_cliente', 'telefone', 'canal', 'titulo', 'descricao', 'quantidade', 'prazo',
                  'largura', 'altura', 'profundidade', 'medidas_obs', 'cores', 'material', 'verba', 'status']
        widgets = {
            'prazo': DATA, 'verba': _dinheiro(),
            'descricao': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Cole aqui o que o cliente escreveu, tema, nome a gravar…'}),
            'telefone': forms.TextInput(attrs={'inputmode': 'tel', 'placeholder': '(65) 99999-9999'}),
            'material': forms.TextInput(attrs={'list': 'lista-materiais', 'autocomplete': 'off'}),
            'largura': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'inputmode': 'decimal'}),
            'altura': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'inputmode': 'decimal'}),
            'profundidade': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'inputmode': 'decimal'}),
            'quantidade': forms.NumberInput(attrs={'min': '1', 'inputmode': 'numeric'}),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if not self.instance.pk:
            self.fields.pop('status')

    def clean(self):
        d = super().clean()
        if not d.get('cliente') and not (d.get('nome_cliente') or '').strip():
            self.add_error('nome_cliente', 'Escolha um cliente cadastrado ou digite o nome.')
        return d
