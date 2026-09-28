"""Qui peut consulter, saisir, valider et clôturer la comptabilité.

Cohérent avec ``billing.permissions`` : la RH fait tout ce que fait la FINANCES, la DIRECTION a
la même largeur que l'ADMIN — sauf sur la validation d'une écriture manuelle et la clôture d'un
exercice, strictement réservées à la DIRECTION (comme la validation d'une facture, jamais
l'ADMIN/un superutilisateur à sa place : ce sont les deux seuls contrôles comptables a posteriori
sur une saisie humaine).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})

# Saisie d'une écriture manuelle (opérations diverses, P4) : créer le brouillon, y ajouter/retirer
# des lignes, l'abandonner.
SAISIE_OD = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
# Validation d'une écriture manuelle : DIRECTION seule, contrôle strict.
VALIDATION_OD = frozenset({Role.DIRECTION})
# Clôture d'un exercice comptable (P5) : DIRECTION seule, contrôle strict.
CLOTURE_EXERCICE = frozenset({Role.DIRECTION})
# Gestion du plan comptable (créer/modifier un compte, Lot F autonomie comptable) : même largeur
# que la saisie d'une écriture manuelle, pas de contrôle Direction a posteriori (ce n'est pas une
# transaction financière, seulement le paramétrage du référentiel).
GESTION_PLAN_COMPTABLE = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
