"""Qui peut consulter et saisir les pleins.

Le CDC réserve la saisie du carburant au CHAUFFEUR depuis l'espace mobile
(cahier-des-charges.md:54, étape 6). Côté back-office, le suivi de la consommation
relève du parc auto : PARCAUTO et ADMIN saisissent (à partir des tickets), la
DIRECTION consulte en « lecture seule sur Parc Auto » (cahier-des-charges.md:49).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
