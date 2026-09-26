"""Qui peut consulter et faire bouger le stock.

Cahier-des-charges.md:44-55 : le PARCAUTO gère les « mouvements de stock,
inventaires » ; la DIRECTION est en « lecture seule sur Parc Auto ». L'ADMIN a tous
les droits.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
