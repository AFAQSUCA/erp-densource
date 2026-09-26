from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    label = 'billing'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Depense, Facture, Proforma, Reglement

        audit_model(Facture, module="FINANCES")
        audit_model(Reglement, module="FINANCES")
        audit_model(Depense, module="FINANCES")
        audit_model(Proforma, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Facturation", "billing:factures", "fa-file-invoice-dollar",
                permissions.CONSULTATION, ordre=60,
            )
        )
        enregistrer(
            EntreeMenu(
                "Dépenses", "billing:depenses", "fa-receipt", permissions.CONSULTATION, ordre=61
            )
        )
        enregistrer(
            EntreeMenu(
                "Devis", "billing:proformas", "fa-file-signature",
                permissions.PROFORMA_CONSULTATION, ordre=59,
            )
        )
