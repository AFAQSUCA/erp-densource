"""Mission créée depuis un devis accepté (R6) : recopie du trajet, du prix HT, et « 1 devis = 1 mission »."""

from decimal import Decimal

import pytest

from apps.billing import services as billing_services
from apps.billing.models import StatutProforma
from apps.billing.tests.helpers import JOUR, charge_clientele, proforma_envoyee
from apps.missions import services
from apps.missions.exceptions import TransitionMissionInterdite
from apps.missions.models import StatutMission

pytestmark = pytest.mark.django_db


def _acceptee(**surcharges):
    proforma = proforma_envoyee(aujourd_hui=JOUR, **surcharges)
    billing_services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    return proforma


def test_la_mission_recopie_le_trajet_la_marchandise_le_poids_et_le_prix_ht():
    proforma = _acceptee(prix="350000")

    mission = services.creer_mission_depuis_proforma(proforma)

    assert mission.client == proforma.client
    assert mission.lieu_chargement == proforma.lieu_chargement
    assert mission.lieu_livraison == proforma.lieu_livraison
    assert mission.nature_marchandise == proforma.nature_marchandise
    assert mission.poids_t == proforma.poids_t
    assert mission.prix_convenu == Decimal("350000")  # HT du devis, pas le TTC
    assert mission.statut == StatutMission.BROUILLON


def test_le_devis_devient_convertie_et_reference_la_mission():
    proforma = _acceptee()

    mission = services.creer_mission_depuis_proforma(proforma)

    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.CONVERTIE
    assert mission.proforma_id == proforma.pk
    assert proforma.mission_creee == mission


@pytest.mark.parametrize(
    "statut",
    [StatutProforma.BROUILLON, StatutProforma.SOUMISE, StatutProforma.VALIDEE, StatutProforma.ENVOYEE_CLIENT],
)
def test_creation_impossible_hors_devis_accepte(statut):
    proforma = _acceptee()
    proforma.statut = statut
    proforma.save(update_fields=["statut"])

    with pytest.raises(TransitionMissionInterdite):
        services.creer_mission_depuis_proforma(proforma)


def test_un_devis_deja_converti_ne_recree_pas_de_seconde_mission():
    proforma = _acceptee()
    services.creer_mission_depuis_proforma(proforma)

    with pytest.raises(TransitionMissionInterdite):
        services.creer_mission_depuis_proforma(proforma)
