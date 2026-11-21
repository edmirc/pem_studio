"""Foto do produto e atalhos para abrir o arquivo 3D no Windows."""
import io
import os
import zipfile
from pathlib import Path
from urllib.parse import quote

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from PIL import Image, ImageOps, UnidentifiedImageError

from cadastro.models import Product

MAX_LADO = 1600
MINI_LADO = 360
MAX_BYTES = 25 * 1024 * 1024
FERRAMENTAS = Path(__file__).resolve().parent / 'ferramentas' / 'abrir-arquivos'
EXTENSOES_3D = ('.3mf', '.stl', '.obj', '.step', '.stp', '.amf', '.ply', '.gcode', '.bgcode')


class FotoInvalida(Exception):
    pass


# ---------------------------------------------------------------------------
# Foto
# ---------------------------------------------------------------------------
def _salvar(img, fmt, qualidade):
    buf = io.BytesIO()
    if fmt == 'PNG':
        img.save(buf, 'PNG', optimize=True)
    else:
        img.save(buf, 'JPEG', quality=qualidade, optimize=True)
    return buf.getvalue()


def apagar_foto(produto, salvar=True):
    for campo in (produto.imagem, produto.miniatura):
        if campo:
            try:
                campo.storage.delete(campo.name)
            except OSError:
                pass
    produto.imagem = ''
    produto.miniatura = ''
    if salvar:
        produto.save(update_fields=['imagem', 'miniatura'])


def salvar_foto(produto, upload):
    """Reduz a foto (máx. 1600 px), gera a miniatura e troca a foto antiga."""
    if upload.size > MAX_BYTES:
        raise FotoInvalida('A foto é maior que 25 MB.')
    try:
        img = Image.open(upload)
        img.load()
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise FotoInvalida('Esse arquivo não é uma imagem (use JPG, PNG ou WEBP).')
    tem_alfa = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    img.thumbnail((MAX_LADO, MAX_LADO))
    if tem_alfa:
        rgba = img.convert('RGBA')
        grande, ext = _salvar(rgba, 'PNG', 0), 'png'
        fundo = Image.new('RGB', rgba.size, 'white')
        fundo.paste(rgba, mask=rgba.split()[-1])
        base = fundo
    else:
        base = img.convert('RGB')
        grande, ext = _salvar(base, 'JPEG', 86), 'jpg'
    mini = base.copy()
    mini.thumbnail((MINI_LADO, MINI_LADO))
    apagar_foto(produto, salvar=False)
    produto.imagem.save(f'produto-{produto.pk}.{ext}', ContentFile(grande), save=False)
    produto.miniatura.save(f'produto-{produto.pk}-mini.jpg', ContentFile(_salvar(mini, 'JPEG', 80)), save=False)
    produto.save(update_fields=['imagem', 'miniatura'])


@login_required
def foto(request, pk, mini=False):
    p = get_object_or_404(Product, pk=pk)
    campo = (p.miniatura or p.imagem) if mini else p.imagem
    if not campo:
        raise Http404('Produto sem foto.')
    try:
        arq = campo.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('Foto não encontrada na pasta de imagens.')
    resp = FileResponse(arq)
    resp['Cache-Control'] = 'private, max-age=2592000'  # a URL muda quando a foto muda
    return resp


# ---------------------------------------------------------------------------
# Formulário do produto
# ---------------------------------------------------------------------------
def limpar_caminho(c):
    c = (c or '').strip().strip('"').strip("'").strip()
    return c


class ProdutoForm(forms.ModelForm):
    foto = forms.FileField(label='Foto', required=False,
                           widget=forms.ClearableFileInput(attrs={'accept': 'image/*', 'class': 'campo'}))
    remover_foto = forms.BooleanField(label='Tirar a foto', required=False)

    class Meta:
        model = Product
        fields = ['product', 'category', 'arquivo']
        widgets = {'arquivo': forms.TextInput(attrs={'placeholder': r'\\192.168.3.190\hd4t\3D\vaso.3mf',
                                                     'spellcheck': 'false', 'autocomplete': 'off'})}

    def __init__(self, *args, rotulos=None, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if rotulos and nome in rotulos:
                campo.label = rotulos[nome]
            if nome != 'remover_foto':
                campo.widget.attrs.setdefault('class', 'campo')
        self.fields['arquivo'].help_text = ('Copie o caminho no Windows: clique com o botão direito no arquivo '
                                            'e escolha "Copiar como caminho".')

    def clean_arquivo(self):
        return limpar_caminho(self.cleaned_data.get('arquivo'))

    def clean_foto(self):
        f = self.cleaned_data.get('foto')
        if f and f.size > MAX_BYTES:
            raise forms.ValidationError('A foto é maior que 25 MB.')
        return f

    def save(self, commit=True):
        produto = super().save(commit=True)
        f = self.cleaned_data.get('foto')
        if f:
            try:
                salvar_foto(produto, f)
            except FotoInvalida as e:
                self.aviso_foto = str(e)
        elif self.cleaned_data.get('remover_foto'):
            apagar_foto(produto)
        return produto


# ---------------------------------------------------------------------------
# Abrir o arquivo 3D no Windows (protocolo pemstudio:)
# ---------------------------------------------------------------------------
FATIADORES = [('creality', 'Creality Print'), ('bambu', 'Bambu Studio'), ('snapmaker', 'Snapmaker Orca')]


def fatiador_da_impressora(impressora):
    """Qual fatiador abre primeiro para esta impressora."""
    if not impressora:
        return 'creality'
    texto = f'{impressora} {getattr(impressora, "modelo", "")}'.lower()
    if 'bambu' in texto:
        return 'bambu'
    if 'snapmaker' in texto or texto.split()[:1] == ['u1']:
        return 'snapmaker'
    return 'creality'


def links_arquivo(caminho, impressora=None):
    """Links pemstudio: para abrir a pasta ou o fatiador. `impressora` decide qual fatiador vem primeiro."""
    if not caminho:
        return None
    p = quote(caminho, safe='')
    nome = caminho.replace('/', '\\').rstrip('\\').rsplit('\\', 1)[-1]
    e_3d = nome.lower().endswith(EXTENSOES_3D)
    preferido = fatiador_da_impressora(impressora)
    fatiadores = sorted(FATIADORES, key=lambda f: f[0] != preferido)
    return {
        'caminho': caminho, 'nome': nome, 'e_3d': e_3d,
        'pasta': f'pemstudio:pasta?p={p}',
        'fatiadores': [{'chave': k, 'nome': n, 'url': f'pemstudio:abrir?com={k}&p={p}'} for k, n in fatiadores] if e_3d else [],
        'padrao': f'pemstudio:abrir?com=padrao&p={p}',
    }


@login_required
def ferramenta_zip(request):
    """Instalador do atalho 'abrir arquivo' para os computadores com Windows."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(FERRAMENTAS.iterdir()):
            if f.is_file():
                dados = f.read_bytes()
                if f.suffix.lower() in ('.cmd', '.txt', '.vbs'):
                    dados = dados.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                z.writestr(f'PEM Studio - abrir arquivos/{f.name}', dados)
    resp = HttpResponse(buf.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = 'attachment; filename="pem-studio-abrir-arquivos.zip"'
    return resp
