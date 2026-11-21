from django.urls import path

from . import crud, produtos, views

app_name = 'painel'

urlpatterns = [
    path('', views.inicio, name='inicio'),

    # Venda na feira
    path('feira/', views.pdv_escolher, name='pdv_escolher'),
    path('feira/<int:pk>/', views.pdv, name='pdv'),
    path('feira/<int:pk>/adicionar/', views.pdv_adicionar, name='pdv_adicionar'),
    path('feira/<int:pk>/apagar/<int:venda_id>/', views.pdv_apagar, name='pdv_apagar'),
    path('feira/<int:pk>/fechamento/', views.fechamento_feira, name='fechamento_feira'),

    # Relatórios
    path('relatorios/mensal/', views.relatorio_mensal, name='relatorio_mensal'),
    path('relatorios/anual/', views.relatorio_anual, name='relatorio_anual'),

    # Ficha do cliente
    path('clientes/<int:pk>/', views.cliente, name='cliente'),

    # Foto do produto e atalho para abrir arquivos 3D no Windows
    path('produtos/<int:pk>/foto/', produtos.foto, name='produto_foto'),
    path('produtos/<int:pk>/foto/mini/', produtos.foto, {'mini': True}, name='produto_mini'),
    path('ferramentas/abrir-arquivos.zip', produtos.ferramenta_zip, name='ferramenta_abrir'),

    # Cadastros genéricos (clientes, produtos, compras, ...)
    path('<slug:slug>/', crud.lista, name='lista'),
    path('<slug:slug>/novo/', crud.editar, name='novo'),
    path('<slug:slug>/<int:pk>/editar/', crud.editar, name='editar'),
    path('<slug:slug>/<int:pk>/apagar/', crud.apagar, name='apagar'),
]
