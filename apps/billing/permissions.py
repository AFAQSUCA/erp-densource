"""Qui peut consulter, préparer et valider les factures.

Cahier-des-charges.md:44-55 : FINANCES = « validation factures, saisie dépenses/entrées,
suivi trésorerie » ; DIRECTION = « accès financier (lecture + validation) » ;
architecture.md:432 : « Rôle FINANCES + validation DIRECTION ». Décision retenue : FINANCES
prépare la facture et la soumet, la DIRECTION la valide (ce qui l'émet). L'ADMIN a accès à
tout mais ne valide pas : une facture est toujours validée par la DIRECTION. La RH, le
PARCAUTO, le chargé clientèle et le chauffeur n'ont pas accès.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES})
SAISIE = frozenset({Role.ADMIN, Role.FINANCES})  # préparer, règlements, dépenses
VALIDATION = frozenset({Role.DIRECTION})

# Devis (R5) : le chargé clientèle fixe le prix, la FINANCES (et la DIRECTION au-delà d'un
# seuil, R1 fusionnée) le valide — jamais la même personne des deux côtés.
PROFORMA_CONSULTATION = frozenset(
    {Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.CHARGE_CLIENTELE}
)
PROFORMA_SAISIE = frozenset({Role.ADMIN, Role.CHARGE_CLIENTELE})
PROFORMA_VALIDATION_FINANCES = frozenset({Role.FINANCES})
PROFORMA_VALIDATION_DIRECTION = frozenset({Role.DIRECTION})
