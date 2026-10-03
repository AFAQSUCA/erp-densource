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

# Un mouvement manuel de trésorerie vient d'être enregistré : à comptabiliser (même principe que
# ``billing.signals.facture_a_comptabiliser`` — ``send()`` **brut**, pas ``send_robust`` : une
# écriture qui échoue à s'équilibrer annule l'enregistrement plutôt que de laisser un mouvement de
# trésorerie non tracé). Argument : ``mouvement``.
mouvement_a_comptabiliser = Signal()

# Un mouvement manuel vient d'être annulé (``annuler_mouvement``) : son écriture comptable doit être
# contre-passée. ``send()`` brut, même principe que ``mouvement_a_comptabiliser``. Argument :
# ``mouvement`` (déjà supprimé logiquement, ``motif_annulation`` renseigné).
mouvement_annule = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
