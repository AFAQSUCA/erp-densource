from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    label = 'finance'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import DemandeDepense, EnveloppeDepense, MouvementManuel, OrdreDecaissement

        audit_model(MouvementManuel, module="FINANCES")
        audit_model(EnveloppeDepense, module="FINANCES")
        audit_model(DemandeDepense, module="FINANCES")
        audit_model(OrdreDecaissement, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Trésorerie", "finance:tresorerie", "fa-wallet", permissions.CONSULTATION, ordre=62
            )
        )
        enregistrer(
            EntreeMenu(
                "Demandes de dépense", "finance:demandes", "fa-file-invoice",
                permissions.DEMANDE_CONSULTATION, ordre=63,
            )
        )
