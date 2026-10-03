"""Audit M5-10 : le compteur d'un camion ne recule jamais, sauf correction tracée de l'ADMIN (motif obligatoire)."""

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.fleet import services
from apps.fleet.exceptions import ActionNonAutorisee, KilometrageInvalide

from .factories import VehiculeFactory

pytestmark = pytest.mark.django_db


def _admin():
    return UserFactory(role=Role.ADMIN)


def test_l_admin_corrige_un_compteur_gonfle_et_la_correction_est_tracee():
    camion = VehiculeFactory(kilometrage=1200000)  # un zéro de trop
    admin = _admin()

    services.corriger_kilometrage(camion, admin, kilometrage=120000, motif="Faute de frappe sur le plein T-42")

    camion.refresh_from_db()
    assert camion.kilometrage == 120000
    trace = AuditLog.objects.filter(entite="Vehicule", entite_id=camion.pk, nouvelle_valeur__motif__isnull=False).get()
    assert trace.ancienne_valeur == {"correction_kilometrage": 1200000}
    assert trace.nouvelle_valeur == {"correction_kilometrage": 120000, "motif": "Faute de frappe sur le plein T-42"}
    assert trace.utilisateur == admin


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_autres_roles_ne_corrigent_pas_le_compteur(role):
    camion = VehiculeFactory(kilometrage=5000)

    with pytest.raises(ActionNonAutorisee):
        services.corriger_kilometrage(camion, UserFactory(role=role), kilometrage=100, motif="Test")

    camion.refresh_from_db()
    assert camion.kilometrage == 5000


def test_le_motif_est_obligatoire_et_la_valeur_doit_changer():
    camion = VehiculeFactory(kilometrage=5000)

    with pytest.raises(KilometrageInvalide, match="motif"):
        services.corriger_kilometrage(camion, _admin(), kilometrage=100, motif="  ")
    with pytest.raises(KilometrageInvalide, match="déjà"):
        services.corriger_kilometrage(camion, _admin(), kilometrage=5000, motif="Rien")
    with pytest.raises(KilometrageInvalide, match="négatif"):
        services.corriger_kilometrage(camion, _admin(), kilometrage=-1, motif="Test")


def test_l_ecran_propose_la_correction_a_l_admin_seulement(client):
    camion = VehiculeFactory(kilometrage=1200000)
    url_detail = reverse("fleet:detail", args=[camion.pk])
    url_action = reverse("fleet:compteur", args=[camion.pk])

    client.force_login(_admin())
    assert url_action in client.get(url_detail).content.decode()
    client.force_login(UserFactory(role=Role.PARCAUTO))
    assert url_action not in client.get(url_detail).content.decode()
    assert client.post(url_action, {"kilometrage": 10, "motif": "x"}).status_code == 403


def test_corriger_via_l_ecran(client):
    camion = VehiculeFactory(kilometrage=1200000)
    client.force_login(_admin())

    reponse = client.post(
        reverse("fleet:compteur", args=[camion.pk]), {"kilometrage": 120000, "motif": "Faute de frappe"}, follow=True
    )

    camion.refresh_from_db()
    assert camion.kilometrage == 120000
    assert any("corrigé" in str(m) for m in reponse.context["messages"])
