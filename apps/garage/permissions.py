"""Qui peut consulter et gérer le garage.

Cahier-des-charges.md:44-55 : le PARCAUTO a la « gestion technique véhicules » et
gère les « OR ». L'ADMIN a tous les droits. La DIRECTION, à l'origine en « lecture
seule sur Parc Auto », agit désormais aussi : retour d'une réunion entreprise, elle a
la même largeur que l'ADMIN sur la saisie/modification (ouvrir/clôturer un OR,
immobiliser un camion ou le remettre en service).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
