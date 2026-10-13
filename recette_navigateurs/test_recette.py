"""Scénarios de la fiche RECETTE-NAVIGATEURS.md, joués dans Chrome, Edge, Firefox et WebKit (audit TECH-74 à 77).

Chaque test porte le numéro de la fiche (A1, B2...) dans la première ligne de sa documentation, reprise par
``RESULTATS.md``.
"""

from __future__ import annotations

import re
import time
from decimal import Decimal
from pathlib import Path

import pyotp
import pytest
from django.core import mail
from playwright.sync_api import expect

from apps.accounts.models import AppareilMFA, Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import emise
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.fuel.models import Plein
from apps.hr.tests.factories import PersonnelFactory
from apps.missions.models import FraisMission, StatutMission
from apps.mobile_api.tests.helpers import CODE_EXPEDITEUR, chauffeur_avec_compte, mission_de
from apps.notifications.models import CategorieNotification
from apps.notifications.services import notifier

from .conftest import verifier_console

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

MOT_DE_PASSE = "Test-Passw0rd!"  # celui de UserFactory
MILLIERS = r"[\s  ]"


def _image_chargee(page, image):
    """Attend qu'une image soit chargée et non vide (une image cassée ferait échouer le scénario)."""
    expect(image).to_be_visible()
    page.wait_for_function("(img) => img.complete && img.naturalWidth > 0", arg=image.element_handle(), timeout=10000)


def _admin():
    return UserFactory(is_superuser=True, is_staff=True, first_name="Awa", last_name="Diallo")


# --- A. Connexion et sécurité ---


def test_a1_connexion(ouvrir):
    """A1 — Connexion, puis refus d'un mauvais mot de passe"""
    UserFactory(username="awa", role=Role.RH)
    page = ouvrir()
    page.goto("/")
    expect(page).to_have_url(re.compile(r"/connexion/"))
    page.fill("#id_username", "awa")
    page.fill("#id_password", "mauvais-mot-de-passe")
    page.click("button[type=submit]")
    expect(page.get_by_role("alert").first).to_be_visible()

    page.fill("#id_username", "awa")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")
    expect(page.get_by_role("button", name="Déconnexion")).to_be_visible()
    verifier_console(page)


def test_a2_double_authentification(ouvrir, settings):
    """A2 — Double authentification : QR affiché, code à 6 chiffres accepté"""
    settings.MFA_ENFORCED = True
    UserFactory(username="direction", role=Role.DIRECTION)
    page = ouvrir()
    page.goto("/connexion/")
    page.fill("#id_username", "direction")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")

    qr = page.get_by_role("img", name=re.compile("Code QR d'activation"))
    _image_chargee(page, qr)
    secret = AppareilMFA.objects.get(utilisateur__username="direction").secret
    page.fill("#id_code", pyotp.TOTP(secret).now())
    page.get_by_role("button", name="Activer").click()
    expect(page.get_by_text(re.compile("codes de secours", re.I)).first).to_be_visible()
    verifier_console(page)


def test_a3_mot_de_passe_oublie(ouvrir):
    """A3 — « Mot de passe oublié » : envoi et confirmation"""
    UserFactory(username="rh", email="rh@densourcegroup.ci", role=Role.RH)
    page = ouvrir()
    page.goto("/mot-de-passe/")
    page.fill("#id_email", "rh@densourcegroup.ci")
    page.click("button[type=submit]")
    expect(page.get_by_role("heading", name="E-mail envoyé")).to_be_visible()
    assert len(mail.outbox) == 1
    verifier_console(page)


def test_a4_expiration_de_session(ouvrir, settings):
    """A4 — La session expire après l'inactivité et ramène à la connexion"""
    settings.SESSION_COOKIE_AGE = 3
    UserFactory(username="rh", role=Role.RH)
    page = ouvrir()
    page.goto("/connexion/")
    page.fill("#id_username", "rh")
    page.fill("#id_password", MOT_DE_PASSE)
    page.click("button[type=submit]")
    expect(page.get_by_role("button", name="Déconnexion")).to_be_visible()

    time.sleep(4)
    page.reload()
    expect(page).to_have_url(re.compile(r"/connexion/"))


