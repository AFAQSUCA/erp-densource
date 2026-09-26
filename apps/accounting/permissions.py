"""Qui peut consulter la comptabilité.

Phase 1 : lecture seule (aucune saisie manuelle avant l'introduction des opérations diverses).
Cohérent avec ``billing.permissions.CONSULTATION`` : la RH fait tout ce que fait la FINANCES, la
DIRECTION a la même largeur que l'ADMIN.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
