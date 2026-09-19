from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.customers'
    label = 'customers'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Client

        audit_model(Client, module="CLIENTELE")
        enregistrer(
            EntreeMenu(
                "Clients", "customers:liste", "fa-handshake", permissions.CONSULTATION, ordre=15
            )
        )
