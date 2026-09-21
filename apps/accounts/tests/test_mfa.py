"""Double authentification : règles (mfa.py), porte (middleware) et écrans."""

import io

import pyotp
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from apps.accounts import mfa
from apps.accounts.models import AppareilMFA, CodeSecours, Role, User
from apps.audit.models import AuditLog, StatutChoices

from .factories import UserFactory
from .helpers_mfa import activer_mfa, code_frais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mfa_imposee(settings):
    """Dans ce fichier la MFA est imposée (les autres tests du projet la laissent désactivée)."""
    settings.MFA_ENFORCED = True
    cache.clear()


@pytest.fixture
def direction():
    return UserFactory(role=Role.DIRECTION)


def _connecte(client, utilisateur):
    client.force_login(utilisateur)
    return utilisateur


# --- qui est soumis à la MFA ---


@pytest.mark.parametrize("role, attendu", [
    (Role.ADMIN, True), (Role.DIRECTION, True), (Role.RH, False), (Role.CHARGE_CLIENTELE, False),
    (Role.PARCAUTO, False), (Role.FINANCES, False), (Role.CHAUFFEUR, False),
])
def test_seuls_l_admin_et_la_direction_sont_soumis_a_la_mfa(role, attendu):
    assert mfa.mfa_requise(UserFactory(role=role)) is attendu


def test_un_superutilisateur_sans_role_est_soumis_a_la_mfa():
    assert mfa.mfa_requise(UserFactory(role="", is_superuser=True)) is True


def test_la_mfa_peut_etre_desactivee_par_reglage(settings, direction):
    settings.MFA_ENFORCED = False
    assert mfa.mfa_requise(direction) is False


# --- règles du service ---


def test_activation_avec_un_bon_code_donne_dix_codes_de_secours(direction):
    appareil = mfa.preparer_activation(direction)

    codes = mfa.confirmer_activation(direction, pyotp.TOTP(appareil.secret).now())

    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    direction.refresh_from_db()
    assert direction.mfa_enabled is True and mfa.appareil_actif(direction) is not None


def test_activation_avec_un_mauvais_code_est_refusee(direction):
    mfa.preparer_activation(direction)

    with pytest.raises(mfa.CodeInvalide):
        mfa.confirmer_activation(direction, "000000")

    direction.refresh_from_db()
    assert direction.mfa_enabled is False and mfa.appareil_actif(direction) is None


def test_on_ne_peut_pas_activer_deux_fois(direction):
    activer_mfa(direction)

    with pytest.raises(mfa.DejaActive):
        mfa.preparer_activation(direction)


def test_les_codes_de_secours_ne_sont_pas_conserves_en_clair(direction):
    _, codes = activer_mfa(direction)

    empreintes = set(CodeSecours.objects.filter(utilisateur=direction).values_list("empreinte", flat=True))

    assert len(empreintes) == 10
    assert all(c.replace("-", "") not in " ".join(empreintes) for c in codes)


def test_un_code_totp_ne_sert_qu_une_fois(direction):
    activer_mfa(direction)
    code = code_frais(direction)

    assert mfa.verifier_code(direction, code) is True
    assert mfa.verifier_code(direction, code) is False  # rejeu refusé


def test_un_code_totp_faux_ou_mal_forme_est_refuse(direction):
    activer_mfa(direction)

    for code in ("", "abcdef", "12345", "1234567", "000000"):
        assert mfa.verifier_code(direction, code) is False, code


def test_un_code_de_secours_ne_sert_qu_une_fois_meme_mal_saisi(direction):
    _, codes = activer_mfa(direction)
    code = codes[0]

    assert mfa.verifier_code(direction, code.lower().replace("-", " ")) is True
    assert mfa.verifier_code(direction, code) is False
    assert mfa.codes_secours_restants(direction) == 9


def test_verifier_sans_appareil_actif_est_refuse(direction):
    assert mfa.verifier_code(direction, "123456") is False


def test_regenerer_les_codes_exige_un_code_totp_et_annule_les_anciens(direction):
    _, anciens = activer_mfa(direction)

    with pytest.raises(mfa.CodeInvalide):
        mfa.regenerer_codes_secours(direction, anciens[0])  # un code de secours ne suffit pas
    nouveaux = mfa.regenerer_codes_secours(direction, code_frais(direction))

    assert set(nouveaux).isdisjoint(anciens)
    assert mfa.verifier_code(direction, anciens[1]) is False
    assert mfa.verifier_code(direction, nouveaux[0]) is True


def test_reinitialiser_supprime_l_appareil_et_les_codes(direction):
    activer_mfa(direction)

    mfa.reinitialiser(direction)

    direction.refresh_from_db()
    assert direction.mfa_enabled is False
    assert not AppareilMFA.objects.filter(utilisateur=direction).exists()
    assert not CodeSecours.objects.filter(utilisateur=direction).exists()


