from django.apps import AppConfig


class ProducaoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'producao'
    verbose_name = 'Impressão e estoque'

    def ready(self):
        from . import sinais  # noqa: F401
