"""Fiche véhicule et documents réglementaires — cahier-des-charges.md:88-95."""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services
from apps.fleet.exceptions import (
    DocumentInvalide,
    DoublonVehicule,
    KilometrageInvalide,
    VehiculeInvalide,
)
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db

AUJOURDHUI = date(2026, 9, 20)


def _donnees(**surcharges):
    donnees = dict(
        immatriculation="1234 AB 01",
        marque="Mercedes-Benz",
        modele="Actros",
        annee=2021,
        vin="WDB9634031L123456",
        kilometrage=50000,
        capacite_charge_t=Decimal("25"),
        reservoir_l=600,
    )
    donnees.update(surcharges)
    return donnees


# --- création ---


def test_creer_vehicule_disponible_avec_les_donnees_saisies():
    chauffeur = ChauffeurFactory()

    camion = services.creer_vehicule(**_donnees(chauffeur_habituel=chauffeur))

    assert camion.statut == StatutVehicule.DISPONIBLE
    assert camion.chauffeur_habituel == chauffeur
    assert camion.capacite_charge_t == Decimal("25.00")


def test_creer_vehicule_normalise_immatriculation_et_vin():
    camion = services.creer_vehicule(
        **_donnees(immatriculation="  1234   ab  01 ", vin=" wdb9634031l123456 ")
    )

    assert camion.immatriculation == "1234 AB 01"
    assert camion.vin == "WDB9634031L123456"


def test_deux_saisies_qui_ne_different_que_par_la_casse_sont_un_doublon():
    services.creer_vehicule(**_donnees())

    with pytest.raises(DoublonVehicule, match="immatriculation"):
        services.creer_vehicule(**_donnees(immatriculation="1234 ab 01", vin="AUTRE0000000000001"))


def test_un_vin_deja_utilise_est_refuse():
    services.creer_vehicule(**_donnees())

    with pytest.raises(DoublonVehicule, match="châssis"):
        services.creer_vehicule(**_donnees(immatriculation="9999 ZZ 01"))


def test_l_immatriculation_d_un_camion_supprime_logiquement_reste_reservee():
    ancien = services.creer_vehicule(**_donnees())
    ancien.delete()

    with pytest.raises(DoublonVehicule):
        services.creer_vehicule(**_donnees(vin="AUTRE0000000000001"))


@pytest.mark.parametrize(
    "champ", [{"capacite_charge_t": Decimal("0")}, {"reservoir_l": 0}, {"immatriculation": "  "}, {"vin": ""}]
)
def test_creer_vehicule_refuse_les_donnees_invalides(champ):
    with pytest.raises(VehiculeInvalide):
        services.creer_vehicule(**_donnees(**champ))


def test_la_creation_est_auditee():
    camion = services.creer_vehicule(**_donnees())

    assert AuditLog.objects.filter(entite="Vehicule", entite_id=camion.pk, action="CREATE").exists()


# --- modification ---


def test_modifier_vehicule_met_a_jour_la_fiche():
    camion = VehiculeFactory(kilometrage=1000)

    services.modifier_vehicule(
        camion, **_donnees(immatriculation="5555 XY 01", marque="Volvo", kilometrage=1500)
    )

    camion.refresh_from_db()
    assert (camion.immatriculation, camion.marque, camion.kilometrage) == (
        "5555 XY 01",
        "Volvo",
        1500,
    )


def test_modifier_vehicule_conserve_son_statut():
    camion = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE, kilometrage=0)

    services.modifier_vehicule(camion, **_donnees(kilometrage=0))

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.EN_MAINTENANCE


def test_modifier_vehicule_accepte_de_garder_sa_propre_immatriculation():
    camion = services.creer_vehicule(**_donnees())

    services.modifier_vehicule(camion, **_donnees(marque="MAN"))

    camion.refresh_from_db()
    assert camion.marque == "MAN"


def test_modifier_vehicule_refuse_l_immatriculation_d_un_autre_camion():
    services.creer_vehicule(**_donnees())
    autre = VehiculeFactory(kilometrage=0)

    with pytest.raises(DoublonVehicule):
        services.modifier_vehicule(autre, **_donnees(vin="AUTRE0000000000001", kilometrage=0))


def test_le_compteur_ne_peut_pas_reculer_lors_d_une_modification():
    camion = VehiculeFactory(kilometrage=10000)

    with pytest.raises(KilometrageInvalide):
        services.modifier_vehicule(camion, **_donnees(kilometrage=9999))

    camion.refresh_from_db()
    assert camion.kilometrage == 10000


def test_modifier_le_chauffeur_habituel_puis_le_retirer():
    camion = VehiculeFactory(kilometrage=0)
    chauffeur = ChauffeurFactory()

    services.modifier_vehicule(camion, **_donnees(kilometrage=0, chauffeur_habituel=chauffeur))
    camion.refresh_from_db()
    assert camion.chauffeur_habituel == chauffeur

    services.modifier_vehicule(camion, **_donnees(kilometrage=0, chauffeur_habituel=None))
    camion.refresh_from_db()
    assert camion.chauffeur_habituel is None


# --- recherche ---


