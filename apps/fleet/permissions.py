"""Qui peut consulter et modifier la flotte.

Cahier-des-charges.md:44-55 : la DIRECTION assure la « gestion flotte + chauffeurs »
et le PARCAUTO la « gestion technique véhicules, renouvellement pièces
administratives ». L'ADMIN a tous les droits. Les autres rôles n'ont pas accès au
parc auto (FINANCES : « pas d'accès parc auto » ; CHARGE_CLIENTELE et RH : idem).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
# Corriger le compteur d'un camion (faute de frappe qui l'a gonflé : il ne recule jamais autrement) : l'ADMIN
# seulement, motif obligatoire, tracé dans le journal d'audit.
CORRECTION_COMPTEUR = frozenset({Role.ADMIN})
