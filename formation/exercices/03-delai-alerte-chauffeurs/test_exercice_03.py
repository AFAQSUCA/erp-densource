"""Exercice 3 — Un délai d'alerte propre aux chauffeurs (formation/exercices/03-delai-alerte-chauffeurs).

À copier dans apps/parametres/tests/ puis : python -m pytest apps/parametres/tests/test_exercice_03.py -q --no-cov
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers import services as drivers_services
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet import services as fleet_services
from apps.fleet.models import DocumentReglementaire, TypeDocument
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.notifications import taches
from apps.parametres import services
from apps.parametres.services import ParametresInvalides

pytestmark = pytest.mark.django_db


def _direction():
    return UserFactory(role=Role.DIRECTION)


def test_par_defaut_le_delai_des_chauffeurs_est_celui_du_cahier_des_charges():
    assert services.parametres().delai_alerte_chauffeurs_jours == 30
    assert services.delai_alerte_chauffeurs() == 30
    assert services.delai_alerte_chauffeurs(7) == 7  # un délai passé explicitement l'emporte


def test_il_se_modifie_et_garde_ses_bornes():
    services.modifier_parametres(_direction(), delai_alerte_chauffeurs_jours=60)
    assert services.parametres().delai_alerte_chauffeurs_jours == 60

    with pytest.raises(ParametresInvalides):
        services.modifier_parametres(_direction(), delai_alerte_chauffeurs_jours=0)


def test_les_chauffeurs_suivent_leur_delai_et_les_camions_le_leur():
    services.modifier_parametres(_direction(), delai_alerte_chauffeurs_jours=60)  # camions : 30 jours par défaut
    dans_45_jours = timezone.localdate() + timedelta(days=45)
    chauffeur = ChauffeurFactory(date_expiration_permis=dans_45_jours)
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.ASSURANCE).update(
        date_expiration=dans_45_jours
    )

    assert chauffeur in drivers_services.chauffeurs_a_renouveler()
    assert not fleet_services.documents_a_renouveler().filter(vehicule=camion).exists()


def test_la_notification_quotidienne_utilise_le_delai_des_chauffeurs():
    UserFactory(role=Role.RH)
    services.modifier_parametres(_direction(), delai_alerte_chauffeurs_jours=60)
    ChauffeurFactory(date_expiration_permis=timezone.localdate() + timedelta(days=45))

    assert taches.alerter_echeances_chauffeurs() >= 1


def test_l_ecran_des_parametres_propose_le_nouveau_reglage(client):
    client.force_login(_direction())

    page = client.get(reverse("parametres:modifier")).content.decode()

    assert 'name="delai_alerte_chauffeurs_jours"' in page
