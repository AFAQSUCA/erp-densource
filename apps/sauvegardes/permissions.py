"""Qui suit et lance les sauvegardes : l'ADMIN (cahier-des-charges.md:48). Un superutilisateur agit en ADMIN."""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN})
LANCEMENT = frozenset({Role.ADMIN})
