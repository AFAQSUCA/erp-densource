"""Qui peut consulter et gérer le garage.

Cahier-des-charges.md:44-55 : le PARCAUTO a la « gestion technique véhicules » et
gère les « OR » ; la DIRECTION est en « lecture seule sur Parc Auto ». L'ADMIN a
tous les droits. Ouvrir ou clôturer un OR, immobiliser un camion ou le remettre en
service relèvent donc du PARCAUTO et de l'ADMIN.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.PARCAUTO})
