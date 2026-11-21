from django.urls import path

from . import kits, views

app_name = 'producao'

urlpatterns = [
    path('impressao/', views.painel, name='painel'),
    path('impressao/nova/', views.nova, name='nova'),
    path('impressao/<int:pk>/<slug:acao>/', views.acao, name='acao'),
    path('kits/', kits.lista, name='kits'),
    path('kits/novo/', kits.editar, name='kit_novo'),
    path('kits/<int:pk>/', kits.editar, name='kit'),
    path('kits/<int:pk>/apagar/', kits.apagar, name='kit_apagar'),
    path('estoque/', views.estoque, name='estoque'),
    path('estoque/contagem/', views.contagem, name='contagem'),
    path('estoque/<int:pk>/', views.produto, name='produto'),
]
