"""Génération automatique des écritures comptables depuis les événements de facturation.

Souscrit aux signaux **bloquants** de ``billing`` (``facture_a_comptabiliser``, envoyé en
``send()`` brut, pas ``emettre()``/``send_robust``) : si l'écriture ne peut pas s'équilibrer,
l'opération d'origine (ici la validation de la facture) est annulée plutôt que de laisser un
grand livre incomplet — cahier-des-charges.md:340.
"""

from django.dispatch import receiver

from apps.billing.signals import facture_a_comptabiliser

from . import services


@receiver(facture_a_comptabiliser)
def comptabiliser_une_facture_validee(sender, facture, **kwargs) -> None:
    services.comptabiliser_facture_validee(facture)
