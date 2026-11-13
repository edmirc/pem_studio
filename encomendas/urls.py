from django.urls import path

from . import views, views_solicitacoes as vs

app_name = 'encomendas'

urlpatterns = [
    path('solicitacoes/', vs.solicitacoes, name='solicitacoes'),
    path('solicitacoes/nova/', vs.solicitacao_editar, name='solicitacao_nova'),
    path('solicitacoes/<int:pk>/', vs.solicitacao, name='solicitacao'),
    path('solicitacoes/<int:pk>/editar/', vs.solicitacao_editar, name='solicitacao_editar'),
    path('solicitacoes/<int:pk>/<slug:acao>/', vs.solicitacao_acao, name='solicitacao_acao'),
    path('arquivo/<int:pk>/', vs.arquivo, name='arquivo'),
    path('arquivo/<int:pk>/<slug:tipo>/', vs.arquivo, name='arquivo_tipo'),

    path('calculadora/', views.calculadora, name='calculadora'),
    path('calculadora/precificacao/', views.calc_precificacao, name='calc_precificacao'),
    path('calculadora/orcamento/', views.orcamento_da_calc, name='orcamento_da_calc'),
    path('configuracoes/', views.configuracoes, name='configuracoes'),
    path('configuracoes/impressora/nova/', views.impressora_editar, name='impressora_nova'),
    path('configuracoes/impressora/<int:pk>/', views.impressora_editar, name='impressora_editar'),

    path('orcamentos/', views.orcamentos, name='orcamentos'),
    path('orcamentos/novo/', views.orcamento_editar, name='orcamento_novo'),
    path('orcamentos/<int:pk>/', views.orcamento, name='orcamento'),
    path('orcamentos/<int:pk>/editar/', views.orcamento_editar, name='orcamento_editar'),
    path('orcamentos/<int:pk>/<slug:acao>/', views.orcamento_acao, name='orcamento_acao'),

    path('pedidos/', views.pedidos, name='pedidos'),
    path('pedidos/historico/', views.pedidos_historico, name='pedidos_historico'),
    path('pedidos/<int:pk>/', views.pedido, name='pedido'),
    path('pedidos/<int:pk>/editar/', views.pedido_editar, name='pedido_editar'),
    path('pedidos/<int:pk>/<slug:acao>/', views.pedido_acao, name='pedido_acao'),
]