# --- la porte : refus par défaut tant que la MFA n'est pas passée ---

PAGES_DE_BUREAU = [
    "/", "/missions/", "/clients/", "/flotte/", "/rh/personnel/", "/rh/conges/", "/chauffeurs/",
    "/garage/", "/carburant/", "/stock/", "/facturation/", "/finances/", "/notifications/",
    "/admin/", "/api/v1/docs/",
]


@pytest.mark.parametrize("chemin", PAGES_DE_BUREAU)
def test_sans_appareil_toute_page_renvoie_vers_l_activation(client, direction, chemin):
    _connecte(client, direction)

    reponse = client.get(chemin)

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:mfa_activer"))


@pytest.mark.parametrize("chemin", PAGES_DE_BUREAU)
def test_avec_appareil_toute_page_renvoie_vers_la_verification(client, direction, chemin):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.get(chemin)

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:mfa_verifier"))


def test_la_page_demandee_est_conservee_pour_apres_la_verification(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.get("/missions/?q=abc")

    assert "next=/missions/%3Fq%3Dabc" in reponse["Location"]


def test_un_post_est_aussi_bloque(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post("/missions/nouvelle/", {})

    assert reponse.status_code == 302 and "mfa/verifier" in reponse["Location"]


def test_l_api_repond_403_json_plutot_qu_une_redirection(client, direction):
    _connecte(client, direction)

    reponse = client.get("/api/v1/moi/")

    assert reponse.status_code == 403 and reponse.json()["code"] == "mfa_requise"


def test_les_fichiers_statiques_et_la_deconnexion_restent_accessibles(client, direction):
    _connecte(client, direction)

    assert client.post(reverse("accounts:logout")).status_code == 302
    assert client.get("/static/img/favicon.png").status_code != 403  # jamais bloqué par la porte


def test_apres_verification_les_pages_s_ouvrent(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 302 and reponse["Location"] == reverse("home")
    assert client.get("/missions/").status_code == 200


def test_les_autres_roles_ne_sont_pas_concernes(client):
    for role in (Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES):
        client.force_login(UserFactory(role=role))
        assert client.get("/").status_code == 200, role
        for nom in ("mfa_verifier", "mfa_activer", "mfa_qr", "mfa_codes"):
            assert client.get(reverse(f"accounts:{nom}")).status_code == 404, (role, nom)


def test_une_nouvelle_ouverture_de_session_demande_a_nouveau_la_mfa(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})
    assert client.get("/missions/").status_code == 200

    client.force_login(direction)  # même personne, nouvelle ouverture de session

    assert client.get("/missions/").status_code == 302


def test_la_verification_change_l_identifiant_de_session(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    avant = client.session.session_key

    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert client.session.session_key != avant


# --- écran de vérification ---


def test_un_code_faux_est_refuse_et_rien_n_est_ouvert(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    assert reponse.status_code == 200 and "Code incorrect" in reponse.content.decode()
    assert client.get("/missions/").status_code == 302


def test_un_code_de_secours_ouvre_la_session_une_seule_fois(client, direction):
    _, codes = activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": codes[0]})
    assert reponse.status_code == 302 and client.get("/missions/").status_code == 200

    client.force_login(direction)
    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": codes[0]})
    assert reponse.status_code == 200 and client.get("/missions/").status_code == 302


def test_apres_cinq_codes_faux_meme_le_bon_code_est_refuse(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    for _ in range(5):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 429 and "Trop de codes incorrects" in reponse.content.decode()
    assert client.get("/missions/").status_code == 302


def test_un_bon_code_efface_les_echecs(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    for _ in range(4):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})
    client.force_login(direction)
    for _ in range(4):
        client.post(reverse("accounts:mfa_verifier"), {"code": "000000"})

    reponse = client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reponse.status_code == 302  # 4 + 4 échecs, mais le compteur avait été remis à zéro


@pytest.mark.parametrize("cible", ["https://pirate.example/", "//pirate.example/", "javascript:alert(1)"])
def test_la_redirection_apres_verification_refuse_les_adresses_externes(client, direction, cible):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(
        reverse("accounts:mfa_verifier") + f"?next={cible}", {"code": code_frais(direction)}
    )

    assert reponse["Location"] == reverse("home")


def test_la_verification_redirige_vers_la_page_demandee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    reponse = client.post(
        reverse("accounts:mfa_verifier") + "?next=/flotte/", {"code": code_frais(direction)}
    )

    assert reponse["Location"] == "/flotte/"


def test_la_page_de_verification_sans_appareil_renvoie_vers_l_activation(client, direction):
    _connecte(client, direction)

    reponse = client.get(reverse("accounts:mfa_verifier"))

    assert reponse["Location"] == reverse("accounts:mfa_activer")


def test_la_page_de_verification_est_protegee_par_csrf(direction):
    from django.test import Client

    activer_mfa(direction)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(direction)

    assert strict.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)}).status_code == 403


def test_un_anonyme_est_renvoye_vers_la_connexion(client):
    assert client.get(reverse("accounts:mfa_verifier"))["Location"].startswith(reverse("accounts:login"))


# --- écran d'activation ---


def test_la_page_d_activation_montre_le_qr_et_la_cle(client, direction):
    _connecte(client, direction)

    reponse = client.get(reverse("accounts:mfa_activer"))
    texte = reponse.content.decode()

    secret = AppareilMFA.objects.get(utilisateur=direction).secret
    assert reponse.status_code == 200
    assert reverse("accounts:mfa_qr") in texte and secret[:4] in texte


def test_le_secret_reste_le_meme_si_on_recharge_la_page(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    premier = AppareilMFA.objects.get(utilisateur=direction).secret

    client.get(reverse("accounts:mfa_activer"))

    assert AppareilMFA.objects.get(utilisateur=direction).secret == premier


def test_le_qr_est_une_image_png_jamais_mise_en_cache(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))

    reponse = client.get(reverse("accounts:mfa_qr"))

    assert reponse.status_code == 200 and reponse["Content-Type"] == "image/png"
    assert reponse["Cache-Control"] == "no-store, private"
    assert Image.open(io.BytesIO(reponse.content)).size[0] > 100


def test_le_qr_disparait_une_fois_la_mfa_activee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_qr")).status_code == 404


def test_l_activation_affiche_les_codes_de_secours_une_seule_fois(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    secret = AppareilMFA.objects.get(utilisateur=direction).secret

    reponse = client.post(reverse("accounts:mfa_activer"), {"code": pyotp.TOTP(secret).now()})
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and reponse["Cache-Control"] == "no-store, private"
    assert texte.count("<li class=\"rounded-lg bg-slate-100") == 10
    direction.refresh_from_db()
    assert direction.mfa_enabled is True
    assert client.get("/missions/").status_code == 200  # la session est vérifiée d'emblée
    assert "bg-slate-100 px-3 py-2 text-center" not in client.get(reverse("accounts:mfa_activer")).content.decode()


def test_un_mauvais_code_d_activation_n_active_rien(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))

    reponse = client.post(reverse("accounts:mfa_activer"), {"code": "111111"})

    assert reponse.status_code == 200 and "pas valable" in reponse.content.decode()
    direction.refresh_from_db()
    assert direction.mfa_enabled is False


def test_activer_une_mfa_deja_active_renvoie_vers_la_verification(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_activer"))["Location"] == reverse("accounts:mfa_verifier")
    assert client.post(reverse("accounts:mfa_activer"), {"code": "123456"})["Location"] == reverse(
        "accounts:mfa_verifier"
    )


# --- codes de secours ---


def test_la_page_des_codes_est_inaccessible_tant_que_la_mfa_n_est_pas_passee(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)

    assert client.get(reverse("accounts:mfa_codes"))["Location"].startswith(reverse("accounts:mfa_verifier"))


def test_regenerer_les_codes_depuis_l_interface(client, direction):
    _, anciens = activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    page = client.get(reverse("accounts:mfa_codes"))
    assert page.status_code == 200 and "10</strong> codes" in page.content.decode()
    refus = client.post(reverse("accounts:mfa_codes"), {"code": anciens[0]})
    assert refus.status_code == 200 and "Code incorrect" in refus.content.decode()
    reponse = client.post(reverse("accounts:mfa_codes"), {"code": code_frais(direction)})

    assert reponse.status_code == 200 and reponse.content.decode().count('<li class="rounded-lg bg-slate-100') == 10
    assert mfa.verifier_code(direction, anciens[2]) is False


def test_le_lien_codes_de_secours_apparait_pour_les_roles_soumis_a_la_mfa(client, direction):
    activer_mfa(direction)
    _connecte(client, direction)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(direction)})

    assert reverse("accounts:mfa_codes") in client.get("/").content.decode()
    client.force_login(UserFactory(role=Role.RH))
    assert reverse("accounts:mfa_codes") not in client.get("/").content.decode()


