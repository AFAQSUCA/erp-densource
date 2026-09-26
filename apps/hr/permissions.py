"""Qui peut consulter et gérer le personnel et les congés.

Cahier-des-charges.md:44-55 : la RH a la « gestion complète des employés » et les
« congés/absences » ; l'ADMIN a tous les droits. La DIRECTION, à l'origine en
« lecture seule sur RH », modifie désormais aussi : retour d'une réunion entreprise,
elle a la même largeur que l'ADMIN sur la saisie/modification. Les autres rôles
n'accèdent pas à la fiche du personnel.

Les congés sont ouverts à tout employé qui a un compte (il demande son congé, et son
supérieur hiérarchique valide en N1) : le droit de décision ne dépend pas du rôle mais de
la hiérarchie, il est contrôlé par ``services.py``. Le chauffeur passera par l'espace
mobile (étape 6).
"""

from apps.accounts.models import Role

PERSONNEL_CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
PERSONNEL_MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})

# Voit les congés de tous les employés (les autres ne voient que les leurs et ceux
# qu'ils ont à valider).
CONGES_TOUS = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
CONGES_ACCES = frozenset(
    {Role.ADMIN, Role.DIRECTION, Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES}
)
