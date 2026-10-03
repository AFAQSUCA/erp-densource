"""Génération automatique des écritures comptables depuis les événements de facturation et de
trésorerie.

Souscrit aux signaux **bloquants** de ``billing`` et ``finance`` (``facture_a_comptabiliser``,
``reglement_a_comptabiliser``, ``depense_a_comptabiliser``, ``depense_mode_a_reclasser``,
``mouvement_a_comptabiliser``, envoyés en ``send()`` brut, pas ``emettre()``/``send_robust``) :
si l'écriture ne peut pas s'équilibrer, l'opération d'origine (validation de la facture,
enregistrement du règlement ou du mouvement, dépense automatique, correction du mode) est
annulée plutôt que de laisser un grand livre incomplet — cahier-des-charges.md:340.
"""

from django.dispatch import receiver

from apps.billing.signals import (
    depense_a_comptabiliser,
    depense_mode_a_reclasser,
    facture_a_comptabiliser,
    reglement_a_comptabiliser,
    reglement_annule,
)
from apps.finance.signals import mouvement_a_comptabiliser, mouvement_annule

from . import services


@receiver(facture_a_comptabiliser)
def comptabiliser_une_facture_validee(sender, facture, **kwargs) -> None:
    services.comptabiliser_facture_validee(facture)


@receiver(reglement_a_comptabiliser)
def comptabiliser_un_reglement_recu(sender, reglement, **kwargs) -> None:
    services.comptabiliser_un_reglement(reglement)


@receiver(depense_a_comptabiliser)
def comptabiliser_une_depense(sender, depense, **kwargs) -> None:
    services.comptabiliser_une_depense_automatique(depense)


@receiver(depense_mode_a_reclasser)
def reclasser_le_mode_d_une_depense(sender, depense, ancien_mode, **kwargs) -> None:
    services.reclasser_mode_depense(depense, ancien_mode)


@receiver(mouvement_a_comptabiliser)
def comptabiliser_un_mouvement(sender, mouvement, **kwargs) -> None:
    services.comptabiliser_un_mouvement_manuel(mouvement)


@receiver(reglement_annule)
def contre_passer_un_reglement_annule(sender, reglement, **kwargs) -> None:
    services.contre_passer_origine("REGLEMENT", reglement.pk, motif=reglement.motif_annulation)


@receiver(mouvement_annule)
def contre_passer_un_mouvement_annule(sender, mouvement, **kwargs) -> None:
    services.contre_passer_origine("MOUVEMENT", mouvement.pk, motif=mouvement.motif_annulation)
