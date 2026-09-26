"""Politique de sécurité du contenu (CSP), ressources locales et absence de code écrit dans les pages."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.mobile_api.tests.helpers import chauffeur_avec_compte

pytestmark = pytest.mark.django_db

RACINE = Path(settings.BASE_DIR)
GABARITS = [
    *RACINE.glob("templates/**/*.html"),
    *RACINE.glob("apps/**/templates/**/*.html"),
    *RACINE.glob("apps/**/templates/**/*.js"),
]


# --- en-têtes ---


def test_la_csp_est_posee_sur_les_pages(client):
    reponse = client.get(reverse("accounts:login"))

    csp = reponse["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "base-uri 'self'" in csp and "form-action 'self'" in csp


def test_la_csp_n_autorise_aucun_hote_externe_ni_script_en_ligne(client):
    csp = client.get(reverse("accounts:login"))["Content-Security-Policy"]

    assert "http" not in csp and "*" not in csp
    script = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script  # seul 'unsafe-eval' est toléré (Alpine.js)


def test_la_documentation_de_l_api_a_sa_propre_politique(client):
    from apps.accounts.tests.helpers_mfa import activer_mfa  # noqa: F401

    client.force_login(UserFactory(role=Role.DIRECTION))

    csp = client.get("/api/v1/docs/")["Content-Security-Policy"]

    assert "script-src 'self' 'unsafe-inline'" in csp and "http" not in csp


def test_les_pages_d_erreur_ont_aussi_la_csp(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))

    reponse = client.get("/facturation/")  # 403

    assert reponse.status_code == 403 and "Content-Security-Policy" in reponse


def test_le_mode_observation_change_le_nom_de_l_en_tete(client, settings):
    settings.CSP_REPORT_ONLY = True

    reponse = client.get(reverse("accounts:login"))

    assert "Content-Security-Policy-Report-Only" in reponse and "Content-Security-Policy" not in reponse


def test_la_camera_reste_permise_pour_le_scan_des_qr(client):
    politique = client.get(reverse("accounts:login"))["Permissions-Policy"]

    assert "camera=(self)" in politique and "microphone=()" in politique and "geolocation=()" in politique


# --- les pages ne contiennent pas de code et ne chargent rien d'externe ---

PAGES = ["/", "/missions/", "/clients/", "/flotte/", "/rh/personnel/", "/rh/conges/", "/chauffeurs/",
         "/garage/", "/garage/incidents/", "/carburant/", "/stock/", "/facturation/", "/finances/", "/notifications/"]


def _pages_rendues(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    for chemin in PAGES:
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        yield chemin, reponse.content.decode()
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)
    for chemin in ("/chauffeur/", "/chauffeur/plein/", "/chauffeur/incident/", "/chauffeur/hors-ligne/"):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        yield chemin, reponse.content.decode()
    client.logout()
    yield "/connexion/", client.get("/connexion/").content.decode()


def test_aucune_page_ne_charge_de_ressource_externe(client):
    for chemin, html in _pages_rendues(client):
        externes = re.findall(r"""(?:src|href|action)=["'](https?://[^"']+)""", html)
        assert not externes, (chemin, externes)
        assert "cdn." not in html, chemin


def test_aucune_page_rendue_ne_contient_de_script_ou_de_gestionnaire_en_ligne(client):
    for chemin, html in _pages_rendues(client):
        en_ligne = [
            m for m in re.findall(r"<script\b([^>]*)>", html) if "src=" not in m and "application/json" not in m
        ]
        assert not en_ligne, (chemin, en_ligne)
        assert not re.search(r"""\son[a-z]+\s*=\s*["']""", html), chemin
        assert "javascript:" not in html, chemin


@pytest.mark.parametrize("gabarit", GABARITS, ids=lambda p: str(p.relative_to(RACINE)))
def test_les_gabarits_n_ecrivent_ni_script_ni_gestionnaire_en_ligne(gabarit):
    texte = gabarit.read_text(encoding="utf-8")
    if gabarit.suffix == ".js":  # sw.js : servi comme fichier, pas inclus dans une page
        return
    sans_commentaires = re.sub(r"\{% comment %\}.*?\{% endcomment %\}|\{#.*?#\}", "", texte, flags=re.S)
    assert not [
        m for m in re.findall(r"<script\b([^>]*)>", sans_commentaires) if "src=" not in m and "application/json" not in m
    ], "script écrit dans la page"
    assert not re.search(r"""\son(?:click|submit|change|load|error|input|focus|blur|keyup|keydown)\s*=""", sans_commentaires), (
        "gestionnaire d'événement écrit dans la page (utiliser data-confirm / data-imprimer)"
    )
    assert "javascript:" not in sans_commentaires
    assert not re.search(r"(?:cdn\.|cdnjs\.|jsdelivr|googleapis|unpkg)", sans_commentaires, re.I), "ressource externe"


# --- ressources locales ---


@pytest.mark.parametrize("chemin", [
    "css/tailwind.css", "js/app.js", "js/sw-register.js", "js/scanner.js", "vendor/alpine/alpine.min.js",
    "vendor/fontawesome/css/all.min.css", "vendor/fontawesome/webfonts/fa-solid-900.woff2",
    "vendor/fontawesome/webfonts/fa-regular-400.woff2", "img/logo-emblem.jpg", "img/favicon.png",
])
def test_les_ressources_locales_existent(chemin):
    assert finders.find(chemin), chemin


def test_le_css_compile_contient_les_couleurs_de_la_marque():
    css = Path(finders.find("css/tailwind.css")).read_text(encoding="utf-8")

    assert "#8b0319" in css.lower() and "#f28a14" in css.lower()  # marque-700 et accent-500
    assert ".bg-marque-600" in css and ".bg-accent-500" in css


def test_les_classes_tailwind_des_gabarits_sont_dans_le_css_compile():
    """Filet contre un css compilé périmé : chaque classe simple écrite dans un gabarit doit exister."""
    css = Path(finders.find("css/tailwind.css")).read_text(encoding="utf-8")
    manquantes = set()
    motif_classe = re.compile(r'class="([^"{}%]*)"')
    for gabarit in GABARITS:
        if gabarit.suffix != ".html":
            continue
        for attribut in motif_classe.findall(gabarit.read_text(encoding="utf-8")):
            for classe in attribut.split():
                if re.fullmatch(r"(?:hover:|focus:|sm:|lg:|md:)*(?:bg|text|border|ring)-(?:marque|accent)-\d{2,3}", classe):
                    base = classe.replace(":", r"\:")
                    if f".{base}" not in css and base.split("\\:")[-1] not in css:
                        manquantes.add(classe)
    assert not manquantes, sorted(manquantes)[:10]


def test_app_js_gere_la_confirmation_et_l_impression():
    js = Path(finders.find("js/app.js")).read_text(encoding="utf-8")

    assert "dataset.confirm" in js and "data-imprimer" in js and "window.print" in js


def test_le_service_worker_est_enregistre_sans_code_en_ligne(client):
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)

    html = client.get("/chauffeur/").content.decode()

    assert 'src="/static/js/sw-register.js"' in html and 'data-sw="/chauffeur/sw.js"' in html


def test_la_page_hors_connexion_reste_autonome_sans_script(client):
    html = client.get(reverse("chauffeur:hors_ligne")).content.decode()

    assert "<script" not in html and 'href="/chauffeur/"' in html


def test_les_formulaires_a_confirmation_utilisent_data_confirm(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    from apps.missions.tests.factories import MissionFactory
    from apps.missions.models import StatutMission
    from apps.fleet.tests.factories import VehiculeFactory

    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    html = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    assert 'data-confirm="Démarrer la mission ?' in html and "onsubmit" not in html
