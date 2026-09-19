from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    label = 'inventory'

    def ready(self):
        from apps.garage.sections import DETAIL_OR

        from . import sections

        DETAIL_OR.enregistrer(sections.section_pieces)
