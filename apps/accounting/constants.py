"""Numéros de comptes utilisés par le code (ancrages internes, pas de saisie utilisateur).

Le plan comptable complet (``migrations/0002_plan_comptable_seed.py``) est une liste de travail
à valider par un expert-comptable avant mise en production (aucun cabinet externe consulté à ce
stade) ; seuls les comptes ci-dessous sont mobilisés par la Phase 1.
"""

from apps.billing.models import CategorieDepense, CompteTresorerie
from apps.finance.models import NatureMouvement

from .models import Journal

COMPTE_CLIENTS = "411000"
COMPTE_VENTES_TRANSPORT = "706100"
COMPTE_TVA_COLLECTEE = "443300"
COMPTE_TVA_DEDUCTIBLE = "445200"
COMPTE_RESULTAT = "120000"  # résultat de l'exercice : reçoit le solde des comptes 6/7 à la clôture

# billing.models.CategorieDepense -> Compte.numero — les 4 catégories automatiques
# (billing.models.CATEGORIES_AUTOMATIQUES) et les 4 catégories de saisie manuelle sont toutes
# mobilisées (avenant-comptabilite-autonomie.md § Lot C). Péages rattachés aux frais de mission
# (comptes de déplacement) ; Entretien au même compte que la main-d'œuvre des OR (prestataires
# extérieurs) ; Frais administratifs et Autre au compte générique de charges diverses — mapping
# de départ, à valider par un expert-comptable comme le reste du plan comptable.
CATEGORIE_DEPENSE_VERS_COMPTE = {
    CategorieDepense.CARBURANT: "605100",
    CategorieDepense.PIECES: "605800",
    CategorieDepense.MAINTENANCE: "624100",
    CategorieDepense.FRAIS_MISSION: "628100",
    CategorieDepense.PEAGES: "628100",
    CategorieDepense.ENTRETIEN: "624100",
    CategorieDepense.FRAIS_ADMIN: "658000",
    CategorieDepense.AUTRE: "658000",
}

# finance.models.NatureMouvement -> Compte.numero (contrepartie du mouvement manuel de trésorerie).
NATURE_MOUVEMENT_VERS_COMPTE = {
    NatureMouvement.SOLDE_OUVERTURE: "101000",
    NatureMouvement.APPORT: "101000",
    NatureMouvement.RETRAIT: "108000",
    NatureMouvement.FRAIS_BANCAIRE: "631000",
    NatureMouvement.AUTRE: "658000",
}

# apps.billing.models.CompteTresorerie -> Compte.numero (Mobile Money reste fusionné pour les
# 3 opérateurs, cf. avenant-comptabilite-syscohada.md).
COMPTE_TRESORERIE_VERS_COMPTE = {
    CompteTresorerie.BANQUE: "521000",
    CompteTresorerie.CAISSE: "571000",
    CompteTresorerie.MOBILE_MONEY: "521900",
}

# apps.billing.models.CompteTresorerie -> Journal : le Mobile Money, dématérialisé, n'a pas de
# journal auxiliaire dédié dans les 5 journaux SYSCOHADA standards — rattaché à la Banque.
COMPTE_TRESORERIE_VERS_JOURNAL = {
    CompteTresorerie.BANQUE: Journal.BANQUE,
    CompteTresorerie.CAISSE: Journal.CAISSE,
    CompteTresorerie.MOBILE_MONEY: Journal.BANQUE,
}
