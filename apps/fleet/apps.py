from django.apps import AppConfig


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fleet'
    label = 'fleet'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import DocumentReglementaire, Vehicule

        audit_model(Vehicule, module="PARC_AUTO")
        audit_model(DocumentReglementaire, module="PARC_AUTO")
        enregistrer(
            EntreeMenu("Flotte", "fleet:liste", "fa-truck", permissions.CONSULTATION, ordre=20)
        )
