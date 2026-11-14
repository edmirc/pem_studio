"""Login com trava: depois de várias senhas erradas, bloqueia por alguns minutos."""
import hashlib

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.cache import cache


def ip_do_cliente(request):
    # Atrás do Caddy, o IP real é o último do X-Forwarded-For (o Caddy não repassa o que o cliente inventar)
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '')


def _chave(tipo, valor):
    return f'login:{tipo}:' + hashlib.sha256(valor.lower().encode()).hexdigest()[:32]


class LoginView(auth_views.LoginView):
    template_name = 'painel/login.html'
    redirect_authenticated_user = True

    def _chaves(self):
        usuario = (self.request.POST.get('username') or '').strip()
        return _chave('ip', ip_do_cliente(self.request)), _chave('usuario', usuario) if usuario else None

    def _bloqueado(self):
        k_ip, k_user = self._chaves()
        if (cache.get(k_ip) or 0) >= settings.LOGIN_MAX_TENTATIVAS_IP:
            return True
        return bool(k_user and (cache.get(k_user) or 0) >= settings.LOGIN_MAX_TENTATIVAS_USUARIO)

    def post(self, request, *args, **kwargs):
        if self._bloqueado():
            form = self.get_form()
            form.is_valid()  # não autentica: só para renderizar a página
            return self.render_to_response(self.get_context_data(form=form, bloqueado=True))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        segundos = settings.LOGIN_BLOQUEIO_MINUTOS * 60
        for k in self._chaves():
            if k:
                cache.add(k, 0, segundos)
                try:
                    cache.incr(k)
                except ValueError:
                    cache.set(k, 1, segundos)
        return super().form_invalid(form)

    def form_valid(self, form):
        k_ip, k_user = self._chaves()
        cache.delete(k_ip)
        if k_user:
            cache.delete(k_user)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['minutos_bloqueio'] = settings.LOGIN_BLOQUEIO_MINUTOS
        return ctx
