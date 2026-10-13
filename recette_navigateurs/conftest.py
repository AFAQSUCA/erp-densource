"""Recette automatisée dans de vrais navigateurs (cahier-des-charges.md:300 ; audit TECH-74 à TECH-77).

Lancement (hors de la suite habituelle, qui ne lit que ``apps/``) :

    python -m pytest recette_navigateurs -p no:cacheprovider

Prérequis : ``pip install playwright`` puis ``python -m playwright install firefox webkit`` ; Chrome et Edge sont
ceux installés sur le poste (canaux ``chrome`` et ``msedge`` de Playwright). Les scénarios suivent la fiche
``RECETTE-NAVIGATEURS.md`` (sections A à F) ; chacun tourne dans chaque navigateur, sur un serveur de test et une
base de test (jamais les données de démonstration). En fin de passage, ``recette_navigateurs/RESULTATS.md`` donne les
versions testées et le résultat de chaque scénario par navigateur.

Safari : Playwright fournit le moteur de Safari (WebKit) sur Windows, pas Safari lui-même ; la ligne Safari de la
matrice demande en plus la vérification sur un iPhone ou un Mac (section F de la fiche).
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

import pytest
from django.test import Client
from playwright.sync_api import sync_playwright

# L'API synchrone de Playwright fait tourner une boucle d'événements dans le fil principal : Django y voit un contexte
# asynchrone et refuserait les requêtes en base des scénarios (créations de données, vérifications). Réglage prévu
# par Django pour ce cas (tests seulement).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

ICI = Path(__file__).resolve().parent
CODE_QR = "ABCD2345"  # code expéditeur des missions de test (apps/mobile_api/tests/helpers.py)

NAVIGATEURS = {
    "chrome": ("chromium", {"channel": "chrome"}),
    "edge": ("chromium", {"channel": "msedge"}),
    "firefox": ("firefox", {}),
    "webkit": ("webkit", {}),
}
LIBELLES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "webkit": "WebKit (moteur de Safari)"}

VERSIONS: dict[str, str] = {}
RESULTATS: dict[tuple[str, str], str] = {}  # (scénario, navigateur) -> réussi / échoué / ignoré


def pytest_collection_modifyitems(items):
    """Un navigateur après l'autre (un seul lancement de chacun), dans l'ordre de la fiche."""
    ordre = list(NAVIGATEURS)
    items.sort(key=lambda item: ordre.index(item.callspec.params["navigateur"]) if hasattr(item, "callspec") else -1)


def _video_qr(dossier: Path) -> Path:
    """Vidéo Y4M d'un QR du code expéditeur : la « caméra » simulée de Chrome et Edge (section F3)."""
    import qrcode
    from PIL import Image

    largeur, hauteur = 640, 480
    fond = Image.new("RGB", (largeur, hauteur), "white")
    qr = qrcode.make(CODE_QR, box_size=10, border=4).convert("RGB")
    fond.paste(qr, ((largeur - qr.width) // 2, (hauteur - qr.height) // 2))
    y, cb, cr = fond.convert("YCbCr").split()
    demi = (largeur // 2, hauteur // 2)
    trame = y.tobytes() + cb.resize(demi).tobytes() + cr.resize(demi).tobytes()
    chemin = dossier / "qr.y4m"
    with chemin.open("wb") as video:
        video.write(f"YUV4MPEG2 W{largeur} H{hauteur} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(10):
            video.write(b"FRAME\n" + trame)
    return chemin


def _lancer(type_navigateur, options):
    """Lance le navigateur. Sur certains postes Windows, le Firefox de Playwright refuse de démarrer depuis son
    dossier d'installation (« configuration côte-à-côte incorrecte », composant mozglue) mais démarre depuis une
    copie dans le dossier temporaire : on s'y replie."""
    try:
        return type_navigateur.launch(**options)
    except Exception:
        if type_navigateur.name != "firefox" or sys.platform != "win32" or "executable_path" in options:
            raise
        copie = Path(tempfile.gettempdir()) / "erp-recette-firefox"
        if not (copie / "firefox.exe").exists():
            shutil.copytree(Path(type_navigateur.executable_path).parent, copie, dirs_exist_ok=True)
        return type_navigateur.launch(executable_path=str(copie / "firefox.exe"), **options)


@pytest.fixture(scope="session")
def playwright_session():
    if sys.platform == "win32":
        # Daphne (WebSocket) impose à l'import une boucle d'événements « Selector », incapable de lancer le processus
        # de Playwright sous Windows : on rétablit la boucle « Proactor », celle par défaut de Windows.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session", params=list(NAVIGATEURS))
def navigateur(request, playwright_session, tmp_path_factory):
    nom = request.param
    moteur, options = NAVIGATEURS[nom]
    if moteur == "chromium":
        video = _video_qr(tmp_path_factory.mktemp("camera"))
        options = {**options, "args": [
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={video}",
        ]}
    elif moteur == "firefox":
        options = {**options, "firefox_user_prefs": {
            "media.navigator.streams.fake": True, "media.navigator.permission.disabled": True,
        }}
    try:
        navigateur = _lancer(getattr(playwright_session, moteur), options)
    except Exception as erreur:  # navigateur absent du poste
        pytest.skip(f"{LIBELLES[nom]} indisponible : {erreur}")
    VERSIONS[nom] = navigateur.version
    navigateur.nom = nom
    yield navigateur
    navigateur.close()


@pytest.fixture
def serveur(live_server, settings, tmp_path):
    from django.core.cache import cache

    settings.MEDIA_ROOT = tmp_path / "media"
    cache.clear()  # compteurs anti-abus (connexion, mot de passe oublié) : chaque scénario repart de zéro
    return live_server.url


@pytest.fixture
def ouvrir(navigateur, serveur, playwright_session):
    """``ouvrir(utilisateur=None, mobile=False)`` : une page neuve, connectée si un utilisateur est donné.

    Les erreurs JavaScript et les refus de la politique de sécurité (CSP) de la page sont relevés ; un scénario
    échoue s'il y en a (``verifier_console``).
    """
    contextes = []

    def _ouvrir(utilisateur=None, *, mobile=False):
        options = {"base_url": serveur, "accept_downloads": True, "locale": "fr-FR", "timezone_id": "Africa/Abidjan"}
        if mobile:
            # Téléphone : iPhone pour le moteur de Safari, Android pour Chrome et Edge ; Firefox n'émule pas de
            # téléphone (option « is_mobile » non prise en charge), seulement sa taille d'écran.
            appareil = {"webkit": "iPhone 14", "chrome": "Pixel 7", "edge": "Pixel 7"}.get(navigateur.nom)
            if appareil:
                description = dict(playwright_session.devices[appareil])
                description.pop("default_browser_type", None)
                options.update(description)
            else:
                options.update({"viewport": {"width": 412, "height": 915}, "has_touch": True})
        else:
            options["viewport"] = {"width": 1366, "height": 850}
        if navigateur.nom in ("chrome", "edge"):
            options["permissions"] = ["camera"]
        contexte = navigateur.new_context(**options)
        contextes.append(contexte)
        if utilisateur is not None:
            client = Client()
            client.force_login(utilisateur)
            contexte.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": serveur}])
        page = contexte.new_page()
        suivre_erreurs(page)
        return page

    yield _ouvrir
    for contexte in contextes:
        contexte.close()


def suivre_erreurs(page):
    """Relève les erreurs JavaScript, les messages d'erreur de la console et les réponses en erreur (avec leur
    adresse : la console de Chrome ne la donne pas toujours)."""
    page.erreurs = []
    page.on("pageerror", lambda e: page.erreurs.append(f"JavaScript : {e}"))
    page.on("console", lambda m: page.erreurs.append(f"Console : {m.text}")
            if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    page.on("response", lambda r: page.erreurs.append(f"HTTP {r.status} : {r.url}") if r.status >= 400 else None)


def verifier_console(page, *, sauf=()):
    """Aucune erreur JavaScript ni refus de la CSP. ``sauf`` : morceaux de messages attendus (ex. WebSocket, que le
    serveur de test ne sert pas)."""
    ignorees = ("WebSocket", "ws/missions", "favicon") + tuple(sauf)
    restantes = [e for e in page.erreurs if not any(morceau in e for morceau in ignorees)]
    assert not restantes, restantes


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultat = yield
    rapport = resultat.get_result()
    if not hasattr(item, "callspec") or "navigateur" not in item.callspec.params:
        return
    cle = (item.originalname, item.callspec.params["navigateur"])
    if rapport.when == "call" or (rapport.when == "setup" and not rapport.passed):
        RESULTATS[cle] = "ignoré" if rapport.skipped else ("réussi" if rapport.passed else "ÉCHOUÉ")
    elif rapport.when == "teardown" and rapport.failed:
        RESULTATS[cle] = "ÉCHOUÉ"


def pytest_sessionfinish(session):
    if not RESULTATS or os.environ.get("RECETTE_SANS_RAPPORT"):
        return
    scenarios = list(dict.fromkeys(nom for nom, _ in RESULTATS))
    noms = [n for n in NAVIGATEURS if any(cle[1] == n for cle in RESULTATS)]
    docstrings = {}
    for item in session.items:
        docstrings.setdefault(item.originalname, (item.function.__doc__ or "").strip().splitlines()[0])
    sortie = io.StringIO()
    sortie.write("# Résultats de la recette navigateurs automatisée\n\n")
    sortie.write(f"Passage du {datetime.now():%d/%m/%Y à %H:%M}, `python -m pytest recette_navigateurs` "
                 "(fiche `RECETTE-NAVIGATEURS.md`, audit TECH-74 à TECH-77). Fichier régénéré à chaque passage.\n\n")
    sortie.write("| Navigateur | Version |\n|---|---|\n")
    for nom in noms:
        sortie.write(f"| {LIBELLES[nom]} | {VERSIONS.get(nom, 'indisponible')} |\n")
    sortie.write("\n| Scénario | " + " | ".join(LIBELLES[n] for n in noms) + " |\n")
    sortie.write("|---|" + "---|" * len(noms) + "\n")
    for scenario in scenarios:
        cellules = [RESULTATS.get((scenario, n), "—") for n in noms]
        sortie.write(f"| {docstrings.get(scenario, scenario)} | " + " | ".join(cellules) + " |\n")
    (ICI / "RESULTATS.md").write_text(sortie.getvalue(), encoding="utf-8")
