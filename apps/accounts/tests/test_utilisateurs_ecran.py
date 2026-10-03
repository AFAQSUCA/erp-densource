"""Écran « Utilisateurs » (audit M1-02) : l'ADMIN crée, modifie, active et désactive les comptes — jamais un
superutilisateur, jamais soi-même, toujours tracé."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts import services
from apps.accounts.models import Role, User
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Camion-vert-2026!"


def _admin():
    return UserFactory(role=Role.ADMIN, is_staff=False)


def _donnees(**surcharges):
    donnees = {
        "username": "awa.kone", "first_name": "Awa", "last_name": "Koné", "email": "awa@densource.ci",
        "telephone": "+2250700000000", "role": Role.FINANCES, "password1": MOT_DE_PASSE, "password2": MOT_DE_PASSE,
    }
    donnees.update(surcharges)
    return donnees


@pytest.fixture
def admin_client(client):
    client.force_login(_admin())
    return client


# --- droits ---


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHAUFFEUR])
def test_seul_l_admin_accede_a_l_ecran_des_utilisateurs(client, role):
    client.force_login(UserFactory(role=role))

    for nom in ("utilisateurs", "utilisateur_nouveau"):
        assert client.get(reverse(f"accounts:{nom}")).status_code == 403
    cible = UserFactory(role=Role.RH)
    assert client.post(reverse("accounts:utilisateur_activation", args=[cible.pk]), {"actif": "non"}).status_code == 403
    cible.refresh_from_db()
    assert cible.is_active


def test_le_menu_propose_utilisateurs_a_l_admin_seulement(client):
    client.force_login(_admin())
    assert reverse("accounts:utilisateurs") in client.get(reverse("home")).content.decode()
    client.force_login(UserFactory(role=Role.FINANCES))
    assert reverse("accounts:utilisateurs") not in client.get(reverse("home")).content.decode()


# --- création ---


def test_l_admin_cree_un_compte_qui_peut_se_connecter(admin_client):
    reponse = admin_client.post(reverse("accounts:utilisateur_nouveau"), _donnees(), follow=True)

    compte = User.objects.get(username="awa.kone")
    assert compte.role == Role.FINANCES and compte.is_active and not compte.is_staff and not compte.is_superuser
    assert compte.check_password(MOT_DE_PASSE)
    assert any("créé" in str(m) for m in reponse.context["messages"])
    assert AuditLog.objects.filter(entite="User", entite_id=compte.pk, action=ActionChoices.CREATE).exists()


def test_le_mot_de_passe_n_est_jamais_ecrit_en_clair_dans_le_journal(admin_client):
    admin_client.post(reverse("accounts:utilisateur_nouveau"), _donnees())

    trace = AuditLog.objects.get(entite="User", action=ActionChoices.CREATE, nouvelle_valeur__username="awa.kone")

    assert MOT_DE_PASSE not in str(trace.nouvelle_valeur) and trace.nouvelle_valeur["password"].startswith("masqué:")


@pytest.mark.parametrize(
    "surcharges, attendu",
    [
        ({"password2": "autre-chose-1234"}, "ne correspondent pas"),
        ({"password1": "court1", "password2": "court1"}, "trop court"),
        ({"password1": "1234567890", "password2": "1234567890"}, "numérique"),
        ({"username": "ADMIN.EXISTANT"}, "déjà pris"),
        ({"email": ""}, "obligatoire"),
        ({"role": "SUPER"}, "Sélectionnez"),
    ],
)
def test_une_creation_invalide_est_refusee_avec_son_message(admin_client, surcharges, attendu):
    UserFactory(username="admin.existant")

    reponse = admin_client.post(reverse("accounts:utilisateur_nouveau"), _donnees(**surcharges))

    assert reponse.status_code == 200 and attendu in reponse.content.decode()
    assert not User.objects.filter(username="awa.kone").exists()


def test_un_email_deja_utilise_est_refuse(admin_client):
    UserFactory(email="awa@densource.ci")

    reponse = admin_client.post(reverse("accounts:utilisateur_nouveau"), _donnees())

    assert "déjà utilisée" in reponse.content.decode()


# --- modification et activation ---


def test_l_admin_change_le_role_et_la_modification_est_tracee(admin_client):
    compte = UserFactory(role=Role.RH, email="rh@densource.ci")

    admin_client.post(
        reverse("accounts:utilisateur_modifier", args=[compte.pk]),
        {"first_name": "Marie", "last_name": "Yao", "email": "rh@densource.ci", "telephone": "", "role": Role.FINANCES},
    )

    compte.refresh_from_db()
    assert compte.role == Role.FINANCES and compte.first_name == "Marie"
    trace = AuditLog.objects.filter(entite="User", entite_id=compte.pk, action=ActionChoices.UPDATE).latest("date_heure")
    assert trace.ancienne_valeur["role"] == Role.RH and trace.nouvelle_valeur["role"] == Role.FINANCES


def test_on_ne_change_pas_son_propre_role(client):
    admin = _admin()
    client.force_login(admin)

    reponse = client.post(
        reverse("accounts:utilisateur_modifier", args=[admin.pk]),
        {"first_name": "A", "last_name": "B", "email": "a@b.ci", "telephone": "", "role": Role.CHAUFFEUR},
    )

    admin.refresh_from_db()
    assert admin.role == Role.ADMIN and "propre rôle" in reponse.content.decode()


def test_desactiver_puis_reactiver_un_compte(admin_client):
    compte = UserFactory(role=Role.RH)
    url = reverse("accounts:utilisateur_activation", args=[compte.pk])

    admin_client.post(url, {"actif": "non"})
    compte.refresh_from_db()
    assert compte.is_active is False
    admin_client.post(url, {"actif": "oui"})
    compte.refresh_from_db()
    assert compte.is_active is True


def test_un_compte_desactive_ne_se_connecte_plus(admin_client):
    compte = UserFactory(role=Role.RH, username="rh.desactive")
    compte.set_password(MOT_DE_PASSE)
    compte.save()
    admin_client.post(reverse("accounts:utilisateur_activation", args=[compte.pk]), {"actif": "non"})

    assert Client().login(username="rh.desactive", password=MOT_DE_PASSE) is False


def test_on_ne_se_desactive_pas_soi_meme(client):
    admin = _admin()
    client.force_login(admin)

    client.post(reverse("accounts:utilisateur_activation", args=[admin.pk]), {"actif": "non"})

    admin.refresh_from_db()
    assert admin.is_active


def test_un_superutilisateur_n_est_jamais_modifie_ni_desactive_par_cet_ecran(admin_client):
    super_ = UserFactory(role=Role.ADMIN, is_superuser=True, is_staff=True)

    reponse = admin_client.post(reverse("accounts:utilisateur_activation", args=[super_.pk]), {"actif": "non"}, follow=True)
    modification = admin_client.post(
        reverse("accounts:utilisateur_modifier", args=[super_.pk]),
        {"first_name": "X", "last_name": "Y", "email": "x@y.ci", "telephone": "", "role": Role.CHAUFFEUR},
    )

    super_.refresh_from_db()
    assert super_.is_active and super_.role == Role.ADMIN and super_.first_name != "X"
    assert "superutilisateur" in reponse.content.decode().lower()
    assert "superutilisateur" in modification.content.decode().lower()


def test_les_services_refusent_un_acteur_qui_n_est_pas_admin():
    with pytest.raises(services.ActionUtilisateurNonAutorisee):
        services.creer_utilisateur(
            UserFactory(role=Role.DIRECTION), username="x", first_name="", last_name="", email="x@y.ci",
            role=Role.RH, password=MOT_DE_PASSE,
        )


def test_la_liste_se_filtre_par_role_statut_et_texte(admin_client):
    UserFactory(username="rh.un", role=Role.RH)
    UserFactory(username="fin.un", role=Role.FINANCES, is_active=False)

    en_rh = admin_client.get(reverse("accounts:utilisateurs"), {"role": Role.RH}).content.decode()
    inactifs = admin_client.get(reverse("accounts:utilisateurs"), {"actif": "non"}).content.decode()
    texte = admin_client.get(reverse("accounts:utilisateurs"), {"q": "fin.un"}).content.decode()

    assert "rh.un" in en_rh and "fin.un" not in en_rh
    assert "fin.un" in inactifs and "rh.un" not in inactifs
    assert "fin.un" in texte and "rh.un" not in texte