def test_a5_deconnexion(ouvrir):
    """A5 — Déconnexion : « Précédent » ne réaffiche pas une page protégée"""
    PersonnelFactory(nom="Secretnom")
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    expect(page.get_by_text("Secretnom").first).to_be_visible()
    page.get_by_role("button", name="Déconnexion").click()
    expect(page).to_have_url(re.compile(r"/connexion/"))

    page.go_back()
    page.wait_for_load_state()
    expect(page.get_by_text("Secretnom")).to_have_count(0)
    verifier_console(page)


# --- B. Mise en page et navigation ---


def test_b1_menu_logo_et_icones(ouvrir):
    """B1 — Menu latéral, logo et icônes affichés"""
    page = ouvrir(_admin())
    page.goto("/")
    liens = page.locator("#navigation nav a")
    assert liens.count() >= 8
    for i in range(liens.count()):
        expect(liens.nth(i)).to_be_visible()
    _image_chargee(page, page.locator("#navigation img").first)
    page.evaluate("document.fonts.ready")
    assert page.evaluate(
        "[...document.fonts].some(f => /Font Awesome/i.test(f.family) && f.status === 'loaded')"
    ), "police d'icônes non chargée"
    largeur_icone = page.evaluate("document.querySelector('#navigation nav i').getBoundingClientRect().width")
    assert largeur_icone > 0
    with page.expect_navigation():
        liens.nth(1).click()
    assert page.locator("#navigation [aria-current=page]").count() == 1
    verifier_console(page)


def test_b2_menu_sur_petit_ecran(ouvrir):
    """B2 — Petit écran : le menu s'ouvre par « ☰ » et se ferme par Échap"""
    page = ouvrir(_admin())
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    navigation = page.locator("#navigation")
    expect(navigation).not_to_be_in_viewport()
    page.get_by_role("button", name="Ouvrir le menu").click()
    expect(navigation).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(navigation).not_to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    verifier_console(page)


def test_b3_pagination_et_recherche_sans_accents(ouvrir):
    """B3 — Pagination et recherche sans accents (« kone » trouve « Koné »)"""
    for i in range(24):
        PersonnelFactory(nom=f"Agent{i:02d}")
    PersonnelFactory(nom="Koné", prenom="Mariam")
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    page.locator("a[href*='page=2']").first.click()
    expect(page).to_have_url(re.compile(r"page=2"))
    page.goto("/rh/personnel/?q=kone")
    expect(page.get_by_text("Koné").first).to_be_visible()
    expect(page.get_by_text("Agent00")).to_have_count(0)
    verifier_console(page)


def test_b4_notifications(ouvrir):
    """B4 — Cloche des notifications et « Tout marquer comme lu »"""
    utilisateur = _admin()
    notifier([utilisateur], categorie=CategorieNotification.MISSION, titre="Mission livrée")
    page = ouvrir(utilisateur)
    page.goto("/")
    cloche = page.locator("a[href='/notifications/']")
    expect(cloche).to_contain_text("1")
    cloche.click()
    expect(page.get_by_text("Mission livrée").first).to_be_visible()
    with page.expect_navigation():
        page.get_by_role("button", name="Tout marquer comme lu").click()
    expect(page.locator("a[href='/notifications/']")).not_to_contain_text("1")
    verifier_console(page)


