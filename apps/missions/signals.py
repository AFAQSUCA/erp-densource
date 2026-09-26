"""Événements des missions (souscrits par ``notifications`` et, pour ``frais_mission_confirme``,
par ``finance``).
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# La mission vient de démarrer : « en cours de route (départ) » (cahier-des-charges.md:136-137).
# Argument : ``mission`` (instance à jour).
mission_demarree = Signal()

# La mission vient de passer « Affectée » : mouvement de caisse probable (R4). Argument : ``mission``.
mission_affectee = Signal()

# Un imprévu vient d'être déclaré par le chauffeur, avec sa preuve. Argument : ``frais``.
frais_mission_declare = Signal()
# Le Parc Auto vient de valider un imprévu (première validation) : la Finance doit confirmer.
# Argument : ``frais``.
frais_mission_valide_parcauto = Signal()
# Une ligne vient d'être rejetée (Parc Auto ou Finance selon l'étape). Argument : ``frais``.
frais_mission_rejete = Signal()
# Une ligne vient d'être confirmée : mouvement de trésorerie réel. Argument : ``frais``. Émis en
# dehors de ``emettre`` (``send`` brut, comme ``garage.or_cloture``) : si la dépense automatique
# ne peut pas s'écrire, la confirmation est annulée plutôt que de laisser une sortie d'argent non
# comptée. Souscrit par ``finance.receivers``.
frais_mission_confirme = Signal()


def emettre(signal: Signal, **arguments) -> None:
    """Émet un signal en journalisant (sans propager) les erreurs des récepteurs."""
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