def test_rechercher_vehicules_par_statut_et_texte():
    libre = VehiculeFactory(immatriculation="1000 AA 01", marque="Volvo")
    VehiculeFactory(immatriculation="2000 BB 01", marque="DAF", statut=StatutVehicule.EN_MISSION)

    assert list(services.rechercher_vehicules(statut=StatutVehicule.DISPONIBLE)) == [libre]
    assert list(services.rechercher_vehicules(recherche="volvo")) == [libre]
    assert list(services.rechercher_vehicules(recherche="1000")) == [libre]
    assert services.rechercher_vehicules(statut="???", recherche="  ").count() == 2


def test_rechercher_vehicules_ne_garde_que_ceux_avec_un_document_a_renouveler():
    alerte = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=alerte, date_delivrance=date(2025, 1, 1), date_expiration=date(2026, 1, 1)
    )
    en_regle = VehiculeFactory()
    DocumentReglementaireFactory(vehicule=en_regle, date_expiration=date(2099, 1, 1))

    resultat = services.rechercher_vehicules(documents_a_renouveler=True)

    assert list(resultat) == [alerte]


# --- documents ---


def test_enregistrer_un_nouveau_document():
    camion = VehiculeFactory()

    document, cree = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2026, 1, 1),
        date_expiration=date(2027, 1, 1),
    )

    assert cree is True
    assert document.vehicule == camion


def test_renouveler_met_a_jour_le_meme_document_et_garde_l_historique_dans_l_audit():
    camion = VehiculeFactory()
    premier, _ = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=date(2026, 1, 1),
    )

    renouvele, cree = services.enregistrer_document(
        camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2026, 1, 1),
        date_expiration=date(2027, 1, 1),
    )

    assert cree is False and renouvele.pk == premier.pk
    assert DocumentReglementaire.objects.filter(vehicule=camion).count() == 1
    modification = AuditLog.objects.get(
        entite="DocumentReglementaire", entite_id=premier.pk, action="UPDATE"
    )
    assert modification.ancienne_valeur["date_expiration"] == "2026-01-01"
    assert modification.nouvelle_valeur["date_expiration"] == "2027-01-01"


def test_l_expiration_ne_peut_pas_preceder_la_delivrance():
    with pytest.raises(DocumentInvalide):
        services.enregistrer_document(
            VehiculeFactory(),
            type_document=TypeDocument.PATENTE,
            date_delivrance=date(2026, 5, 1),
            date_expiration=date(2026, 4, 1),
        )


def test_un_type_de_document_inconnu_est_refuse():
    with pytest.raises(DocumentInvalide):
        services.enregistrer_document(
            VehiculeFactory(),
            type_document="PERMIS_DE_CONDUIRE",
            date_delivrance=date(2026, 1, 1),
            date_expiration=date(2027, 1, 1),
        )


# --- état des documents (alerte à 30 jours) ---


def _etats(camion):
    return {d["code"]: d for d in services.etat_documents(camion, aujourd_hui=AUJOURDHUI)}


def test_etat_documents_liste_les_4_types_dans_l_ordre_du_cdc():
    situation = services.etat_documents(VehiculeFactory(), aujourd_hui=AUJOURDHUI)

    assert [d["code"] for d in situation] == [
        "CARTE_GRISE",
        "ASSURANCE",
        "VISITE_TECHNIQUE",
        "PATENTE",
    ]
    assert {d["etat"] for d in situation} == {"MANQUANT"}


@pytest.mark.parametrize(
    ("expiration", "etat", "jours"),
    [
        (date(2026, 9, 19), "EXPIRE", -1),  # hier
        (date(2026, 9, 20), "A_RENOUVELER", 0),  # aujourd'hui : encore valable
        (date(2026, 10, 20), "A_RENOUVELER", 30),  # 30 jours : alerte
        (date(2026, 10, 21), "VALIDE", 31),  # 31 jours : pas encore
    ],
)
def test_etat_d_un_document_selon_les_jours_restants(expiration, etat, jours):
    camion = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=expiration,
    )

    assurance = _etats(camion)["ASSURANCE"]

    assert (assurance["etat"], assurance["jours_restants"]) == (etat, jours)


def test_un_document_supprime_logiquement_redevient_manquant():
    camion = VehiculeFactory()
    document = DocumentReglementaireFactory(vehicule=camion, type_document=TypeDocument.PATENTE)
    document.delete()

    assert _etats(camion)["PATENTE"]["etat"] == "MANQUANT"


def test_vehicules_avec_documents_a_renouveler():
    alerte, tranquille = VehiculeFactory(), VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=alerte, date_delivrance=date(2026, 1, 1), date_expiration=date(2026, 10, 1)
    )
    DocumentReglementaireFactory(vehicule=tranquille, date_expiration=date(2099, 1, 1))

    ids = services.vehicules_avec_documents_a_renouveler(aujourd_hui=AUJOURDHUI)

    assert ids == {alerte.pk}


def test_vehicules_queryset_charge_le_chauffeur_habituel_sans_requete_supplementaire(
    django_assert_num_queries,
):
    chauffeur = ChauffeurFactory()
    VehiculeFactory(chauffeur_habituel=chauffeur)

    with django_assert_num_queries(1):
        camions = list(services.vehicules_queryset())
        assert camions[0].chauffeur_habituel.personnel.nom


def test_chauffeurs_actifs_exclut_les_inactifs_et_est_trie_par_nom():
    from apps.drivers.models import StatutChauffeur
    from apps.drivers import services as drivers_services

    b = ChauffeurFactory(personnel__nom="Zoro")
    a = ChauffeurFactory(personnel__nom="Adou")
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    assert list(drivers_services.chauffeurs_actifs()) == [a, b]