def test_b5_tableau_de_bord(ouvrir):
    """B5 — Tableau de bord : indicateurs et graphiques sans débordement"""
    fiche, _ = chauffeur_avec_compte()
    mission_de(fiche)  # des données pour que les graphiques aient quelque chose à montrer
    emise()
    page = ouvrir(_admin())
    page.goto("/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert page.locator("main [class*='viz-']").count() >= 1  # graphiques en HTML/CSS (apps/core/graphiques.py)
    verifier_console(page)


# --- C. Formulaires ---


def _formulaire_plein(page, vehicule, chauffeur, *, date_plein):
    page.goto("/carburant/nouveau/")
    page.select_option("#id_vehicule", str(vehicule.pk))
    page.select_option("#id_chauffeur", str(chauffeur.pk))
    page.fill("#id_date_plein", date_plein)
    page.fill("#id_station", "Total Plateau")
    page.fill("#id_quantite_litres", "100")
    page.fill("#id_prix_unitaire", "700")
    page.fill("#id_km_compteur", "1500")
    page.fill("#id_numero_ticket", "T-001")


def test_c1_c2_c3_formulaire_dates_montants_erreurs(ouvrir):
    """C1-C3 — Calendrier de date, montant en FCFA, erreurs affichées sans perdre la saisie"""
    vehicule, chauffeur = VehiculeEnRegleFactory(), ChauffeurFactory()
    page = ouvrir(UserFactory(role=Role.PARCAUTO))

    _formulaire_plein(page, vehicule, chauffeur, date_plein="2099-01-01")  # date future : refusée par le serveur
    page.get_by_role("button", name=re.compile("Enregistrer")).click()
    expect(page.get_by_text("ne peut pas être dans le futur")).to_be_visible()
    expect(page.locator("#id_station")).to_have_value("Total Plateau")

    page.fill("#id_date_plein", "2026-10-10")
    with page.expect_navigation():
        page.get_by_role("button", name=re.compile("Enregistrer")).click()
    plein = Plein.objects.get()
    assert plein.date_plein.isoformat() == "2026-10-10"
    page.goto("/carburant/")
    expect(page.locator("main")).to_contain_text(re.compile(f"70{MILLIERS}000"))
    verifier_console(page)


def test_c5_confirmation_avant_une_action(ouvrir):
    """C5 — Confirmation avant une action : « Annuler » n'enregistre rien"""
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    page = ouvrir(UserFactory(role=Role.CHARGE_CLIENTELE))
    page.goto(f"/missions/{mission.pk}/")
    page.get_by_role("button", name="Annuler la mission").click()
    page.fill("#motif-annulation", "Le client a retiré sa commande")

    page.once("dialog", lambda dialogue: dialogue.dismiss())
    page.get_by_role("button", name="Confirmer l'annulation").click()
    page.wait_for_timeout(500)
    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE

    page.once("dialog", lambda dialogue: dialogue.accept())
    page.get_by_role("button", name="Confirmer l'annulation").click()
    expect(page.get_by_text(re.compile("annulée")).first).to_be_visible()
    mission.refresh_from_db()
    assert mission.statut == StatutMission.ANNULEE
    verifier_console(page)


# --- D. Documents et exports ---


def test_d1_impression_d_une_facture(ouvrir):
    """D1 — Impression d'une facture : la page imprimée ne montre que la facture"""
    facture = emise()
    page = ouvrir(_admin())
    page.goto(f"/facturation/{facture.pk}/imprimer/")
    expect(page.get_by_text(facture.numero).first).to_be_visible()
    assert page.locator("#navigation").count() == 0
    bouton = page.locator("[data-imprimer]").first
    expect(bouton).to_be_visible()
    page.emulate_media(media="print")
    expect(bouton).to_be_hidden()
    verifier_console(page)


def test_d2_pdf_prepare_en_tache_de_fond(ouvrir, settings):
    """D2 — « Télécharger en PDF » : page d'attente puis téléchargement automatique"""
    settings.PDF_EN_TACHE_DE_FOND = True
    PersonnelFactory()
    page = ouvrir(_admin())
    page.goto("/rh/personnel/imprimer/")
    with page.expect_download(timeout=20000) as attente:
        page.get_by_role("link", name="Télécharger en PDF").click()
    fichier = attente.value
    assert fichier.suggested_filename.startswith("personnel-") and fichier.suggested_filename.endswith(".pdf")
    assert Path(fichier.path()).read_bytes().startswith(b"%PDF")


def test_d3_export_excel(ouvrir):
    """D3 — Export Excel : le fichier .xlsx se télécharge"""
    PersonnelFactory()
    page = ouvrir(_admin())
    page.goto("/rh/personnel/")
    with page.expect_download() as attente:
        page.locator("a[href*='/rh/personnel/excel/']").first.click()
    fichier = attente.value
    assert fichier.suggested_filename.endswith(".xlsx")
    assert Path(fichier.path()).read_bytes().startswith(b"PK")  # classeur = archive zip
    verifier_console(page)


def test_d4_pdf_des_codes_d_une_mission(ouvrir):
    """D4 — PDF des codes d'une mission et QR affichés"""
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    page = ouvrir(UserFactory(role=Role.CHARGE_CLIENTELE))
    page.goto(f"/missions/{mission.pk}/")
    _image_chargee(page, page.get_by_role("img", name=re.compile("Code QR de l'expéditeur")))
    with page.expect_download() as attente:
        page.get_by_role("link", name="Télécharger le PDF des codes").click()
    assert Path(attente.value.path()).read_bytes().startswith(b"%PDF")
    verifier_console(page)


# --- F. Espace chauffeur (téléphone) ---


def test_f1_espace_chauffeur_a_la_taille_du_telephone(ouvrir):
    """F1 — Espace chauffeur à la taille de l'écran, barre du bas sur une ligne"""
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)
    page = ouvrir(compte, mobile=True)
    page.goto("/chauffeur/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    barre = page.locator("nav").last
    expect(barre).to_be_visible()
    assert barre.bounding_box()["height"] < 100
    verifier_console(page)


def test_f2_installable_sur_l_ecran_d_accueil(ouvrir):
    """F2 — Installable : manifeste valide et service worker enregistré"""
    _, compte = chauffeur_avec_compte()
    page = ouvrir(compte, mobile=True)
    page.goto("/chauffeur/")
    adresse = page.evaluate("document.querySelector('link[rel=manifest]').href")
    manifeste = page.context.request.get(adresse).json()  # lu directement, sans passer par le service worker
    assert manifeste["name"] and manifeste["icons"] and manifeste["start_url"].startswith("/chauffeur/")
    enregistre = page.evaluate(
        "navigator.serviceWorker ? navigator.serviceWorker.ready.then(r => !!r.active) : false"
    )
    assert enregistre, "service worker non enregistré"
    verifier_console(page)


def test_f4_code_saisi_a_la_main(ouvrir):
    """F4 — Code de récupération saisi à la main (en minuscules) et accepté"""
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/missions/{mission.pk}/")
    page.fill("#id_code", CODE_EXPEDITEUR.lower())
    with page.expect_navigation():
        page.get_by_role("button", name="Confirmer la récupération").click()
    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    verifier_console(page)


def test_f3_qr_scanne_par_la_camera(ouvrir, navigateur):
    """F3 — Caméra ouverte depuis l'espace chauffeur ; QR lu (Chrome, Edge : caméra simulée filmant un QR)"""
    if navigateur.nom == "webkit":
        pytest.skip("Pas de caméra simulée dans WebKit sous Windows : à vérifier sur un iPhone (fiche, F3)")
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/missions/{mission.pk}/")
    page.get_by_role("button", name="Scanner le QR").click()
    if navigateur.nom == "firefox":
        expect(page.locator("video")).to_be_visible()
        page.wait_for_function("document.querySelector('video').readyState >= 2", timeout=10000)
        page.get_by_role("button", name="Fermer la caméra").click()
    else:
        expect(page.locator("#id_code")).to_have_value(CODE_EXPEDITEUR, timeout=15000)
    expect(page.get_by_role("alert")).to_have_count(0)
    verifier_console(page)


def test_f5_imprevu_avec_photo(ouvrir, tmp_path):
    """F5 — Imprévu déclaré avec une photo"""
    from PIL import Image

    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 64), "orange").save(photo)
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche, statut=StatutMission.EN_COURS_DEPART)
    page = ouvrir(compte, mobile=True)
    page.goto(f"/chauffeur/imprevu/?mission={mission.pk}")
    page.fill("#id_montant", "15000")
    page.fill("#id_description", "Crevaison, pneu remplacé")
    page.set_input_files("#id_justificatif", str(photo))
    with page.expect_navigation():
        page.locator("form button[type=submit]").last.click()
    frais = FraisMission.objects.get(mission=mission)
    assert frais.montant == Decimal("15000") and frais.justificatif
    verifier_console(page)

