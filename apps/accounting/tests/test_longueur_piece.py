"""La référence de pièce d'une écriture recopie celle de la pièce d'origine : elle doit être au moins aussi
longue (audit AUD-22 : 30 caractères contre 100, erreur 500 sur PostgreSQL)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.models import EcritureComptable
from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, Depense, Facture, ModePaiement
from apps.billing.tests.helpers import finances
from apps.finance.models import LigneReleve, MouvementManuel

pytestmark = pytest.mark.django_db


def _longueur(modele, champ):
    return modele._meta.get_field(champ).max_length


@pytest.mark.parametrize(
    "modele, champ",
    [(Depense, "reference"), (MouvementManuel, "reference"), (LigneReleve, "reference"), (Facture, "numero")],
)
def test_la_piece_d_une_ecriture_contient_toute_reference_d_origine(modele, champ):
    assert _longueur(EcritureComptable, "piece_reference") >= _longueur(modele, champ)


def test_une_depense_a_la_reference_de_100_caracteres_est_comptabilisee_en_entier():
    reference = "BON-" + "7" * 96

    depense = billing_services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=date(2026, 9, 1), libelle="Péage",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES, reference=reference,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.piece_reference == reference
