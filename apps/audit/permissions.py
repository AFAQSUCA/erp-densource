"""Qui peut consulter le journal d'audit.

Cahier-des-charges.md:81 : « Consultation ADMIN, lecture seule DIRECTION » — l'ADMIN et la DIRECTION
consultent tous deux le journal complet ; il n'y a de toute façon aucune écriture possible depuis
l'écran (append-only, ``AuditLog.save``/``delete`` verrouillés). Les autres rôles n'y ont pas accès.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION})
