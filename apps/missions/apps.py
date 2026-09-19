from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.missions'
    label = 'missions'

    def ready(self):
        from apps.audit.registry import audit_model

        from .models import Mission

        # Les codes secrets ne doivent jamais apparaître dans le journal.
        audit_model(
            Mission, module="MISSION", exclure=("code_expediteur", "code_destinataire")
        )
