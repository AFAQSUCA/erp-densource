"""Qui peut consulter et alimenter la trésorerie.

Mêmes droits que la facturation (cahier-des-charges.md:53) : FINANCES saisit et suit la
trésorerie, la DIRECTION consulte, l'ADMIN a tous les accès.
"""

from apps.billing.permissions import CONSULTATION, SAISIE

__all__ = ["CONSULTATION", "SAISIE"]
