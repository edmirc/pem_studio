from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from painel.login import LoginView

urlpatterns = [
    # o login do Admin passa pela mesma tela (com a trava contra tentativas)
    path('admin/login/', RedirectView.as_view(url='/entrar/', query_string=True)),
    path('admin/', admin.site.urls),
    path('entrar/', LoginView.as_view(), name='login'),
    path('sair/', auth_views.LogoutView.as_view(), name='sair'),
    path('encomendas/', include('encomendas.urls')),
    path('financeiro/', include('financas.urls')),
    path('', include('producao.urls')),
    path('', include('painel.urls')),
]
