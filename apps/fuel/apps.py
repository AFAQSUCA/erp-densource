from django.apps import AppConfig


class FuelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fuel'
    label = 'fuel'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Plein

        audit_model(Plein, module="CARBURANT")  # audit M1-67 : un plein corrigé ne passait pas au journal
        enregistrer(
            EntreeMenu(
                "Carburant", "fuel:liste", "fa-gas-pump", permissions.CONSULTATION, ordre=45
            )
        )
