"""Prévision de trésorerie des missions (R4) : déclaration, planification, double validation."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr.tests.factories import PersonnelFactory
from apps.missions import terrain as services
from apps.missions.exceptions import ActionFraisNonAutorisee, FraisInvalide
from apps.missions.models import StatutFraisMission, StatutMission, TypeFraisMission
from apps.missions.signals import frais_mission_confirme

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def _preuve() -> SimpleUploadedFile:
    return SimpleUploadedFile("preuve.jpg", BytesIO(b"donnees").read(), content_type="image/jpeg")


def _chauffeur():
    return ChauffeurFactory(personnel=PersonnelFactory(utilisateur=UserFactory(role=Role.CHAUFFEUR)))


def _mission_affectee(chauffeur=None):
    chauffeur = chauffeur or _chauffeur()
    return MissionFactory(
        statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur
    )


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


def _finances():
    return UserFactory(role=Role.FINANCES)


# --- déclaration d'un imprévu (chauffeur) ---


def test_le_chauffeur_declare_un_imprevu_avec_preuve():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    frais = services.declarer_imprevu(
        mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve(), description="Panne moteur"
    )

    assert frais.type_frais == TypeFraisMission.IMPREVU
    assert frais.statut == StatutFraisMission.PREVU
    assert frais.chauffeur == chauffeur
    assert frais.justificatif


def test_un_chauffeur_ne_declare_pas_sur_la_mission_d_un_autre():
    mission = _mission_affectee()
    autre_chauffeur = _chauffeur()

    with pytest.raises(ActionFraisNonAutorisee):
        services.declarer_imprevu(mission, autre_chauffeur, montant=Decimal("1000"), justificatif=_preuve())


def test_un_imprevu_sans_preuve_est_refuse():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    with pytest.raises(FraisInvalide, match="preuve"):
        services.declarer_imprevu(mission, chauffeur, montant=Decimal("1000"), justificatif=None)


def test_un_montant_negatif_ou_nul_est_refuse():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    with pytest.raises(FraisInvalide, match="positif"):
        services.declarer_imprevu(mission, chauffeur, montant=Decimal("0"), justificatif=_preuve())


# --- planification (Parc Auto) ---


def test_le_parc_auto_planifie_une_avance_de_route():
    mission = _mission_affectee()

    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    assert frais.statut == StatutFraisMission.PREVU
    assert frais.saisi_par.role == Role.PARCAUTO


def test_seul_le_parc_auto_planifie():
    mission = _mission_affectee()

    with pytest.raises(ActionFraisNonAutorisee):
        services.planifier_frais(
            mission, _finances(), type_frais=TypeFraisMission.DEPENSE_PREVUE, montant=Decimal("1000")
        )


def test_on_ne_planifie_pas_un_imprevu_ni_un_encaissement():
    mission = _mission_affectee()

    with pytest.raises(FraisInvalide):
        services.planifier_frais(
            mission, _parcauto(), type_frais=TypeFraisMission.IMPREVU, montant=Decimal("1000")
        )


# --- validation d'une avance / dépense prévue : la Finance seule ---


def test_la_finance_confirme_directement_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    services.valider_finances(frais, _finances())

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.valide_finances_par is not None


def test_seule_la_finance_valide_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    for acteur in (_parcauto(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFraisNonAutorisee):
            services.valider_finances(frais, acteur)


# --- double validation d'un imprévu : Parc Auto puis Finance ---


def test_un_imprevu_passe_par_le_parc_auto_avant_la_finance():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    with pytest.raises(FraisInvalide, match="Parc Auto"):
        services.valider_finances(frais, _finances())

    services.valider_parcauto(frais, _parcauto())
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU  # toujours en attente de la finance
    assert frais.valide_parcauto_par is not None

    services.valider_finances(frais, _finances())
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.valide_finances_par is not None


def test_seul_le_parc_auto_valide_en_premier_un_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    with pytest.raises(ActionFraisNonAutorisee):
        services.valider_parcauto(frais, _finances())


def test_le_chauffeur_ne_valide_jamais_son_propre_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    utilisateur_chauffeur = chauffeur.personnel.utilisateur
    with pytest.raises(ActionFraisNonAutorisee):
        services.valider_parcauto(frais, utilisateur_chauffeur)


def test_une_ligne_deja_traitee_ne_se_valide_plus():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    services.valider_finances(frais, _finances())

    with pytest.raises(FraisInvalide, match="déjà traitée"):
        services.valider_finances(frais, _finances())


# --- rejet ---


def test_le_parc_auto_rejette_un_imprevu_avant_la_finance():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = services.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=_preuve())

    services.rejeter(frais, _parcauto(), motif="Aucune preuve valable")

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE and frais.motif_rejet == "Aucune preuve valable"


def test_la_finance_rejette_une_avance_de_route():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    with pytest.raises(ActionFraisNonAutorisee):
        services.rejeter(frais, _parcauto(), motif="x")

    services.rejeter(frais, _finances(), motif="Montant excessif")
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE


def test_le_rejet_exige_un_motif():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    with pytest.raises(FraisInvalide, match="motif"):
        services.rejeter(frais, _finances(), motif="   ")


# --- encaissement automatique ---


def test_creer_encaissement_est_directement_confirme():
    mission = _mission_affectee()

    frais = services.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement FACT-2026-0001")

    assert frais.type_frais == TypeFraisMission.ENCAISSEMENT
    assert frais.statut == StatutFraisMission.CONFIRME
    assert frais.est_sortie is False


# --- totaux ---


def test_totaux_ne_comptent_que_les_lignes_confirmees():
    mission = _mission_affectee()
    sortie_confirmee = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    services.valider_finances(sortie_confirmee, _finances())
    services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.DEPENSE_PREVUE, montant=Decimal("99999")
    )  # encore PREVU, ignoré
    services.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement")

    totaux = services.totaux(mission)

    assert totaux == {
        "sorties": Decimal("50000"), "encaisse": Decimal("300000"),
        "solde": Decimal("250000"), "en_attente": 1,
    }


# --- signal de confirmation (utilisé par finance.receivers) ---


def test_la_confirmation_emet_le_signal_frais_mission_confirme():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    recus = []
    frais_mission_confirme.connect(lambda sender, frais, **kw: recus.append(frais.pk), weak=False)

    services.valider_finances(frais, _finances())

    assert recus == [frais.pk]


def test_une_erreur_du_recepteur_annule_la_confirmation():
    mission = _mission_affectee()
    frais = services.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    def _echoue(sender, frais, **kwargs):
        raise RuntimeError("dépense impossible à écrire")

    frais_mission_confirme.connect(_echoue, weak=False, dispatch_uid="test-echec-confirmation")
    try:
        with pytest.raises(RuntimeError):
            services.valider_finances(frais, _finances())
    finally:
        frais_mission_confirme.disconnect(dispatch_uid="test-echec-confirmation")

    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU  # la transaction a été annulée
