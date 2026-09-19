"""Qui peut consulter et gérer les chauffeurs.

Cahier-des-charges.md:44-55 : la DIRECTION assure la « gestion flotte + chauffeurs » ;
la RH a la « gestion complète des employés » (embauche, licenciement), dont les
chauffeurs, qui sont des employés (cahier-des-charges.md:105-108). L'ADMIN a tous les
droits. Le PARCAUTO, les FINANCES et la CHARGE_CLIENTELE n'ont pas accès.

Suspendre ou désactiver un chauffeur relève des mêmes rôles que la gestion de la fiche.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
