from django.apps import AppConfig
from django.db.backends.signals import connection_created


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    label = 'core'

    def ready(self):
        from .search import enregistrer_fonction_sqlite

        connection_created.connect(
            enregistrer_fonction_sqlite, dispatch_uid="core.recherche.sqlite"
        )
