from django.apps import AppConfig


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fleet'
    label = 'fleet'

    def ready(self):
        from apps.audit.registry import audit_model

        from .models import DocumentReglementaire, Vehicule

        audit_model(Vehicule, module="PARC_AUTO")
        audit_model(DocumentReglementaire, module="PARC_AUTO")
