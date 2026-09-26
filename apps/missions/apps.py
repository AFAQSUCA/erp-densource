from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.missions'
    label = 'missions'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from apps.customers.sections import DETAIL_CLIENT
        from apps.hr.sections import DETAIL_CONGE

        from django.db.models.signals import post_save

        from . import permissions, sections, temps_reel
        from .models import FraisMission, Mission

        # Les codes secrets ne doivent jamais apparaître dans le journal.
        audit_model(
            Mission, module="MISSION", exclure=("code_expediteur", "code_destinataire")
        )
        audit_model(FraisMission, module="FINANCES")
        # Suivi en direct : tout changement d'une mission est diffusé aux écrans ouverts.
        post_save.connect(
            temps_reel.diffuser_apres_enregistrement, sender=Mission, dispatch_uid="missions.suivi_en_direct"
        )
        DETAIL_CONGE.enregistrer(sections.section_alerte_conge)
        DETAIL_CLIENT.enregistrer(sections.section_missions_client)
        enregistrer(
            EntreeMenu(
                "Missions", "missions:liste", "fa-truck-fast", permissions.CONSULTATION, ordre=10
            )
        )
        enregistrer(
            EntreeMenu(
                "Frais de mission", "missions:frais_liste", "fa-money-bill-transfer",
                permissions.FRAIS_CONSULTATION, ordre=63,
            )
        )
