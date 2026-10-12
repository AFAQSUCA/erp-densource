"""Suivi des sauvegardes par l'ADMIN (audit M1-14) : journal, demande immédiate, alerte, écran."""

import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.dashboard import services as dashboard_services
from apps.sauvegardes import services

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 10, 12, 9, 0, tzinfo=dt_timezone.utc)


@pytest.fixture(autouse=True)
def dossier(settings, tmp_path):
    settings.SAUVEGARDES_DIR = tmp_path
    settings.SAUVEGARDES_SURVEILLEES = True
    return tmp_path


def _essai(dossier, fin, statut="OK", declencheur="planifiee", **autres):
    ligne = {
        "debut": (fin - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fin": fin.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "statut": statut,
        "declencheur": declencheur,
        "message": "Sauvegarde réussie." if statut != "ECHEC" else "La sauvegarde a échoué (code 1).",
        "base": {"nom": "erp_densource_x.dump.gpg", "taille": 2048, "sha256": "a" * 64} if statut != "ECHEC" else None,
        "medias": {"nom": "erp_densource_medias_x.tar.gz.gpg", "taille": 4096, "sha256": "b" * 64}
        if statut != "ECHEC" else None,
    }
    ligne.update(autres)
    with open(dossier / "journal.jsonl", "a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")


# --- journal ---


def test_sans_journal_rien_n_est_affiche():
    assert services.journal() == [] and services.derniere_reussie() is None


def test_le_journal_se_lit_du_plus_recent_au_plus_ancien(dossier):
    _essai(dossier, MAINTENANT - timedelta(days=1))
    _essai(dossier, MAINTENANT, declencheur="demande:admin")

    essais = services.journal()

    assert [e["fin"] for e in essais] == [MAINTENANT, MAINTENANT - timedelta(days=1)]
    assert essais[0]["declencheur"] == "Demandée par admin"
    assert essais[1]["declencheur"] == "Planifiée (nuit)"
    assert essais[0]["base"] == {"nom": "erp_densource_x.dump.gpg", "taille": 2048, "sha256": "a" * 64}


def test_une_ligne_illisible_ou_un_statut_inconnu_ne_masque_pas_les_autres(dossier):
    _essai(dossier, MAINTENANT - timedelta(hours=2))
    with open(dossier / "journal.jsonl", "a", encoding="utf-8") as fichier:
        fichier.write('{"debut": "2026-10-12T08:\n')  # ligne tronquée (arrêt brutal)
        fichier.write("[1, 2]\n")
    _essai(dossier, MAINTENANT, statut="BIZARRE", base="pas un objet")

    essais = services.journal()

    assert len(essais) == 2
    assert essais[0]["statut"] == services.STATUT_ECHEC and essais[0]["base"] is None
    assert services.derniere_reussie()["fin"] == MAINTENANT - timedelta(hours=2)


def test_le_journal_est_borne(dossier):
    for heures in range(5):
        _essai(dossier, MAINTENANT - timedelta(hours=heures))

    assert len(services.journal(limite=3)) == 3


def test_une_sauvegarde_dont_la_copie_hors_serveur_a_echoue_compte_comme_faite(dossier):
    _essai(dossier, MAINTENANT, statut="ALERTE")

    assert services.derniere_reussie()["statut"] == services.STATUT_ALERTE


# --- en cours, demandes ---


def test_une_sauvegarde_en_cours_est_signalee(dossier):
    (dossier / "en_cours.json").write_text('{"debut": "2026-10-12T09:00:00Z", "declencheur": "planifiee"}')

    assert services.en_cours() == {"debut": MAINTENANT, "declencheur": "Planifiée (nuit)"}


def test_un_fichier_en_cours_illisible_est_ignore(dossier):
    (dossier / "en_cours.json").write_text("{pas du json")

    assert services.en_cours() is None


def test_l_admin_demande_une_sauvegarde(dossier):
    admin = UserFactory(role=Role.ADMIN, username="kone")

    services.demander_sauvegarde(admin)

    (demande,) = (dossier / "demandes").glob("*.demande")
    assert demande.read_text(encoding="utf-8") == "kone"
    assert not list((dossier / "demandes").glob("*.tmp"))  # écriture atomique
    assert services.demande_en_attente()["par"] == "kone"
    entree = AuditLog.objects.get(module="SAUVEGARDES")
    assert entree.utilisateur == admin and entree.entite == "DemandeSauvegarde"


def test_un_superutilisateur_agit_en_admin(dossier):
    services.demander_sauvegarde(UserFactory(role=Role.CHAUFFEUR, is_superuser=True))

    assert services.demande_en_attente() is not None


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHAUFFEUR])
def test_les_autres_roles_ne_demandent_pas_de_sauvegarde(dossier, role):
    with pytest.raises(services.ActionNonAutorisee):
        services.demander_sauvegarde(UserFactory(role=role))
    assert services.demande_en_attente() is None


def test_une_seconde_demande_est_refusee_tant_que_la_premiere_attend(dossier):
    admin = UserFactory(role=Role.ADMIN)
    services.demander_sauvegarde(admin)

    with pytest.raises(services.SauvegardeError, match="déjà demandée"):
        services.demander_sauvegarde(admin)
    assert len(list((dossier / "demandes").glob("*.demande"))) == 1


def test_une_demande_est_refusee_pendant_une_sauvegarde(dossier):
    (dossier / "en_cours.json").write_text('{"debut": "2026-10-12T09:00:00Z", "declencheur": "planifiee"}')

    with pytest.raises(services.SauvegardeError, match="déjà en cours"):
        services.demander_sauvegarde(UserFactory(role=Role.ADMIN))


# --- alerte ---


