from django.apps import AppConfig


class DriversConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.drivers'
    label = 'drivers'

    def ready(self):
        from apps.audit.registry import audit_model

        from . import signals  # noqa: F401
        from .models import Chauffeur

        audit_model(Chauffeur, module="CHAUFFEUR")
