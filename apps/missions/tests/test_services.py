"""Cycle de vie d'une mission — cahier-des-charges.md:127-143."""

import re
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.customers.tests.factories import ClientFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import services
from apps.missions.exceptions import (
    AffectationImpossible,
    CodeInvalide,
    DemarrageImpossible,
    KilometrageInvalide,
    MissionError,
    TransitionMissionInterdite,
)
from apps.missions.models import Mission, StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _creer(**surcharges):
    donnees = dict(
        client=ClientFactory(),
        lieu_chargement="Abidjan",
        lieu_livraison="Bouaké",
        nature_marchandise="Ciment",
        poids_t=Decimal("20"),
        prix_convenu=Decimal("850000"),
    )
    donnees.update(surcharges)
    return services.creer_mission(**donnees)


def _planifiee(**surcharges):
    return services.planifier_mission(_creer(**surcharges))


def _affectee(vehicule=None, chauffeur=None, **surcharges):
    vehicule = vehicule or VehiculeFactory()
    chauffeur = chauffeur or ChauffeurFactory()
    return services.affecter_mission(
        _planifiee(**surcharges), vehicule=vehicule, chauffeur=chauffeur
    )


def _en_cours():
    return services.demarrer_mission(_affectee())


def _recuperee():
    mission = _en_cours()
    return services.confirmer_recuperation(mission, code=mission.code_expediteur)


def _livree(km_arrivee=125000):
    mission = _recuperee()
    return services.livrer_mission(
        mission, code=mission.code_destinataire, km_arrivee=km_arrivee
    )


# --- création ---


def test_creation_donne_un_brouillon_numerote_avec_deux_codes():
    mission = _creer()

    assert mission.statut == StatutMission.BROUILLON
    assert re.fullmatch(r"MIS-\d{4}-0001", mission.numero)
    assert mission.vehicule is None and mission.chauffeur is None
    for code in (mission.code_expediteur, mission.code_destinataire):
        assert re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code)
    assert mission.code_expediteur != mission.code_destinataire


def test_les_numeros_de_mission_sont_consecutifs():
    assert _creer().numero.endswith("-0001")
    assert _creer().numero.endswith("-0002")


def test_creation_refuse_un_poids_nul_ou_negatif():
    with pytest.raises(MissionError):
        _creer(poids_t=Decimal("0"))


def test_creation_refuse_un_prix_negatif():
    with pytest.raises(MissionError):
        _creer(prix_convenu=Decimal("-1"))


def test_les_codes_secrets_ne_sont_pas_ecrits_dans_le_journal_d_audit():
    mission = _creer()
    mission.lieu_livraison = "Korhogo"
    mission.save()

    entrees = AuditLog.objects.filter(entite="Mission", entite_id=mission.pk)
    assert entrees.count() == 2  # création + modification du lieu
    for entree in entrees:
        valeurs = {**(entree.ancienne_valeur or {}), **(entree.nouvelle_valeur or {})}
        assert "code_expediteur" not in valeurs
        assert "code_destinataire" not in valeurs


# --- planification ---


def test_planifier_passe_le_brouillon_a_planifiee():
    assert _planifiee().statut == StatutMission.PLANIFIEE


def test_planifier_refuse_hors_brouillon():
    with pytest.raises(TransitionMissionInterdite):
        services.planifier_mission(_planifiee())


# --- affectation ---


def test_affecter_reserve_camion_et_chauffeur_sans_les_passer_en_mission():
    vehicule, chauffeur = VehiculeFactory(), ChauffeurFactory()

    mission = _affectee(vehicule, chauffeur)

    assert mission.statut == StatutMission.AFFECTEE
    assert (mission.vehicule, mission.chauffeur) == (vehicule, chauffeur)
    vehicule.refresh_from_db()
    assert vehicule.statut == StatutVehicule.DISPONIBLE


def test_affecter_refuse_une_mission_non_planifiee():
    with pytest.raises(TransitionMissionInterdite):
        services.affecter_mission(
            _creer(), vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
        )


@pytest.mark.parametrize(
    "statut",
    [
        StatutVehicule.EN_MISSION,
        StatutVehicule.EN_MAINTENANCE,
        StatutVehicule.IMMOBILISE,
        StatutVehicule.HORS_SERVICE,
    ],
)
def test_affecter_refuse_un_camion_non_disponible(statut):
    with pytest.raises(AffectationImpossible, match="camion"):
        services.affecter_mission(
            _planifiee(),
            vehicule=VehiculeFactory(statut=statut),
            chauffeur=ChauffeurFactory(),
        )


@pytest.mark.parametrize(
    "statut",
    [
        StatutChauffeur.EN_MISSION,
        StatutChauffeur.EN_CONGE,
        StatutChauffeur.SUSPENDU,
        StatutChauffeur.INACTIF,
    ],
)
def test_affecter_refuse_un_chauffeur_non_disponible(statut):
    with pytest.raises(AffectationImpossible, match="chauffeur"):
        services.affecter_mission(
            _planifiee(),
            vehicule=VehiculeFactory(),
            chauffeur=ChauffeurFactory(statut=statut),
        )


