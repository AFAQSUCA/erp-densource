"""Écran du journal d'audit : accès, filtres, export CSV, rapport imprimable."""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit import services
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode()


def _entree(**surcharges):
    donnees = dict(
        action=ActionChoices.UPDATE, module="FLEET", entite="Vehicule", entite_id=1,
        utilisateur_nom="Awa Koné", role=Role.PARCAUTO, adresse_ip="10.0.0.1",
    )
    donnees.update(surcharges)
    entree = AuditLog.objects.create(**donnees)
    if "date_heure" in surcharges:
        AuditLog.objects.filter(pk=entree.pk).update(date_heure=surcharges["date_heure"])
        entree.refresh_from_db()
    return entree


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_le_journal_est_accessible_a_admin_et_direction(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("audit:journal")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE])
def test_le_journal_est_interdit_aux_autres_roles(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("audit:journal")).status_code == 403


# --- filtres ---


def test_la_recherche_porte_sur_l_utilisateur_l_entite_et_l_ip(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(utilisateur_nom="Fatou Diallo", entite="Facture", adresse_ip="41.1.1.1")
    _entree(utilisateur_nom="Ibrahim Sanogo", entite="Vehicule", adresse_ip="41.2.2.2")

    reponse = client.get(reverse("audit:journal"), {"q": "Fatou"})

    assert "Fatou Diallo" in _texte(reponse) and "Ibrahim Sanogo" not in _texte(reponse)


def test_le_filtre_module_et_action_se_combinent(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(module="RH", action=ActionChoices.CREATE)
    _entree(module="RH", action=ActionChoices.DELETE)
    _entree(module="FLEET", action=ActionChoices.CREATE)

    reponse = services.rechercher(module="RH", action=ActionChoices.CREATE)

    assert reponse.count() == 1


def test_le_filtre_de_periode_borne_la_date(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    dans_la_periode = _entree(date_heure=datetime(2026, 9, 10, tzinfo=dt_timezone.utc))
    hors_periode = _entree(date_heure=datetime(2026, 8, 1, tzinfo=dt_timezone.utc))

    resultat = services.rechercher(date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 30))

    assert dans_la_periode in resultat and hors_periode not in resultat


def test_le_statut_echec_est_filtrable(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(statut=StatutChoices.FAILED, module="AUTH")
    _entree(statut=StatutChoices.SUCCESS, module="AUTH")

    assert services.rechercher(statut=StatutChoices.FAILED).count() == 1


def test_le_filtre_module_liste_les_modules_deja_presents():
    _entree(module="RH")
    _entree(module="FLEET")

    assert services.modules_utilises() == ["FLEET", "RH"]


# --- export CSV ---


def test_export_csv_reprend_les_filtres_et_contient_les_colonnes(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(utilisateur_nom="Awa Koné", module="RH", entite="Personnel", entite_id=7)
    _entree(utilisateur_nom="Fatou Diallo", module="FINANCES")

    reponse = client.get(reverse("audit:export_csv"), {"module": "RH"})

    assert reponse["Content-Type"].startswith("text/csv")
    contenu = reponse.content.decode("utf-8-sig")
    assert "Awa Koné" in contenu and "Fatou Diallo" not in contenu
    assert "Date/heure;Utilisateur;Rôle;Action;Module;Entité;ID entité;Statut;Adresse IP" in contenu


def test_export_csv_interdit_hors_role(client):
    client.force_login(UserFactory(role=Role.RH))

    assert client.get(reverse("audit:export_csv")).status_code == 403


# --- rapport imprimable ---


def test_impression_du_journal(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    _entree(utilisateur_nom="Awa Koné", module="RH", action=ActionChoices.VALIDATE)

    texte = _texte(client.get(reverse("audit:imprimer"), {"module": "RH"}))

    assert "Journal d" in texte and "audit</h1>" in texte  # apostrophe échappée en HTML (&#x27;)
    assert "Awa Koné" in texte and "module : RH" in texte


def test_le_lien_imprimer_et_l_export_sont_sur_la_liste(client):
    client.force_login(UserFactory(role=Role.ADMIN))

    page = client.get(reverse("audit:journal"), {"module": "RH"}).content.decode()

    assert reverse("audit:imprimer") in page and reverse("audit:export_csv") in page
    assert "module%3DRH" in page or "module=RH" in page


# --- menu ---


def test_le_journal_apparait_dans_le_menu_de_l_admin_et_de_la_direction():
    from apps.accounts.navigation import entrees_pour

    for role in (Role.ADMIN, Role.DIRECTION):
        assert any(e["url"] == reverse("audit:journal") for e in entrees_pour(role, "/"))
    assert not any(e["url"] == reverse("audit:journal") for e in entrees_pour(Role.RH, "/"))
