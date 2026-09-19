"""Événements du cycle de facturation (souscrits par ``notifications``).

Émis dans la transaction de l'action, avec ``send_robust`` : un récepteur en erreur ne doit
jamais empêcher une validation de facture.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# La facture vient d'être soumise à la DIRECTION. Argument : ``facture``.
facture_a_valider = Signal()
# La DIRECTION vient de valider la facture (numéro attribué). Argument : ``facture``.
facture_validee = Signal()
# La DIRECTION a refusé la facture (retour en brouillon). Arguments : ``facture``, ``motif``.
facture_refusee = Signal()


def emettre(signal: Signal, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    from .models import Facture

    for recepteur, resultat in signal.send_robust(sender=Facture, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