def test_affecter_refuse_un_camion_deja_reserve_par_une_autre_mission():
    vehicule = VehiculeFactory()
    _affectee(vehicule=vehicule)

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.affecter_mission(
            _planifiee(), vehicule=vehicule, chauffeur=ChauffeurFactory()
        )


def test_affecter_refuse_un_chauffeur_deja_reserve_par_une_autre_mission():
    chauffeur = ChauffeurFactory()
    _affectee(chauffeur=chauffeur)

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.affecter_mission(
            _planifiee(), vehicule=VehiculeFactory(), chauffeur=chauffeur
        )


def test_une_mission_planifiee_ne_reserve_pas_encore_de_camion():
    _planifiee()

    assert Mission.objects.filter(vehicule__isnull=False).count() == 0


def test_affecter_refuse_une_charge_superieure_a_la_capacite_du_camion():
    with pytest.raises(AffectationImpossible, match="capacité"):
        services.affecter_mission(
            _planifiee(poids_t=Decimal("25.01")),
            vehicule=VehiculeFactory(capacite_charge_t=Decimal("25.00")),
            chauffeur=ChauffeurFactory(),
        )


def test_affecter_accepte_une_charge_egale_a_la_capacite():
    mission = _affectee(poids_t=Decimal("25.00"))

    assert mission.statut == StatutMission.AFFECTEE


# --- démarrage ---


def test_demarrer_passe_camion_et_chauffeur_en_mission_et_releve_le_km():
    vehicule = VehiculeFactory(kilometrage=120000)
    chauffeur = ChauffeurFactory()
    mission = services.demarrer_mission(_affectee(vehicule, chauffeur))

    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert mission.km_depart == 120000
    assert mission.date_depart is not None
    vehicule.refresh_from_db()
    chauffeur.refresh_from_db()
    assert vehicule.statut == StatutVehicule.EN_MISSION
    assert chauffeur.statut == StatutChauffeur.EN_MISSION


def test_demarrer_refuse_si_le_camion_est_passe_en_maintenance_entre_temps():
    vehicule = VehiculeFactory()
    mission = _affectee(vehicule=vehicule)
    vehicule.statut = StatutVehicule.EN_MAINTENANCE
    vehicule.save()

    with pytest.raises(DemarrageImpossible, match="camion"):
        services.demarrer_mission(mission)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE


def test_demarrer_refuse_si_le_chauffeur_est_passe_en_conge_entre_temps():
    chauffeur = ChauffeurFactory()
    mission = _affectee(chauffeur=chauffeur)
    chauffeur.statut = StatutChauffeur.EN_CONGE
    chauffeur.save()

    with pytest.raises(DemarrageImpossible, match="chauffeur"):
        services.demarrer_mission(mission)

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


def test_demarrer_refuse_hors_statut_affectee():
    with pytest.raises(TransitionMissionInterdite):
        services.demarrer_mission(_planifiee())


# --- récupération du colis (code expéditeur) ---


def test_confirmer_recuperation_avec_le_bon_code():
    mission = _en_cours()

    services.confirmer_recuperation(mission, code=mission.code_expediteur)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert mission.date_recuperation is not None


def test_le_code_est_tolere_en_minuscules_et_avec_espaces():
    mission = _en_cours()

    services.confirmer_recuperation(mission, code=f" {mission.code_expediteur.lower()} ")

    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_confirmer_recuperation_refuse_un_mauvais_code():
    mission = _en_cours()

    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(mission, code="AAAAAAAA")

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART


def test_le_code_destinataire_ne_permet_pas_de_recuperer_le_colis():
    mission = _en_cours()

    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(mission, code=mission.code_destinataire)


def test_confirmer_recuperation_refuse_hors_statut_depart():
    mission = _affectee()

    with pytest.raises(TransitionMissionInterdite):
        services.confirmer_recuperation(mission, code=mission.code_expediteur)


# --- livraison (code destinataire) ---


def test_livrer_libere_camion_et_chauffeur_et_met_a_jour_le_compteur():
    mission = _livree(km_arrivee=125000)

    assert mission.statut == StatutMission.LIVREE
    assert mission.km_arrivee == 125000
    assert mission.date_livraison is not None
    mission.vehicule.refresh_from_db()
    mission.chauffeur.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE
    assert mission.vehicule.kilometrage == 125000
    assert mission.chauffeur.statut == StatutChauffeur.DISPONIBLE


def test_livrer_refuse_le_code_expediteur():
    mission = _recuperee()

    with pytest.raises(CodeInvalide):
        services.livrer_mission(mission, code=mission.code_expediteur, km_arrivee=125000)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_livrer_refuse_un_km_arrivee_inferieur_au_km_depart_et_ne_change_rien():
    mission = _recuperee()

    with pytest.raises(KilometrageInvalide, match="départ"):
        services.livrer_mission(
            mission, code=mission.code_destinataire, km_arrivee=mission.km_depart - 1
        )

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert mission.vehicule.statut == StatutVehicule.EN_MISSION


