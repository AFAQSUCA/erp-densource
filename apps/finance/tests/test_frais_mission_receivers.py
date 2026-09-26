"""Prévision de trésorerie des missions (R4) côté finance : un frais confirmé devient une dépense,
un règlement reçu se reflète (sans double saisie) dans les frais de la mission facturée."""

from datetime import date
from decimal import Decimal

import pytest

from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import direction, finances, mission_livree
from apps.billing import services as billing_services
from apps.missions import terrain as missions_terrain
from apps.missions.models import FraisMission, StatutFraisMission, TypeFraisMission
from apps.missions.tests.test_frais_mission import _chauffeur, _mission_affectee, _parcauto

pytestmark = pytest.mark.django_db


def test_une_avance_confirmee_devient_une_depense_liee_a_la_mission():
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000"),
        description="Avance essence",
    )

    missions_terrain.valider_finances(frais, finances())

    depense = Depense.objects.get(origine=OrigineDepense.FRAIS_MISSION, origine_id=frais.pk)
    assert depense.categorie == CategorieDepense.FRAIS_MISSION
    assert depense.montant == Decimal("50000.00")
    assert depense.mission_id == mission.pk
    assert "Avance essence" in depense.libelle


def test_un_imprevu_confirme_devient_une_depense():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile

    preuve = SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=preuve)
    missions_terrain.valider_parcauto(frais, _parcauto())

    missions_terrain.valider_finances(frais, finances())

    assert Depense.objects.filter(origine=OrigineDepense.FRAIS_MISSION, origine_id=frais.pk).exists()


def test_un_encaissement_ne_cree_aucune_depense():
    mission = _mission_affectee()

    missions_terrain.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement")

    assert not Depense.objects.filter(origine=OrigineDepense.FRAIS_MISSION).exists()


def test_un_reglement_recu_se_reflete_dans_les_frais_de_la_mission():
    facture = billing_services.creer_facture(mission_livree(prix="1000000"), finances())
    billing_services.soumettre(facture, finances())
    billing_services.valider(facture, direction(), aujourd_hui=date(2026, 9, 1))

    billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 5),
    )

    ligne = FraisMission.objects.get(mission=facture.mission, type_frais=TypeFraisMission.ENCAISSEMENT)
    assert ligne.statut == StatutFraisMission.CONFIRME
    assert ligne.montant == Decimal("400000")
    assert facture.numero in ligne.description
    # Aucune double saisie : le règlement reste la seule dépense/entrée réelle en trésorerie.
    assert not Depense.objects.filter(mission=facture.mission).exists()
