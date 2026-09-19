from django.apps import AppConfig


class GarageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.garage'
    label = 'garage'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model
        from apps.fleet.sections import DETAIL_VEHICULE

        from . import permissions, sections
        from .models import OrdreReparation

        audit_model(OrdreReparation, module="PARC_AUTO")
        enregistrer(
            EntreeMenu(
                "Garage", "garage:liste", "fa-screwdriver-wrench", permissions.CONSULTATION, ordre=40
            )
        )
        DETAIL_VEHICULE.enregistrer(sections.section_maintenance)
