"""Événements du workflow de congés (souscrits par ``notifications``).

Émis dans la transaction de l'action, avec ``send_robust`` : un récepteur en erreur ne doit
jamais empêcher une validation de congé.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Une demande vient d'être déposée. Argument : ``conge``.
conge_soumis = Signal()
# La validation N1 vient d'être donnée. Argument : ``conge``.
conge_valide_n1 = Signal()
# Décision finale : ``decision`` vaut DECISION_APPROUVE, DECISION_REFUSE ou DECISION_ANNULE.
# Arguments : ``conge``, ``decision``, ``acteur``.
conge_decide = Signal()
# Report du solde d'un congé en cours demandé par l'employé (avenant § R7). Argument : ``report``.
report_demande = Signal()
# Décision de la RH sur une demande de report. ``decision`` vaut DECISION_APPROUVE ou DECISION_REFUSE.
# Arguments : ``report``, ``decision``, ``acteur``.
report_decide = Signal()

DECISION_APPROUVE, DECISION_REFUSE, DECISION_ANNULE = "APPROUVE", "REFUSE", "ANNULE"


def emettre(signal: Signal, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    from .models import Conge

    for recepteur, resultat in signal.send_robust(sender=Conge, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
