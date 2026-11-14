from django.urls import path

from . import views

app_name = 'financas'

urlpatterns = [
    path('', views.contas, name='contas'),
    path('novo/', views.lancamento_editar, name='novo'),
    path('<int:pk>/editar/', views.lancamento_editar, name='editar'),
    path('acao/<slug:acao>/', views.lancamento_acao, name='acao'),
    path('faturas/', views.faturas, name='faturas'),
    path('fluxo/', views.fluxo, name='fluxo'),
]