# --- réinitialisation ---


def test_l_administrateur_reinitialise_la_mfa_depuis_l_administration(client):
    perdu = UserFactory(role=Role.DIRECTION)
    activer_mfa(perdu)
    admin = UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    reponse = client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "reinitialiser_mfa", "_selected_action": [perdu.pk]},
        follow=True,
    )

    assert reponse.status_code == 200
    perdu.refresh_from_db()
    assert perdu.mfa_enabled is False and not AppareilMFA.objects.filter(utilisateur=perdu).exists()
    assert AuditLog.objects.filter(entite="MFA", entite_id=perdu.pk, nouvelle_valeur__evenement__startswith="reinitialisation_par_").exists()


def test_la_commande_reinitialise_la_mfa(direction):
    activer_mfa(direction)

    call_command("reinitialiser_mfa", direction.username)

    direction.refresh_from_db()
    assert direction.mfa_enabled is False


def test_la_commande_refuse_un_compte_inconnu():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("reinitialiser_mfa", "personne")


def test_le_champ_mfa_active_n_est_pas_modifiable_a_la_main(client):
    admin = UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})
    autre = UserFactory(role=Role.RH)

    page = client.get(reverse("admin:accounts_user_change", args=[autre.pk]))

    assert page.status_code == 200
    assert 'name="mfa_enabled"' not in page.content.decode()


