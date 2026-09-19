from django.apps import AppConfig


class FuelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fuel'
    label = 'fuel'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(
            EntreeMenu(
                "Carburant", "fuel:liste", "fa-gas-pump", permissions.CONSULTATION, ordre=45
            )
        )
