"""Qui consulte et modifie les paramètres : l'ADMIN (cahier-des-charges.md:48) et la DIRECTION (décision du
12/10/2026, avenant-parametres.md). Un superutilisateur agit en ADMIN."""

from apps.accounts.models import Role

MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION})
