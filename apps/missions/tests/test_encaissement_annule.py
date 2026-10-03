"""Audit (Lot H, limite connue) : annuler un règlement retire son reflet de la prévision de trésorerie de la mission."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.billing import services as billing
from apps.billing.models import ModePaiement, Reglement
from apps.billing.tests.helpers import JOUR, emise, finances
from apps.missions.models import FraisMission, TypeFraisMission

pytestmark = pytest.mark.django_db


def _encaissements(mission):
    return FraisMission.objects.filter(mission=mission, type_frais=TypeFraisMission.ENCAISSEMENT)


def _reglement(facture, montant="100000"):
    return billing.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )


def test_un_reglement_se_reflete_sur_la_mission_avec_son_lien():
    facture = emise(prix="1000000")
    reglement = _reglement(facture)

    ligne = _encaissements(facture.mission).get()

    assert ligne.reglement == reglement


def test_annuler_le_reglement_retire_l_encaissement_de_la_mission():
    facture = emise(prix="1000000")
    premier, second = _reglement(facture, "100000"), _reglement(facture, "200000")

    billing.annuler_reglement(premier, finances(), motif="Erreur de saisie")

    restantes = _encaissements(facture.mission)
    assert [(l.reglement_id, l.montant) for l in restantes] == [(second.pk, Decimal("200000.00"))]
    # soft delete : la ligne reste en base, tracée
    assert FraisMission.all_objects.filter(reglement=premier, is_deleted=True).count() == 1


def test_la_commande_de_reprise_rattache_et_retire_les_anciens_encaissements():
    facture = emise(prix="1000000")
    garde, annule = _reglement(facture, "100000"), _reglement(facture, "250000")
    billing.annuler_reglement(annule, finances(), motif="Erreur")
    # état « avant ce lot » : aucune ligne n'avait de lien, et celle de l'annulé était restée
    FraisMission.all_objects.filter(type_frais=TypeFraisMission.ENCAISSEMENT).update(
        reglement=None, is_deleted=False, deleted_at=None
    )

    call_command("rattacher_encaissements_missions")
    call_command("rattacher_encaissements_missions")  # rejouable

    actives = _encaissements(facture.mission)
    assert [(l.reglement_id, l.montant) for l in actives] == [(garde.pk, Decimal("100000.00"))]
    assert Reglement.all_objects.get(pk=annule.pk).is_deleted


def test_la_commande_en_simulation_n_ecrit_rien():
    facture = emise(prix="1000000")
    _reglement(facture)
    FraisMission.objects.filter(type_frais=TypeFraisMission.ENCAISSEMENT).update(reglement=None)

    call_command("rattacher_encaissements_missions", "--dry-run")

    assert _encaissements(facture.mission).get().reglement_id is None
