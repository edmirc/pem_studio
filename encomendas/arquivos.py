"""Salvar anexos: fotos são reduzidas (máx. 2000 px) e ganham miniatura."""
import io
import os

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Anexo

MAX_LADO = 2000
MINI_LADO = 480
MAX_BYTES = 60 * 1024 * 1024  # 60 MB por arquivo
EXTENSOES = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'heic', 'stl', '3mf', 'obj', 'step', 'stp', 'pdf',
             'svg', 'dxf', 'txt', 'zip', 'mp4', 'mov'}


class ArquivoInvalido(Exception):
    pass


def _jpeg(img, qualidade=85):
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=qualidade, optimize=True)
    return buf.getvalue()


def salvar_anexo(solicitacao, upload, anotacao=None):
    nome = os.path.basename(upload.name or 'arquivo')[:200]
    ext = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
    if upload.size > MAX_BYTES:
        raise ArquivoInvalido(f'{nome}: maior que 60 MB.')
    if ext not in EXTENSOES and not (upload.content_type or '').startswith('image/'):
        raise ArquivoInvalido(f'{nome}: tipo de arquivo não aceito.')

    anexo = Anexo(solicitacao=solicitacao, anotacao=anotacao, nome_original=nome)
    dados = upload.read()
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
        img = ImageOps.exif_transpose(img)
        tem_alfa = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
        img.thumbnail((MAX_LADO, MAX_LADO))
        if tem_alfa:
            buf = io.BytesIO()
            img.save(buf, 'PNG', optimize=True)
            conteudo, nome_salvo = buf.getvalue(), 'imagem.png'
            base = Image.new('RGB', img.size, 'white')
            base.paste(img.convert('RGBA'), mask=img.convert('RGBA').split()[-1])
            mini_src = base
        else:
            rgb = img.convert('RGB')
            conteudo, nome_salvo = _jpeg(rgb), 'imagem.jpg'
            mini_src = rgb
        mini = mini_src.copy()
        mini.thumbnail((MINI_LADO, MINI_LADO))
        anexo.e_imagem = True
        anexo.arquivo.save(nome_salvo, ContentFile(conteudo), save=False)
        anexo.miniatura.save('mini.jpg', ContentFile(_jpeg(mini, 80)), save=False)
        anexo.tamanho = len(conteudo)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        anexo.arquivo.save(nome or 'arquivo', ContentFile(dados), save=False)
        anexo.tamanho = len(dados)
    anexo.save()
    return anexo
