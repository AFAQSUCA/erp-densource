"""Qui peut faire quoi sur une mission.

Rôles du CDC (cahier-des-charges.md:44-55) : la DIRECTION crée, affecte et suit
les missions ; le chargé clientèle valide le passage en « Planifiée »
(architecture.md:241). L'ADMIN a tous les droits. Ces ensembles serviront aussi
aux permissions DRF de l'API (étape 6).

Le chauffeur exécute ses missions depuis l'espace mobile (étape 6) : il n'a pas
d'accès à ces écrans.
"""

from __future__ import annotations

from apps.accounts.models import Role

from .models import Mission, StatutMission

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
CREATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
PLANIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
AFFECTATION = frozenset({Role.ADMIN, Role.DIRECTION})
# Séparation des tâches (avenant-separation-des-taches.md § R3) : modifier une mission déjà créée est
# plus restreint que la créer — le chargé clientèle crée, seules DIRECTION et ADMIN modifient ensuite.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION})
# Le départ peut être lancé depuis le back-office (suivi) ; le chauffeur le fait lui-même depuis le mobile.
SUIVI_TERRAIN = frozenset({Role.ADMIN, Role.DIRECTION})
# Récupération et livraison se confirment par un code secret que seul le chauffeur affecté saisit ou
# scanne (espace mobile : une mission d'un autre chauffeur y est introuvable). Depuis le back-office,
# seul l'ADMIN peut le faire à sa place (correction, panne du téléphone) : ni la DIRECTION ni le
# chargé clientèle, qui voient pourtant les codes pour les communiquer.
CODES_TERRAIN = frozenset({Role.ADMIN})
CLOTURE = frozenset({Role.ADMIN, Role.DIRECTION})

# Les codes sont à communiquer à l'expéditeur et au destinataire : ils ne sont
# visibles que des rôles qui gèrent la relation client.
VOIR_CODES = CONSULTATION


def actions_disponibles(utilisateur, mission: Mission) -> dict[str, bool]:
    """Actions proposables à ``utilisateur`` sur ``mission`` (statut + rôle)."""
    role = utilisateur.role_effectif
    statut = mission.statut
    return {
        "planifier": statut == StatutMission.BROUILLON and role in PLANIFICATION,
        "affecter": statut == StatutMission.PLANIFIEE and role in AFFECTATION,
        "demarrer": statut == StatutMission.AFFECTEE and role in SUIVI_TERRAIN,
        "recuperation": statut == StatutMission.EN_COURS_DEPART
        and role in CODES_TERRAIN,
        "livraison": statut == StatutMission.EN_COURS_COLIS_RECUPERE
        and role in CODES_TERRAIN,
        "cloturer": statut == StatutMission.LIVREE and role in CLOTURE,
    }


def codes_visibles(utilisateur, mission: Mission) -> dict[str, str | None]:
    """Codes encore utiles à communiquer, ``None`` quand ils ne le sont plus.

    Le code expéditeur ne sert que jusqu'à la récupération du colis, le code
    destinataire que jusqu'à la livraison.
    """
    if utilisateur.role_effectif not in VOIR_CODES:
        return {"expediteur": None, "destinataire": None}
    avant_recuperation = mission.statut in (
        StatutMission.BROUILLON,
        StatutMission.PLANIFIEE,
        StatutMission.AFFECTEE,
        StatutMission.EN_COURS_DEPART,
    )
    avant_livraison = mission.statut not in (
        StatutMission.LIVREE,
        StatutMission.CLOTUREE,
    )
    return {
        "expediteur": mission.code_expediteur if avant_recuperation else None,
        "destinataire": mission.code_destinataire if avant_livraison else None,
    }
