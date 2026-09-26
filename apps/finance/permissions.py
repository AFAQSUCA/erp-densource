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
# pour la validation d'une facture). Retour réunion : la RH fait tout ce que fait la FINANCES, y
# compris exécuter l'ordre de décaissement ; la DIRECTION a la même largeur que l'ADMIN en saisie
# mais ne remplace jamais la FINANCES/RH sur l'exécution (contrôle strict conservé).
DEMANDE_CONSULTATION = frozenset(
    {Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.RH}
)
DEMANDE_SAISIE = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
DEMANDE_VALIDATION = frozenset({Role.DIRECTION})
ORDRE_EXECUTION = frozenset({Role.FINANCES, Role.RH})
ENVELOPPE_VALIDATION = frozenset({Role.DIRECTION})
