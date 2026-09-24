"""Suivi des missions en direct : diffusion d'un changement à tous les écrans ouverts.

Chaque enregistrement d'une mission (création, planification, affectation, départ, récupération,
livraison, clôture — y compris la saisie du code par le chauffeur depuis son téléphone) envoie un court
message au groupe ``GROUPE_SUIVI`` de la couche de messages (Redis en production). Les consommateurs
WebSocket (``consumers.MissionSuiviConsumer``), connectés depuis la fiche et la liste des missions, le
relaient au navigateur, qui rafraîchit l'écran (``static/js/suivi-missions.js``).

Le message ne contient jamais de code secret : seulement de quoi savoir quelle mission a changé.
La diffusion part **après** la validation de la transaction (l'écran qui se rafraîchit relit alors
l'état définitif) et ne fait jamais échouer l'opération métier : si Redis est indisponible, le chauffeur
confirme quand même sa livraison, l'écran du bureau se mettra à jour à son prochain rafraîchissement.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

GROUPE_SUIVI = "suivi_missions"


def message_mission(mission) -> dict:
    return {
        "id": mission.pk,
        "numero": mission.numero,
        "statut": mission.statut,
        "statut_libelle": str(mission.get_statut_display()),
    }


def diffuser(mission) -> None:
    """Prévient les écrans ouverts que ``mission`` a changé (à appeler une fois la transaction validée)."""
    try:
        couche = get_channel_layer()
        if couche is not None:
            async_to_sync(couche.group_send)(
                GROUPE_SUIVI, {"type": "mission.maj", "donnees": message_mission(mission)}
            )
    except Exception:  # noqa: BLE001 - le temps réel est un confort, jamais une condition du métier
        logger.exception("Diffusion du suivi de la mission %s impossible", getattr(mission, "pk", "?"))


def diffuser_apres_enregistrement(sender, instance, **kwargs) -> None:
    """Récepteur de ``post_save`` (branché dans ``MissionsConfig.ready``)."""
    transaction.on_commit(lambda: diffuser(instance))
