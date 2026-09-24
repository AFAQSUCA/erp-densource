"""Connexion, accueil, menu par rôle et garde d'accès."""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts import navigation
from apps.accounts.models import Role
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


# --- connexion / déconnexion ---


def test_la_page_de_connexion_s_affiche(client):
    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 200
    assert "Se connecter" in reponse.content.decode()


def test_connexion_reussie_redirige_vers_l_accueil_et_est_tracee(client):
    utilisateur = UserFactory(username="awa", role=Role.DIRECTION)

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": MOT_DE_PASSE}
    )

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, utilisateur=utilisateur, statut=StatutChoices.SUCCESS
    ).exists()


def test_connexion_avec_un_mauvais_mot_de_passe_affiche_une_erreur_et_est_tracee(client):
    UserFactory(username="awa")

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": "faux"}
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].non_field_errors()
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, statut=StatutChoices.FAILED
    ).exists()


def test_un_utilisateur_connecte_qui_ouvre_la_connexion_va_a_l_accueil(client):
    _connecte(client, Role.RH)

    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")


def test_deconnexion_par_post_ferme_la_session_et_est_tracee(client):
    utilisateur = _connecte(client, Role.RH)

    reponse = client.post(reverse("accounts:logout"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("accounts:login")
    assert client.get(reverse("home")).status_code == 302
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGOUT, utilisateur=utilisateur
    ).exists()


def test_la_deconnexion_refuse_le_get(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("accounts:logout")).status_code == 405


def test_la_deconnexion_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory())

    assert client.post(reverse("accounts:logout")).status_code == 403


def test_la_session_expire_apres_30_minutes_d_inactivite():
    assert settings.SESSION_COOKIE_AGE == 30 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


# --- accueil ---


def test_l_accueil_exige_une_connexion_et_conserve_la_destination(client):
    reponse = client.get(reverse("home"))

    assert reponse.status_code == 302
    assert reponse.url == f"{reverse('accounts:login')}?next=/"


def test_l_accueil_salue_l_utilisateur(client):
    utilisateur = UserFactory(role=Role.DIRECTION, first_name="Awa")
    client.force_login(utilisateur)

    contenu = client.get(reverse("home")).content.decode()

    assert "Bonjour Awa" in contenu
    assert "Direction" in contenu


def test_le_menu_depend_du_role(client):
    _connecte(client, Role.DIRECTION)
    assert 'href="/missions/"' in client.get(reverse("home")).content.decode()

    finances = Client()
    _connecte(finances, Role.FINANCES)  # seuls les congés sont ouverts à ce rôle pour l'instant
    contenu = finances.get(reverse("home")).content.decode()
    assert 'href="/missions/"' not in contenu
    assert 'href="/rh/conges/"' in contenu
    assert "Aucun écran n" not in contenu

    chauffeur = Client()
    _connecte(chauffeur, Role.CHAUFFEUR)  # passe par l'espace mobile : aucun écran web
    assert "Aucun écran n" in chauffeur.get(reverse("home")).content.decode()


def test_un_chauffeur_est_renvoye_vers_l_espace_mobile(client):
    _connecte(client, Role.CHAUFFEUR)

    assert "espace mobile" in client.get(reverse("home")).content.decode()


def test_un_superutilisateur_sans_role_agit_en_admin(client):
    admin = UserFactory(role="", is_superuser=True, is_staff=True)
    client.force_login(admin)

    assert admin.role_effectif == Role.ADMIN
    assert client.get(reverse("missions:liste")).status_code == 200


# --- pages d'erreur ---


def test_un_role_non_autorise_recoit_la_page_403(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("missions:liste"))

    assert reponse.status_code == 403
    assert "Accès refusé" in reponse.content.decode()


def test_une_page_inexistante_affiche_la_page_404(client, settings):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["testserver"]
    _connecte(client, Role.DIRECTION)

    reponse = client.get("/n-existe-pas/")

    assert reponse.status_code == 404
    assert "Page introuvable" in reponse.content.decode()


# --- navigation ---


def test_entrees_pour_filtre_par_role_trie_et_marque_l_entree_active(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    reserve_rh = navigation.EntreeMenu(
        "Réservé RH", "missions:liste", "fa-flask", frozenset({Role.RH}), ordre=5
    )
    monkeypatch.setattr(
        navigation, "_ENTREES", {"missions:liste": reserve_rh, "home": accueil}
    )

    rh = navigation.entrees_pour(Role.RH, "/missions/")
    finances = navigation.entrees_pour(Role.FINANCES, "/missions/")

    assert [e["libelle"] for e in rh] == ["Accueil", "Réservé RH"]
    assert [e["actif"] for e in rh] == [False, True]
    assert [e["libelle"] for e in finances] == ["Accueil"]


def test_l_accueil_n_est_actif_que_sur_la_racine(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil})

    assert navigation.entrees_pour(Role.RH, "/")[0]["actif"] is True
    assert navigation.entrees_pour(Role.RH, "/missions/")[0]["actif"] is False


def test_une_entree_dont_l_ecran_n_existe_pas_est_ignoree_sans_erreur(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    fantome = navigation.EntreeMenu("Fantôme", "ecran:inexistant", "fa-ghost", None, ordre=1)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil, "ecran:inexistant": fantome})

    assert [e["libelle"] for e in navigation.entrees_pour(Role.RH, "/")] == ["Accueil"]


def test_aucun_commentaire_de_template_ne_fuit_dans_les_pages(client):
    """`{# ... #}` multi-lignes s'afficherait en texte brut : régression déjà vue."""
    pages = [reverse("accounts:login")]
    _connecte(client, Role.DIRECTION)
    pages += [reverse("home"), reverse("missions:liste"), reverse("missions:creer")]

    for url in pages:
        contenu = client.get(url).content.decode()
        assert "{#" not in contenu and "#}" not in contenu, url
        assert "{%" not in contenu and "%}" not in contenu, url


def test_un_seul_onglet_est_actif_meme_quand_deux_adresses_se_ressemblent():
    """« Dépenses » (/facturation/depenses/) est sous « Facturation » (/facturation/) : seul le plus précis
    s'allume, le clic sur un onglet ne doit pas en activer un autre."""
    actifs = lambda chemin: [e["libelle"] for e in navigation.entrees_pour(Role.ADMIN, chemin) if e["actif"]]

    assert actifs("/facturation/depenses/") == ["Dépenses"]
    assert actifs("/facturation/") == ["Facturation"]
    assert actifs("/facturation/12/") == ["Facturation"]
    assert actifs("/garage/incidents/3/") == ["Incidents"]
    assert actifs("/garage/") == ["Garage"]
    assert actifs("/") == ["Accueil"]
    assert actifs("/page-inconnue/") == []
