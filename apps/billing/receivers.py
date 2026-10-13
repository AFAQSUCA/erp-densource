"""Réactions de la facturation aux événements des autres apps (``billing`` ne les appelle pas : elles émettent un
signal, souscrit ici)."""

from django.dispatch import receiver

from apps.missions.signals import mission_annulee

from .models import StatutProforma


@receiver(mission_annulee)
def annuler_le_devis_d_une_mission_annulee(sender, mission, **kwargs):
    """Le devis accepté qui avait créé la mission est annulé avec elle (décision du 13/10/2026, audit AUD-02). Une
    mission annulée n'a pas de facture : elle n'est facturable qu'une fois livrée."""
    proforma = mission.proforma
    if proforma is not None and proforma.statut != StatutProforma.ANNULEE:
        proforma.statut = StatutProforma.ANNULEE
        proforma.save(update_fields=["statut", "updated_at"])
