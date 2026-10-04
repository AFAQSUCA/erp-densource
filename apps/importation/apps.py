from django.apps import AppConfig


class ImportationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.importation"
    label = "importation"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(
            EntreeMenu("Import de données", "importation:importer", "fa-file-import", permissions.IMPORT_DONNEES, ordre=88)
        )
