from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounting"
    label = "accounting"
    verbose_name = "Comptabilité"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import Compte, EcritureComptable, LigneEcriture

        audit_model(Compte, module="COMPTABILITE")
        audit_model(EcritureComptable, module="COMPTABILITE")
        audit_model(LigneEcriture, module="COMPTABILITE")
        enregistrer(
            EntreeMenu(
                "Opérations diverses", "accounting:ecritures_manuelles", "fa-scale-balanced",
                permissions.CONSULTATION, ordre=64,
            )
        )
