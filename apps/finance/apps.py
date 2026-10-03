from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    label = 'finance'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model
        from apps.core.medias import enregistrer_media

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import DemandeDepense, EnveloppeDepense, LigneReleve, MouvementManuel, OrdreDecaissement

        audit_model(MouvementManuel, module="FINANCES")
        audit_model(EnveloppeDepense, module="FINANCES")
        audit_model(DemandeDepense, module="FINANCES")
        audit_model(OrdreDecaissement, module="FINANCES")
        audit_model(LigneReleve, module="FINANCES")
        enregistrer_media("demandes_depense", permissions.DEMANDE_CONSULTATION)
        enregistrer_media("ordres_decaissement", permissions.DEMANDE_CONSULTATION)
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
        enregistrer(
            EntreeMenu(
                "Rapprochement bancaire", "finance:rapprochement", "fa-money-check-alt",
                permissions.CONSULTATION, ordre=64,
            )
        )
