"""Mission sans issue : annulation avant le départ, transfert en route — décision du 13/10/2026, audit AUD-02."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import StatutProforma
from apps.billing.tests.helpers import charge_clientele, proforma_envoyee
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory, CopiloteFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.missions import services, terrain
from apps.missions.exceptions import AffectationImpossible, MissionError, TransitionMissionInterdite
from apps.missions.models import FraisMission, StatutFraisMission, StatutMission, TransfertMission, TypeFraisMission

from .test_services import _affectee, _en_cours, _planifiee, _recuperee

pytestmark = pytest.mark.django_db


def _direction():
    return UserFactory(role=Role.DIRECTION)


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


# --- annulation ---


def test_annuler_une_mission_affectee_libere_camion_et_chauffeur():
    mission = _affectee()
    camion, chauffeur = mission.vehicule, mission.chauffeur

    services.annuler_mission(mission, _direction(), motif="Le client annule sa commande")

    mission.refresh_from_db()
    assert mission.statut == StatutMission.ANNULEE and mission.motif_annulation == "Le client annule sa commande"
    assert not services.vehicule_a_mission_active(camion) and not services.chauffeur_a_mission_active(chauffeur)
    services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=chauffeur)  # réutilisables aussitôt


def test_les_frais_prevus_sont_rejetes_mais_une_avance_versee_reste():
    mission = _affectee()
    prevu = terrain.planifier_frais(mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000"))
    verse = terrain.planifier_frais(mission, _parcauto(), type_frais=TypeFraisMission.DEPENSE_PREVUE, montant=Decimal("20000"))
    FraisMission.objects.filter(pk=verse.pk).update(statut=StatutFraisMission.CONFIRME)

    services.annuler_mission(mission, _direction(), motif="Annulée")

    prevu.refresh_from_db()
    verse.refresh_from_db()
    assert prevu.statut == StatutFraisMission.REJETE and "Mission annulée" in prevu.motif_rejet
    assert verse.statut == StatutFraisMission.CONFIRME


def test_le_devis_d_origine_est_annule_avec_la_mission():
    proforma = proforma_envoyee()
    billing.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    mission = billing.convertir_en_mission(proforma)

    services.annuler_mission(mission, charge_clientele(), motif="Commande retirée")

    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.ANNULEE


def test_une_mission_partie_ne_s_annule_pas_et_les_droits_et_le_motif_sont_controles():
    with pytest.raises(TransitionMissionInterdite, match="transfère"):
        services.annuler_mission(_en_cours(), _direction(), motif="x")
    mission = _planifiee()
    with pytest.raises(TransitionMissionInterdite, match="droit"):
        services.annuler_mission(mission, _parcauto(), motif="x")
    with pytest.raises(MissionError, match="motif"):
        services.annuler_mission(mission, _direction(), motif=" ")


# --- transfert ---


def test_transferer_une_mission_en_route_change_l_equipage_et_garde_les_codes():
    mission = _en_cours()
    ancien_camion, ancien_chauffeur, codes = mission.vehicule, mission.chauffeur, (mission.code_expediteur, mission.code_destinataire)
    nouveau_camion, nouveau_chauffeur = VehiculeEnRegleFactory(kilometrage=50000), ChauffeurFactory()

    transfert = services.transferer_mission(
        mission, _parcauto(), vehicule=nouveau_camion, chauffeur=nouveau_chauffeur,
        km_ancien_vehicule=ancien_camion.kilometrage + 180, statut_ancien_vehicule=StatutVehicule.EN_MAINTENANCE,
        motif="Panne moteur définitive",
    )

    mission.refresh_from_db()
    for objet in (ancien_camion, ancien_chauffeur, nouveau_camion, nouveau_chauffeur):
        objet.refresh_from_db()
    assert (mission.vehicule, mission.chauffeur) == (nouveau_camion, nouveau_chauffeur)
    assert (mission.code_expediteur, mission.code_destinataire) == codes and mission.km_depart == 50000
    assert ancien_camion.statut == StatutVehicule.EN_MAINTENANCE and ancien_camion.kilometrage == 120180
    assert ancien_chauffeur.statut == StatutChauffeur.DISPONIBLE
    assert nouveau_camion.statut == StatutVehicule.EN_MISSION and nouveau_chauffeur.statut == StatutChauffeur.EN_MISSION
    assert transfert.km_ancien_vehicule == 120180 and transfert.km_depart_nouveau == 50000


def test_la_mission_transferee_se_livre_avec_le_compteur_du_nouveau_camion():
    mission = _recuperee()
    nouveau = VehiculeEnRegleFactory(kilometrage=50000)
    services.transferer_mission(
        mission, _parcauto(), vehicule=nouveau, chauffeur=mission.chauffeur, km_ancien_vehicule=120050,
        statut_ancien_vehicule=StatutVehicule.IMMOBILISE, motif="Accident",
    )
    mission.refresh_from_db()

    services.livrer_mission(mission, code=mission.code_destinataire, km_arrivee=50300)

    nouveau.refresh_from_db()
    assert nouveau.kilometrage == 50300 and nouveau.statut == StatutVehicule.DISPONIBLE


def test_changer_seulement_de_chauffeur_ou_de_copilote_garde_le_camion():
    mission = _en_cours()
    camion = mission.vehicule
    copilote = CopiloteFactory()

    services.transferer_mission(
        mission, _parcauto(), vehicule=camion, chauffeur=ChauffeurFactory(), copilote=copilote,
        km_ancien_vehicule=0, statut_ancien_vehicule=StatutVehicule.DISPONIBLE, motif="Chauffeur malade",
    )

    camion.refresh_from_db()
    assert camion.statut == StatutVehicule.EN_MISSION and TransfertMission.objects.get().statut_ancien_vehicule == ""
    copilote.refresh_from_db()
    assert copilote.statut == StatutChauffeur.EN_MISSION


def test_les_controles_de_l_affectation_s_appliquent_au_transfert():
    mission = _en_cours()
    occupe = _affectee().vehicule

    with pytest.raises(AffectationImpossible):
        services.transferer_mission(
            mission, _parcauto(), vehicule=occupe, chauffeur=mission.chauffeur, km_ancien_vehicule=120100,
            statut_ancien_vehicule=StatutVehicule.EN_MAINTENANCE, motif="Panne",
        )
    with pytest.raises(TransitionMissionInterdite, match="en route"):
        services.transferer_mission(
            _affectee(), _parcauto(), vehicule=VehiculeEnRegleFactory(), chauffeur=ChauffeurFactory(),
            km_ancien_vehicule=0, statut_ancien_vehicule=StatutVehicule.DISPONIBLE, motif="x",
        )
    with pytest.raises(TransitionMissionInterdite, match="droit"):
        services.transferer_mission(
            mission, UserFactory(role=Role.CHARGE_CLIENTELE), vehicule=VehiculeEnRegleFactory(),
            chauffeur=mission.chauffeur, km_ancien_vehicule=120100, statut_ancien_vehicule=StatutVehicule.DISPONIBLE,
            motif="x",
        )


# --- écrans ---


def test_l_ecran_annule_une_mission(client):
    mission = _affectee()
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))

    assert reverse("missions:annuler", args=[mission.pk]) in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    reponse = client.post(reverse("missions:annuler", args=[mission.pk]), {"motif": "Client injoignable"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.ANNULEE
    assert any("annulée" in str(m) for m in reponse.context["messages"])


def test_l_ecran_transfere_une_mission(client):
    mission = _en_cours()
    nouveau = VehiculeEnRegleFactory(kilometrage=50000)
    client.force_login(_parcauto())
    url = reverse("missions:transferer", args=[mission.pk])

    assert "Transférer" in client.get(url).content.decode()
    client.post(url, {
        "vehicule": nouveau.pk, "chauffeur": mission.chauffeur.pk, "km_ancien_vehicule": 120200,
        "statut_ancien_vehicule": StatutVehicule.EN_MAINTENANCE, "motif": "Panne",
    })

    mission.refresh_from_db()
    assert mission.vehicule == nouveau
