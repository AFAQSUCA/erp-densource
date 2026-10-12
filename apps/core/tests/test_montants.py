"""Montants en FCFA saisis : entiers, refusés avec des centimes (audit AUD-05, M9-16, M9-24)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing_services
from apps.billing.exceptions import MontantInvalide, ReglementInvalide
from apps.billing.models import CategorieDepense, ModePaiement
from apps.billing.tests.helpers import emise, finances
from apps.core.exceptions import ErreurMetier
from apps.core.montants import exiger_montant_entier
from apps.customers.tests.factories import ClientFactory
from apps.finance import services as finance_services
from apps.finance.models import SensMouvement
from apps.missions import services as missions_services
from apps.missions import terrain
from apps.missions.exceptions import FraisInvalide, MissionError
from apps.missions.models import TypeFraisMission
from apps.missions.tests.test_services import _affectee

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("montant", ["1000", 1000, Decimal("1000.00"), "0"])
def test_un_montant_entier_est_accepte(montant):
    assert exiger_montant_entier(montant) == Decimal(montant)


@pytest.mark.parametrize("montant", ["1000.50", Decimal("0.01"), 999.9])
def test_un_montant_avec_des_centimes_est_refuse(montant):
    with pytest.raises(ErreurMetier, match="nombre entier de FCFA, sans centimes"):
        exiger_montant_entier(montant)


def test_l_erreur_est_celle_de_l_app_appelante_et_le_libelle_est_repris():
    with pytest.raises(MontantInvalide, match=r"Le prix doit être un nombre entier de FCFA.*\(12,50 saisi\)"):
        exiger_montant_entier("12.5", libelle="Le prix", erreur=MontantInvalide)


def test_un_reglement_avec_des_centimes_est_refuse_et_le_reste_ne_traine_pas_a_0_50():
    facture = emise(prix="1000000")  # TTC 1 180 000

    with pytest.raises(ReglementInvalide, match="sans centimes"):
        billing_services.enregistrer_reglement(
            facture, finances(), montant=Decimal("1179999.50"), mode=ModePaiement.VIREMENT, date_reglement=date.today()
        )
    billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.VIREMENT, date_reglement=date.today()
    )

    assert billing_services.reste_a_recouvrer(facture) == Decimal("0")


def test_une_depense_ou_sa_tva_avec_des_centimes_est_refusee():
    for montant, tva in ((Decimal("5000.25"), Decimal("0")), (Decimal("5900"), Decimal("900.10"))):
        with pytest.raises(MontantInvalide, match="sans centimes"):
            billing_services.enregistrer_depense(
                finances(), categorie=CategorieDepense.PEAGES, date_depense=date.today(), libelle="Péage",
                montant=montant, mode=ModePaiement.ESPECES, montant_tva=tva,
            )


def test_un_mouvement_de_tresorerie_avec_des_centimes_est_refuse():
    with pytest.raises(MontantInvalide, match="sans centimes"):
        finance_services.enregistrer_mouvement(
            finances(), sens=SensMouvement.ENTREE, date_mouvement=date.today(), libelle="Apport",
            montant=Decimal("100000.5"), mode=ModePaiement.ESPECES,
        )


def test_un_frais_de_mission_avec_des_centimes_est_refuse():
    mission = _affectee()

    with pytest.raises(FraisInvalide, match="sans centimes"):
        terrain.planifier_frais(
            mission, UserFactory(role=Role.PARCAUTO), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("1.5")
        )


def test_un_prix_de_mission_avec_des_centimes_est_refuse():
    with pytest.raises(MissionError, match="Le prix convenu doit être un nombre entier"):
        missions_services.creer_mission(
            client=ClientFactory(), lieu_chargement="Abidjan", lieu_livraison="Bouaké", nature_marchandise="Ciment",
            poids_t=Decimal("20"), prix_convenu=Decimal("850000.75"),
        )
