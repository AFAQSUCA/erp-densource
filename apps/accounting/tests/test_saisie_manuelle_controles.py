"""Saisie manuelle d'une opération diverse : sens contrôlé, comptes revérifiés à la validation — audit AV-09."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import CompteInconnu, EcritureNonEquilibree
from apps.accounting.models import Compte, LigneEcriture, SensEcriture, StatutEcriture
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory

pytestmark = pytest.mark.django_db


def _brouillon():
    return services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Reclassement")


def test_un_sens_autre_que_debit_ou_credit_est_refuse():
    ecriture, compte = _brouillon(), CompteFactory()

    with pytest.raises(EcritureNonEquilibree, match="débit ou crédit"):
        services.ajouter_ligne_manuelle(ecriture, finances(), compte=compte.numero, sens="AUTRE", montant=Decimal("500"))

    assert not LigneEcriture.objects.filter(ecriture=ecriture).exists()


def test_un_compte_desactive_apres_la_saisie_bloque_la_validation():
    ecriture, debit, credit = _brouillon(), CompteFactory(), CompteFactory()
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=debit.numero, sens=SensEcriture.DEBIT, montant=Decimal("500"))
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=credit.numero, sens=SensEcriture.CREDIT, montant=Decimal("500"))
    services.modifier_compte(credit, finances(), libelle=credit.libelle, actif=False)

    with pytest.raises(CompteInconnu, match=credit.numero):
        services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.BROUILLON and not ecriture.numero


def test_une_ecriture_correcte_se_valide_toujours():
    ecriture, debit, credit = _brouillon(), CompteFactory(), CompteFactory()
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=debit.numero, sens=SensEcriture.DEBIT, montant=Decimal("500"))
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=credit.numero, sens=SensEcriture.CREDIT, montant=Decimal("500"))

    services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE


# --- pas d'opération diverse sur un compte de trésorerie (décision du 13/10/2026, audit AV-10) ---


@pytest.mark.parametrize("compte", ["521000", "571000", "521900"])
def test_une_operation_diverse_ne_touche_pas_un_compte_de_tresorerie(compte):
    """Sinon la comptabilité et l'écran Trésorerie ne montrent plus le même solde."""
    ecriture = _brouillon()

    with pytest.raises(CompteInconnu, match="Trésorerie"):
        services.ajouter_ligne_manuelle(ecriture, finances(), compte=compte, sens=SensEcriture.DEBIT, montant=Decimal("500"))

    assert not LigneEcriture.objects.filter(ecriture=ecriture).exists()


def test_un_brouillon_saisi_avant_la_regle_est_refuse_a_la_validation():
    ecriture, autre = _brouillon(), CompteFactory()
    LigneEcriture.objects.create(
        ecriture=ecriture, compte=Compte.objects.get(numero="571000"), sens=SensEcriture.DEBIT, montant=Decimal("500")
    )
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=autre.numero, sens=SensEcriture.CREDIT, montant=Decimal("500"))

    with pytest.raises(CompteInconnu, match="Trésorerie"):
        services.valider_ecriture_manuelle(ecriture, direction())
