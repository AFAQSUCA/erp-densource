from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        from . import signals  # noqa: F401  (branche les récepteurs)

        # L'audit du modèle User est branché par ``apps.audit`` (qui dépend de ``accounts``, pas l'inverse :
        # audit AUD-20).
        from . import permissions
        from .navigation import EntreeMenu, enregistrer

        enregistrer(
            EntreeMenu("Utilisateurs", "accounts:utilisateurs", "fa-users-gear", permissions.GESTION_UTILISATEURS, ordre=89)
        )