def test_pas_d_alerte_quand_la_surveillance_est_inactive(settings):
    settings.SAUVEGARDES_SURVEILLEES = False

    assert services.alerte(maintenant=MAINTENANT) is None


def test_alerte_urgente_sans_aucune_sauvegarde_reussie(dossier):
    _essai(dossier, MAINTENANT, statut="ECHEC")

    assert services.alerte(maintenant=MAINTENANT) == {
        "niveau": "URGENT", "detail": "aucune sauvegarde réussie enregistrée"
    }


def test_alerte_urgente_si_la_derniere_reussie_a_plus_de_26_heures(dossier):
    _essai(dossier, MAINTENANT - timedelta(hours=27))

    assert services.alerte(maintenant=MAINTENANT) == {
        "niveau": "URGENT", "detail": "dernière sauvegarde réussie il y a 27 h"
    }


def test_pas_d_alerte_apres_une_sauvegarde_de_la_nuit(dossier):
    _essai(dossier, MAINTENANT - timedelta(hours=7))

    assert services.alerte(maintenant=MAINTENANT) is None


def test_alerte_si_le_dernier_essai_a_echoue_malgre_une_sauvegarde_recente(dossier):
    _essai(dossier, MAINTENANT - timedelta(hours=7))
    _essai(dossier, MAINTENANT - timedelta(hours=1), statut="ECHEC", declencheur="demande:kone")

    assert services.alerte(maintenant=MAINTENANT)["niveau"] == "ATTENTION"


def test_alerte_si_la_copie_hors_serveur_a_echoue(dossier):
    _essai(dossier, MAINTENANT - timedelta(hours=7), statut="ALERTE")

    assert services.alerte(maintenant=MAINTENANT) == {"niveau": "ATTENTION", "detail": "la copie hors serveur a échoué"}


def test_le_centre_d_alertes_de_l_admin_signale_les_sauvegardes(dossier):
    groupes = {g["code"]: g for g in dashboard_services.centre_alertes(Role.ADMIN)}

    assert groupes["sauvegardes"]["niveau"] == "URGENT"
    assert groupes["sauvegardes"]["lignes"][0]["url"] == reverse("sauvegardes:liste")
    direction = dashboard_services.centre_alertes(Role.DIRECTION) or []
    assert "sauvegardes" not in {g["code"] for g in direction}


# --- écran ---


def test_l_ecran_montre_le_journal_a_l_admin(client, dossier):
    _essai(dossier, MAINTENANT, declencheur="demande:kone")
    client.force_login(UserFactory(role=Role.ADMIN))

    page = client.get(reverse("sauvegardes:liste")).content.decode()

    assert "Dernière sauvegarde réussie" in page and "Demandée par kone" in page
    assert "2,0 Kio" in page and "4,0 Kio" in page  # espace insécable
    assert "Sauvegarder maintenant" in page
    assert 'http-equiv="refresh"' not in page


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHAUFFEUR])
def test_l_ecran_est_refuse_aux_autres_roles(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("sauvegardes:liste")).status_code == 403
    assert client.post(reverse("sauvegardes:liste")).status_code == 403


def test_le_bouton_depose_une_demande_et_la_page_se_rafraichit(client, dossier):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.post(reverse("sauvegardes:liste"), follow=True)

    page = reponse.content.decode()
    assert "Sauvegarde demandée : elle démarre dans la minute." in page
    assert 'http-equiv="refresh"' in page and "disabled" in page
    assert services.demande_en_attente() is not None


def test_un_double_clic_n_empile_pas_les_demandes(client, dossier):
    client.force_login(UserFactory(role=Role.ADMIN))
    client.post(reverse("sauvegardes:liste"))

    reponse = client.post(reverse("sauvegardes:liste"), follow=True)

    assert "déjà demandée" in reponse.content.decode()
    assert len(list((dossier / "demandes").glob("*.demande"))) == 1


def test_le_menu_propose_les_sauvegardes_a_l_admin_seulement(client):
    for role, visible in ((Role.ADMIN, True), (Role.DIRECTION, False), (Role.RH, False)):
        client.force_login(UserFactory(role=role))
        assert (reverse("sauvegardes:liste") in client.get(reverse("home")).content.decode()) is visible


# --- lecture tolérante ---


@pytest.mark.parametrize(
    ("code", "libelle"),
    [("planifiee", "Planifiée (nuit)"), ("manuelle", "Lancée sur le serveur"), ("demande:kone", "Demandée par kone"),
     ("autre", "autre"), ("", "—")],
)
def test_libelle_de_l_origine(code, libelle):
    assert services.libelle_declencheur(code) == libelle


def test_une_date_ou_une_taille_invalide_ne_fait_pas_planter_la_lecture(dossier):
    _essai(dossier, MAINTENANT, debut="2026-13-45T00:00:00Z", base={"nom": "x", "taille": "beaucoup", "sha256": "c"})

    (essai,) = services.journal()

    assert essai["debut"] is None and essai["base"]["taille"] is None


def test_un_fichier_en_cours_qui_n_est_pas_un_objet_est_ignore(dossier):
    (dossier / "en_cours.json").write_text("[1]")

    assert services.en_cours() is None


def test_une_demande_prise_en_charge_pendant_la_lecture_est_ignoree(dossier, monkeypatch):
    services.demander_sauvegarde(UserFactory(role=Role.ADMIN))
    lire = type(dossier).read_text

    def disparue(chemin, *args, **kwargs):
        if chemin.suffix == ".demande":
            raise FileNotFoundError(chemin)
        return lire(chemin, *args, **kwargs)

    monkeypatch.setattr(type(dossier), "read_text", disparue)

    assert services.demande_en_attente() is None