# --- journal d'audit ---


def test_les_etapes_de_la_mfa_sont_inscrites_sans_secret(client, direction):
    _connecte(client, direction)
    client.get(reverse("accounts:mfa_activer"))
    secret = AppareilMFA.objects.get(utilisateur=direction).secret
    client.post(reverse("accounts:mfa_activer"), {"code": "111111"})
    client.post(reverse("accounts:mfa_activer"), {"code": pyotp.TOTP(secret).now()})

    lignes = AuditLog.objects.filter(entite="MFA", entite_id=direction.pk).order_by("pk")

    assert [(l.nouvelle_valeur["evenement"], l.statut) for l in lignes] == [
        ("activation_refusee", StatutChoices.FAILED), ("activation", StatutChoices.SUCCESS),
    ]
    assert secret not in str([l.nouvelle_valeur for l in lignes])


def test_l_admin_django_utilise_la_page_de_connexion_du_site(client):
    reponse = client.get("/admin/login/?next=/admin/accounts/user/")

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("accounts:login"))
    assert "next=/admin/accounts/user/" in reponse["Location"]
    assert User.objects.count() == 0


def test_un_compte_de_role_admin_non_superutilisateur_peut_reinitialiser_la_mfa(client):
    perdu = UserFactory(role=Role.DIRECTION)
    activer_mfa(perdu)
    admin = UserFactory(role=Role.ADMIN, is_staff=True)  # ni superutilisateur, ni permissions Django
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    liste = client.get(reverse("admin:accounts_user_changelist"))
    reponse = client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "reinitialiser_mfa", "_selected_action": [perdu.pk]},
        follow=True,
    )

    assert liste.status_code == 200
    perdu.refresh_from_db()
    assert perdu.mfa_enabled is False and reponse.status_code == 200


def test_un_compte_de_role_admin_ne_peut_pas_modifier_un_utilisateur(client):
    autre = UserFactory(role=Role.RH)
    admin = UserFactory(role=Role.ADMIN, is_staff=True)
    activer_mfa(admin)
    client.force_login(admin)
    client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(admin)})

    page = client.get(reverse("admin:accounts_user_change", args=[autre.pk]))
    envoi = client.post(reverse("admin:accounts_user_change", args=[autre.pk]), {"role": Role.ADMIN})

    assert page.status_code == 200 and "Enregistrer" not in page.content.decode()  # lecture seule
    autre.refresh_from_db()
    assert autre.role == Role.RH and envoi.status_code in (302, 403)


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES])
def test_les_autres_roles_meme_staff_ne_voient_pas_les_utilisateurs(client, role):
    membre = UserFactory(role=role, is_staff=True)
    if mfa.mfa_requise(membre):
        activer_mfa(membre)
        client.force_login(membre)
        client.post(reverse("accounts:mfa_verifier"), {"code": code_frais(membre)})
    else:
        client.force_login(membre)

    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 403


def test_le_favicon_redirige_vers_l_icone_du_site(client):
    reponse = client.get("/favicon.ico")

    assert reponse.status_code == 301 and reponse["Location"].endswith("/static/img/favicon.png")


def test_les_titres_des_pages_de_mfa_sont_ceux_attendus(client, direction):
    _connecte(client, direction)
    activation = client.get(reverse("accounts:mfa_activer")).content.decode()
    _, _codes = activer_mfa(UserFactory(role=Role.DIRECTION))
    autre = UserFactory(role=Role.DIRECTION)
    activer_mfa(autre)
    client.force_login(autre)
    verification = client.get(reverse("accounts:mfa_verifier")).content.decode()

    assert "<h1 class=\"mt-3 text-xl font-bold text-slate-900\">Activez la double authentification</h1>" in activation
    assert "Vérification en deux étapes</h1>" in verification
    assert "SOUS" not in activation + verification  # trace d'un gabarit mal généré
