from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    label = 'inventory'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.garage.sections import DETAIL_OR

        from . import permissions, sections

        DETAIL_OR.enregistrer(sections.section_pieces)
        enregistrer(
            EntreeMenu(
                "Stock", "inventory:articles", "fa-boxes-stacked", permissions.CONSULTATION, ordre=50
            )
        )
