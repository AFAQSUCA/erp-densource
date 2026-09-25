from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    label = 'audit'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions, signals  # noqa: F401

        enregistrer(
            EntreeMenu(
                "Journal d'audit", "audit:journal", "fa-clipboard-list", permissions.CONSULTATION, ordre=90
            )
        )
