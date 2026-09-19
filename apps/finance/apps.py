from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    label = 'finance'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import MouvementManuel

        audit_model(MouvementManuel, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Trésorerie", "finance:tresorerie", "fa-wallet", permissions.CONSULTATION, ordre=62
            )
        )
