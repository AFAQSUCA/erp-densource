from django.apps import AppConfig


class SauvegardesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sauvegardes"
    label = "sauvegardes"
    verbose_name = "Sauvegardes"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(EntreeMenu("Sauvegardes", "sauvegardes:liste", "fa-database", permissions.CONSULTATION, ordre=91))

        from apps.core.mesures import enregistrer_jauge

        from .services import age_derniere_sauvegarde

        enregistrer_jauge(
            "erp_sauvegarde_age_secondes", "Âge de la dernière sauvegarde réussie (service `sauvegarde`).",
            age_derniere_sauvegarde,
        )
