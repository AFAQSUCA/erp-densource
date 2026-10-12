from django.apps import AppConfig


class ParametresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.parametres"
    label = "parametres"
    verbose_name = "Paramètres"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Parametres

        audit_model(Parametres, module="PARAMETRES", exclure=("modifie_le", "modifie_par"))
        enregistrer(EntreeMenu("Paramètres", "parametres:modifier", "fa-sliders", permissions.MODIFICATION, ordre=90))
