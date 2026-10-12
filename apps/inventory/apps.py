from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    label = 'inventory'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model
        from apps.garage.sections import DETAIL_OR

        from . import permissions, sections
        from .models import Article

        # Audit M1-68 : fiche article (seuil minimal, PUMP...). Les mouvements de stock sont déjà append-only.
        audit_model(Article, module="STOCK")
        DETAIL_OR.enregistrer(sections.section_pieces)
        enregistrer(
            EntreeMenu(
                "Stock", "inventory:articles", "fa-boxes-stacked", permissions.CONSULTATION, ordre=50
            )
        )
