"""Événements des dépenses pré-approuvées du parc auto (R2), souscrits par ``notifications``.

Émis avec ``send_robust`` : un récepteur en erreur ne doit jamais empêcher une décision de la
direction ou de la finance.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Une demande vient d'être soumise (manuelle) ou ouverte automatiquement (dépassement d'enveloppe).
# Argument : ``demande``.
demande_soumise = Signal()
# La direction vient de valider ou refuser une demande. Argument : ``demande``.
demande_decidee = Signal()
# Une demande validée (manuelle) vient de générer un ordre à exécuter. Argument : ``ordre``.
ordre_a_executer = Signal()
# Le montant réel dépasse de plus de 10 % le montant validé : l'ordre revient à la direction.
# Argument : ``ordre``.
ordre_depassement = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
