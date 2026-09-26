"""Qui peut consulter et alimenter la trésorerie.

Mêmes droits que la facturation (cahier-des-charges.md:53) : FINANCES saisit et suit la
trésorerie, la DIRECTION consulte, l'ADMIN a tous les accès.
"""

from apps.accounts.models import Role
from apps.billing.permissions import CONSULTATION, SAISIE

__all__ = [
    "CONSULTATION", "SAISIE",
    "DEMANDE_CONSULTATION", "DEMANDE_SAISIE", "DEMANDE_VALIDATION", "ORDRE_EXECUTION", "ENVELOPPE_VALIDATION",
]

# Dépenses du parc auto pré-approuvées (R2) : celui qui demande (Parc Auto) ou exécute (Finance)
# n'est jamais celui qui valide (Direction) — jamais l'ADMIN à sa place (contrôle strict, comme
# pour la validation d'une facture).
DEMANDE_CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES})
DEMANDE_SAISIE = frozenset({Role.ADMIN, Role.PARCAUTO})
DEMANDE_VALIDATION = frozenset({Role.DIRECTION})
ORDRE_EXECUTION = frozenset({Role.FINANCES})
ENVELOPPE_VALIDATION = frozenset({Role.DIRECTION})
