"""Changer son mot de passe une fois connecté — cahier-des-charges.md:273, audit TECH-87."""

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

ANCIEN, NOUVEAU = "Ancien-Secret-2026", "Nouveau-Secret-2027"
URL = reverse("accounts:password_change")


def _connecte(client, role=Role.RH):
    compte = UserFactory(role=role)
    compte.set_password(ANCIEN)
    compte.save()
    client.force_login(compte)
    return compte


def _changer(client, ancien=ANCIEN, nouveau=NOUVEAU, confirmation=None):
    return client.post(
        URL, {"old_password": ancien, "new_password1": nouveau, "new_password2": confirmation or nouveau}, follow=True
    )


def test_l_ecran_est_accessible_une_fois_connecte_et_lie_dans_l_en_tete(client):
    _connecte(client)

    assert client.get(URL).status_code == 200
    assert f'href="{URL}"' in client.get(reverse("home")).content.decode()


def test_un_visiteur_non_connecte_est_renvoye_a_la_connexion(client):
    reponse = client.get(URL)

    assert reponse.status_code == 302 and reverse("accounts:login") in reponse["Location"]


def test_le_mot_de_passe_change_sans_deconnecter_et_l_evenement_est_trace(client):
    compte = _connecte(client)

    reponse = _changer(client)

    compte.refresh_from_db()
    assert compte.check_password(NOUVEAU) and not compte.check_password(ANCIEN)
    assert any("mot de passe a été changé" in str(m) for m in reponse.context["messages"])
    assert client.get(URL).status_code == 200  # toujours connecté
    trace = AuditLog.objects.get(entite="User", entite_id=compte.pk, nouvelle_valeur__evenement="mot_de_passe_change")
    assert NOUVEAU not in str(trace.nouvelle_valeur) and ANCIEN not in str(trace.nouvelle_valeur)


def test_l_ancien_mot_de_passe_est_exige(client):
    compte = _connecte(client)

    reponse = _changer(client, ancien="pas-le-bon-mot")

    compte.refresh_from_db()
    assert compte.check_password(ANCIEN)
    assert "ancien mot de passe" in reponse.content.decode().lower()


def test_un_mot_de_passe_trop_simple_ou_mal_confirme_est_refuse(client):
    compte = _connecte(client)

    for nouveau, confirmation in (("court", "court"), (NOUVEAU, "Autre-Secret-2027")):
        reponse = _changer(client, nouveau=nouveau, confirmation=confirmation)
        assert reponse.status_code == 200 and "text-red-700" in reponse.content.decode()  # erreur sous le champ

    compte.refresh_from_db()
    assert compte.check_password(ANCIEN)


def test_le_chauffeur_peut_aussi_changer_son_mot_de_passe(client):
    compte = _connecte(client, Role.CHAUFFEUR)

    _changer(client)

    compte.refresh_from_db()
    assert compte.check_password(NOUVEAU)
