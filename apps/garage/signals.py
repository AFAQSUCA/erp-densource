"""Événements des signalements du chauffeur (souscrits par ``notifications``).

Émis avec ``send_robust`` : un récepteur en erreur ne doit jamais empêcher le chauffeur de
signaler une panne.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Un incident vient d'être signalé. Argument : ``incident``.
incident_signale = Signal()
# Une check-list vient d'être enregistrée avec au moins un point KO. Argument : ``checklist``.
checklist_anomalie = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
