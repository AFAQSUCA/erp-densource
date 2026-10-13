import pytest
from django.test import RequestFactory

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit import services
from apps.audit.models import ActionChoices, StatutChoices

pytestmark = pytest.mark.django_db


def test_log_action_captures_ip_and_user_agent_from_request():
    user = UserFactory(role=Role.PARCAUTO)
    request = RequestFactory().post(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_USER_AGENT="pytest-agent"
    )

    entry = services.log_action(
        action=ActionChoices.UPDATE,
        module="FLEET",
        entite="Vehicule",
        entite_id=42,
        utilisateur=user,
        request=request,
    )

    assert entry.adresse_ip == "10.0.0.5"
    assert entry.user_agent == "pytest-agent"
    assert entry.role == Role.PARCAUTO
    assert entry.utilisateur_nom == user.get_full_name()


def test_log_action_ignore_x_forwarded_for_sans_proxy_de_confiance():
    """Sans proxy déclaré, l'en-tête écrit par le client ne doit jamais servir d'adresse."""
    request = RequestFactory().get(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4"
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "10.0.0.5"


def test_log_action_lit_l_adresse_ajoutee_par_les_proxys_de_confiance(settings):
    settings.TRUSTED_PROXY_COUNT = 2
    request = RequestFactory().get(
        "/x",
        REMOTE_ADDR="10.0.0.5",
        HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1",
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "203.0.113.9"


def test_log_login_failed_records_failed_status_and_attempted_username():
    request = RequestFactory().post("/login")
    UserFactory(username="awa.kone")

    entry = services.log_login_failed("awa.kone", request)

    assert entry.statut == StatutChoices.FAILED
    assert entry.nouvelle_valeur == {"username_tente": "awa.kone"}  # compte existant : en entier
    assert entry.utilisateur is None


def test_un_identifiant_inconnu_est_masque_car_ce_peut_etre_un_mot_de_passe():
    """Audit AUD-17 : un mot de passe tapé dans le champ « Identifiant » ne doit pas finir lisible au journal."""
    entry = services.log_login_failed("MonSecret2026!", RequestFactory().post("/login"))

    assert entry.nouvelle_valeur == {"username_tente": "Mo… (14 caractères, compte inconnu)"}
    assert "Secret" not in str(entry.nouvelle_valeur)


# --- nom et rôle de l'auteur (audit M1-53, M1-54) ---


def test_un_superutilisateur_sans_nom_est_journalise_avec_son_identifiant_et_le_role_admin():
    racine = UserFactory(username="racine", first_name="", last_name="", role="", is_superuser=True)

    entree = services.log_action(action=ActionChoices.UPDATE, module="TEST", entite="X", utilisateur=racine)

    assert entree.utilisateur_nom == "racine"
    assert entree.role == Role.ADMIN  # rôle effectif : un superutilisateur agit en ADMIN


def test_un_compte_avec_un_nom_complet_garde_son_nom_et_son_role():
    compte = UserFactory(first_name="Awa", last_name="Kone", role=Role.RH)

    entree = services.log_action(action=ActionChoices.UPDATE, module="TEST", entite="X", utilisateur=compte)

    assert entree.utilisateur_nom == "Awa Kone" and entree.role == Role.RH


def test_une_action_sans_auteur_n_a_ni_nom_ni_role():
    entree = services.log_action(action=ActionChoices.UPDATE, module="TEST", entite="X")

    assert entree.utilisateur_nom == "" and entree.role == ""
