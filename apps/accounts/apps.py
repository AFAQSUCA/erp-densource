from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        from apps.audit.registry import audit_model

        from . import signals  # noqa: F401  (branche les récepteurs)
        from .models import User

        # Création de compte, changement de rôle, activation/désactivation, droits : la modification la
        # plus sensible de l'ERP. ``last_login`` change à chaque connexion (bruit) ; le mot de passe
        # n'est jamais écrit, seule son empreinte, pour qu'un changement reste visible.
        audit_model(User, module="UTILISATEURS", exclure=("last_login",), masquer=("password",))

        from . import permissions
        from .navigation import EntreeMenu, enregistrer

        enregistrer(
            EntreeMenu("Utilisateurs", "accounts:utilisateurs", "fa-users-gear", permissions.GESTION_UTILISATEURS, ordre=89)
        )
