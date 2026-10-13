from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    label = 'audit'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions, signals  # noqa: F401
        from .registry import audit_model

        # Création de compte, changement de rôle, activation/désactivation, droits : la modification la
        # plus sensible de l'ERP. ``last_login`` change à chaque connexion (bruit) ; le mot de passe
        # n'est jamais écrit, seule son empreinte, pour qu'un changement reste visible. Branché ici et non dans
        # ``accounts`` : ``audit`` dépend de ``accounts``, jamais l'inverse (audit AUD-20).
        from apps.accounts.models import User

        audit_model(User, module="UTILISATEURS", exclure=("last_login",), masquer=("password",))

        enregistrer(
            EntreeMenu(
                "Journal d'audit", "audit:journal", "fa-clipboard-list", permissions.CONSULTATION, ordre=90
            )
        )
