"""Fichiers téléversés : jamais en accès libre, servis selon le rôle (audit : pièces jointes financières)."""

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.medias import MediaProtegeView

pytestmark = pytest.mark.django_db


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "demandes_depense" / "2026" / "09").mkdir(parents=True)
    (tmp_path / "demandes_depense" / "2026" / "09" / "devis.pdf").write_bytes(b"%PDF-devis")
    (tmp_path / "demandes_depense" / "2026" / "09" / "page.html").write_text("<script>alert(1)</script>")
    (tmp_path / "frais_mission" / "justificatifs").mkdir(parents=True)
    (tmp_path / "frais_mission" / "justificatifs" / "preuve.png").write_bytes(b"\x89PNG")
    (tmp_path / "secret.txt").write_text("hors préfixe")
    return tmp_path


def _url(chemin):
    return reverse("media", args=[chemin])


def test_un_visiteur_anonyme_est_renvoye_vers_la_connexion(client, media):
    reponse = client.get(_url("demandes_depense/2026/09/devis.pdf"))

    assert reponse.status_code == 302 and "/connexion/" in reponse["Location"]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.PARCAUTO, Role.RH])
def test_un_role_autorise_lit_la_piece_jointe_d_une_demande(client, media, role):
    client.force_login(UserFactory(role=role))

    reponse = client.get(_url("demandes_depense/2026/09/devis.pdf"))

    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content) == b"%PDF-devis"
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse["Content-Disposition"].startswith("inline")
    assert reponse["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.CHARGE_CLIENTELE])
def test_un_role_non_autorise_ne_voit_pas_la_piece_jointe(client, media, role):
    client.force_login(UserFactory(role=role))

    assert client.get(_url("demandes_depense/2026/09/devis.pdf")).status_code == 404


def test_les_justificatifs_de_frais_suivent_les_droits_des_frais(client, media):
    client.force_login(UserFactory(role=Role.FINANCES))
    assert client.get(_url("frais_mission/justificatifs/preuve.png")).status_code == 200

    client.force_login(UserFactory(role=Role.CHAUFFEUR))
    assert client.get(_url("frais_mission/justificatifs/preuve.png")).status_code == 404


def test_un_fichier_html_est_telecharge_jamais_affiche(client, media):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(_url("demandes_depense/2026/09/page.html"))

    assert reponse.status_code == 200
    assert reponse["Content-Disposition"].startswith("attachment")


def test_un_prefixe_non_declare_n_est_servi_a_personne(client, media):
    client.force_login(UserFactory(role=Role.ADMIN))

    assert client.get(_url("secret.txt")).status_code == 404


def test_la_sortie_du_dossier_media_est_refusee(client, media):
    client.force_login(UserFactory(role=Role.ADMIN))

    assert client.get(_url("demandes_depense/../secret.txt")).status_code == 404
    assert client.get(_url("demandes_depense/../../secret.txt")).status_code == 404


def test_un_fichier_absent_donne_404(client, media):
    client.force_login(UserFactory(role=Role.ADMIN))

    assert client.get(_url("demandes_depense/2026/09/absent.pdf")).status_code == 404


def test_en_production_django_delegue_l_envoi_a_nginx(client, media, settings):
    settings.MEDIA_ACCEL_REDIRECT = True
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(_url("demandes_depense/2026/09/devis.pdf"))

    assert reponse.status_code == 200
    assert reponse["X-Accel-Redirect"] == "/medias-internes/demandes_depense/2026/09/devis.pdf"
    assert reponse.content == b""


def test_en_production_un_role_non_autorise_n_obtient_pas_de_redirection(client, media, settings):
    settings.MEDIA_ACCEL_REDIRECT = True
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    reponse = client.get(_url("demandes_depense/2026/09/devis.pdf"))

    assert reponse.status_code == 404 and "X-Accel-Redirect" not in reponse


def test_les_liens_des_champs_fichier_passent_par_la_vue_protegee(settings):
    from apps.finance.models import DemandeDepense

    champ = DemandeDepense._meta.get_field("piece_jointe")

    assert champ.storage.url("demandes_depense/2026/09/devis.pdf") == "/medias/demandes_depense/2026/09/devis.pdf"
    assert MediaProtegeView.http_method_names == ["get"]
