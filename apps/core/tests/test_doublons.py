"""Double saisie (double clic, formulaire renvoyé) refusée côté serveur — audit AUD-06."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing_services
from apps.billing.exceptions import MontantInvalide, ReglementInvalide
from apps.billing.models import CategorieDepense, Depense, ModePaiement, Reglement
from apps.billing.tests.helpers import emise, finances
from apps.finance import services as finance_services
from apps.finance.models import MouvementManuel, SensMouvement
from apps.missions import terrain
from apps.missions.exceptions import FraisInvalide
from apps.missions.models import FraisMission, TypeFraisMission
from apps.missions.tests.test_services import _affectee

pytestmark = pytest.mark.django_db


def _vieillir(modele):
    """Fait comme si tout avait été enregistré il y a plus d'une minute."""
    modele.objects.update(created_at=timezone.now() - timedelta(seconds=61))


def _regler(facture, acteur, montant="100000", mode=ModePaiement.VIREMENT):
    return billing_services.enregistrer_reglement(
        facture, acteur, montant=Decimal(montant), mode=mode, date_reglement=date.today()
    )


def test_un_double_clic_sur_un_reglement_n_en_cree_qu_un():
    facture, acteur = emise(prix="1000000"), finances()
    _regler(facture, acteur)

    with pytest.raises(ReglementInvalide, match="saisie en double"):
        _regler(facture, acteur)

    assert Reglement.objects.filter(facture=facture).count() == 1


def test_un_second_reglement_identique_est_accepte_une_minute_plus_tard():
    facture, acteur = emise(prix="1000000"), finances()
    _regler(facture, acteur)
    _vieillir(Reglement)

    _regler(facture, acteur)

    assert Reglement.objects.filter(facture=facture).count() == 2


def test_un_reglement_different_n_est_pas_un_doublon():
    facture, acteur = emise(prix="1000000"), finances()
    _regler(facture, acteur)

    _regler(facture, acteur, montant="50000")
    _regler(facture, acteur, mode=ModePaiement.ESPECES)

    assert Reglement.objects.filter(facture=facture).count() == 3


def test_une_depense_identique_saisie_deux_fois_est_refusee():
    acteur = finances()
    donnees = dict(categorie=CategorieDepense.PEAGES, date_depense=date.today(), libelle="Péage Yamoussoukro",
                   montant=Decimal("5000"), mode=ModePaiement.ESPECES)
    billing_services.enregistrer_depense(acteur, **donnees)

    with pytest.raises(MontantInvalide, match="Une dépense identique"):
        billing_services.enregistrer_depense(acteur, **donnees)
    assert Depense.objects.count() == 1


def test_un_mouvement_identique_saisi_deux_fois_est_refuse():
    acteur = finances()
    donnees = dict(sens=SensMouvement.ENTREE, date_mouvement=date.today(), libelle="Apport", montant=Decimal("100000"),
                   mode=ModePaiement.ESPECES)
    finance_services.enregistrer_mouvement(acteur, **donnees)

    with pytest.raises(MontantInvalide, match="Un mouvement identique"):
        finance_services.enregistrer_mouvement(acteur, **donnees)
    assert MouvementManuel.objects.count() == 1


def test_un_frais_planifie_deux_fois_est_refuse():
    mission, parc = _affectee(), UserFactory(role=Role.PARCAUTO)
    terrain.planifier_frais(mission, parc, type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000"))

    with pytest.raises(FraisInvalide, match="Un frais identique"):
        terrain.planifier_frais(mission, parc, type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000"))
    assert FraisMission.objects.filter(mission=mission).count() == 1