def test_livrer_refuse_un_km_arrivee_inferieur_au_compteur_actuel_du_camion():
    mission = _recuperee()
    mission.vehicule.kilometrage = 200000  # ex. plein saisi entre-temps
    mission.vehicule.save()

    with pytest.raises(KilometrageInvalide, match="compteur"):
        services.livrer_mission(
            mission, code=mission.code_destinataire, km_arrivee=150000
        )


def test_livrer_conserve_le_statut_maintenance_d_un_camion_immobilise_en_route():
    mission = _recuperee()
    mission.vehicule.statut = StatutVehicule.EN_MAINTENANCE
    mission.vehicule.save()

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)

    mission.vehicule.refresh_from_db()
    assert mission.vehicule.statut == StatutVehicule.EN_MAINTENANCE


def test_livrer_conserve_un_statut_chauffeur_suspendu():
    mission = _recuperee()
    mission.chauffeur.statut = StatutChauffeur.SUSPENDU
    mission.chauffeur.save()

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)

    mission.chauffeur.refresh_from_db()
    assert mission.chauffeur.statut == StatutChauffeur.SUSPENDU


def test_livrer_refuse_hors_statut_colis_recupere():
    mission = _en_cours()

    with pytest.raises(TransitionMissionInterdite):
        services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=125000)


# --- clôture ---


def test_cloturer_une_mission_livree():
    mission = services.cloturer_mission(_livree())

    assert mission.statut == StatutMission.CLOTUREE
    assert mission.date_cloture is not None


def test_cloturer_refuse_une_mission_non_livree():
    with pytest.raises(TransitionMissionInterdite):
        services.cloturer_mission(_recuperee())


# --- mission active (fournit mission_active à fleet.calculer_statut) ---


@pytest.mark.parametrize(
    ("etape", "attendu"),
    [
        (_affectee, True),
        (_en_cours, True),
        (_recuperee, True),
        (_livree, False),
    ],
)
def test_vehicule_a_mission_active_selon_l_etape(etape, attendu):
    mission = etape()

    assert services.vehicule_a_mission_active(mission.vehicule) is attendu
    assert services.chauffeur_a_mission_active(mission.chauffeur) is attendu


def test_un_camion_sans_mission_n_a_pas_de_mission_active():
    _planifiee()

    assert services.vehicule_a_mission_active(VehiculeFactory()) is False


def test_le_cycle_complet_est_audite():
    mission = services.cloturer_mission(_livree())

    entrees = AuditLog.objects.filter(
        entite="Mission", entite_id=mission.pk, action="UPDATE"
    ).order_by("pk")
    statuts = [
        e.nouvelle_valeur["statut"] for e in entrees if "statut" in e.nouvelle_valeur
    ]
    assert statuts == [
        "PLANIFIEE",
        "AFFECTEE",
        "EN_COURS_DEPART",
        "EN_COURS_COLIS_RECUPERE",
        "LIVREE",
        "CLOTUREE",
    ]


# --- lecture : recherche des missions ---


def test_rechercher_missions_sans_critere_retourne_tout():
    _creer(), _planifiee()

    assert services.rechercher_missions().count() == 2


def test_rechercher_missions_combine_statut_et_texte():
    cible = _planifiee(lieu_livraison="Korhogo")
    _planifiee(lieu_livraison="Bouaké")
    _creer(lieu_livraison="Korhogo")

    resultat = services.rechercher_missions(
        statut=StatutMission.PLANIFIEE, recherche="korhogo"
    )

    assert list(resultat) == [cible]


def test_rechercher_missions_ignore_un_statut_inconnu_et_les_espaces():
    _creer()

    assert services.rechercher_missions(statut="???", recherche="   ").count() == 1


# --- lieux déjà utilisés (suggestions à la saisie) ---


def test_les_lieux_deja_utilises_sont_classes_par_frequence():
    MissionFactory(lieu_chargement="Abidjan", lieu_livraison="Bouaké")
    MissionFactory(lieu_chargement="Abidjan", lieu_livraison="Korhogo")
    MissionFactory(lieu_chargement="San-Pédro", lieu_livraison="Abidjan")

    assert services.lieux_deja_utilises() == ["Abidjan", "Bouaké", "Korhogo", "San-Pédro"]


def test_un_meme_lieu_ecrit_differemment_n_est_propose_qu_une_fois():
    MissionFactory(lieu_chargement="Bouaké", lieu_livraison="Abidjan")
    MissionFactory(lieu_chargement="Bouaké", lieu_livraison="Abidjan")
    MissionFactory(lieu_chargement="bouake ", lieu_livraison="ABIDJAN")

    lieux = services.lieux_deja_utilises()

    assert sorted(lieux) == ["Abidjan", "Bouaké"]  # la graphie la plus employée l'emporte


def test_aucun_lieu_sans_mission_et_la_liste_est_bornee():
    assert services.lieux_deja_utilises() == []
    for i in range(5):
        MissionFactory(lieu_chargement=f"Ville {i}", lieu_livraison=f"Ville {i}")

    assert len(services.lieux_deja_utilises(limite=3)) == 3
