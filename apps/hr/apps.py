from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hr'
    label = 'hr'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import (
            AttributionConge,
            Conge,
            JourFerie,
            Personnel,
            ReportConge,
            SortiePersonnel,
            ValidationConge,
        )

        audit_model(Personnel, module="RH")
        audit_model(SortiePersonnel, module="RH")
        audit_model(Conge, module="RH", validation=("statut", ("VALIDATION_N1", "APPROUVE")))
        audit_model(AttributionConge, module="RH")
        # Audit M1-67 : décisions N1/N2, reports de congé, jours fériés (ils changent le décompte des jours).
        audit_model(ValidationConge, module="RH")
        audit_model(ReportConge, module="RH", validation=("statut", ("APPROUVE",)))
        audit_model(JourFerie, module="RH")
        enregistrer(
            EntreeMenu(
                "Personnel", "hr:personnel_liste", "fa-users", permissions.PERSONNEL_CONSULTATION,
                ordre=25,
            )
        )
        enregistrer(
            EntreeMenu(
                "Congés", "hr:conges_liste", "fa-umbrella-beach", permissions.CONGES_ACCES,
                ordre=26,
            )
        )
