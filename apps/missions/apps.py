from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.missions'
    label = 'missions'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Mission

        # Les codes secrets ne doivent jamais apparaître dans le journal.
        audit_model(
            Mission, module="MISSION", exclure=("code_expediteur", "code_destinataire")
        )
        enregistrer(
            EntreeMenu(
                "Missions", "missions:liste", "fa-truck-fast", permissions.CONSULTATION, ordre=10
            )
        )
