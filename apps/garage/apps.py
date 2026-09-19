from django.apps import AppConfig


class GarageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.garage'
    label = 'garage'

    def ready(self):
        from apps.audit.registry import audit_model

        from .models import OrdreReparation

        audit_model(OrdreReparation, module="PARC_AUTO")
