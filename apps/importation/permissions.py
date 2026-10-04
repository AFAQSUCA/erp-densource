"""Qui peut importer les données de l'entreprise depuis Excel : l'administrateur (un superutilisateur agit en ADMIN)."""

from apps.accounts.models import Role

IMPORT_DONNEES = frozenset({Role.ADMIN})
