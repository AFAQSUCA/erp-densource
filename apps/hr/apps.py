from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hr'
    label = 'hr'

    def ready(self):
        from apps.audit.registry import audit_model

        from .models import Personnel

        audit_model(Personnel, module="RH")
