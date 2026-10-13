"""Scénario E1 de la fiche RECETTE-NAVIGATEURS.md : le suivi des missions se met à jour sans recharger la page.

Le serveur de test de pytest ne sait pas servir de WebSocket : ce scénario lance à part le ``runserver`` de Daphne
(comme en développement) sur une base jetable préparée pour l'occasion (``reglages_asgi.py``).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from .conftest import NAVIGATEURS, suivre_erreurs, verifier_console

RACINE = Path(__file__).resolve().parent.parent
MOT_DE_PASSE = "Test-Passw0rd!"

# Un compte du bureau et une mission par navigateur (chacun annule la sienne), créés une fois au démarrage.
PREPARATION = """
import json
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.mobile_api.tests.helpers import chauffeur_avec_compte, mission_de
UserFactory(username="suivi", role=Role.CHARGE_CLIENTELE)
missions = {}
for nom in NOMS:
    fiche, _ = chauffeur_avec_compte()
    mission = mission_de(fiche)
    missions[nom] = {"mission": mission.pk, "numero": mission.numero}
print("RESULTAT" + json.dumps(missions))
"""


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def serveur_asgi(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("asgi")
    env = {
        **os.environ, "DJANGO_SETTINGS_MODULE": "recette_navigateurs.reglages_asgi",
        "RECETTE_BASE": str(dossier / "recette.sqlite3"), "PYTHONIOENCODING": "utf-8",
    }
    env.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    manage = [sys.executable, str(RACINE / "manage.py")]
    subprocess.run([*manage, "migrate", "--noinput", "-v", "0"], cwd=RACINE, env=env, check=True)
    preparation = PREPARATION.replace("NOMS", repr(list(NAVIGATEURS)))
    sortie = subprocess.run(
        [*manage, "shell", "-c", preparation], cwd=RACINE, env=env, check=True, capture_output=True, text=True,
    ).stdout
    missions = json.loads(sortie.split("RESULTAT", 1)[1])
    port = _port_libre()
    processus = subprocess.Popen(
        [*manage, "runserver", "--noreload", f"127.0.0.1:{port}"], cwd=RACINE, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("Le serveur ASGI de la recette n'a pas démarré")
        yield {"url": f"http://127.0.0.1:{port}", "missions": missions}
    finally:
        processus.terminate()
        processus.wait(timeout=10)


def test_e1_suivi_des_missions_en_direct(navigateur, serveur_asgi):
    """E1 — Suivi des missions : l'écran se met à jour seul quand une mission change"""
    mission = serveur_asgi["missions"][navigateur.nom]
    contexte = navigateur.new_context(base_url=serveur_asgi["url"], locale="fr-FR", viewport={"width": 1366, "height": 850})
    try:
        suivi = contexte.new_page()
        suivre_erreurs(suivi)
        suivi.goto("/connexion/")
        suivi.fill("#id_username", "suivi")
        suivi.fill("#id_password", MOT_DE_PASSE)
        suivi.click("button[type=submit]")
        expect(suivi.get_by_role("button", name="Déconnexion")).to_be_visible()

        suivi.goto("/missions/")
        expect(suivi.locator("#suivi-voyant [data-etat=connecte]")).to_be_visible(timeout=10000)
        ligne = suivi.locator("tr", has_text=mission["numero"])
        expect(ligne).not_to_contain_text("Annulée")

        # Un autre onglet (même session) annule la mission : le premier ne recharge rien lui-même.
        action = contexte.new_page()
        action.goto(f"/missions/{mission['mission']}/")
        action.get_by_role("button", name="Annuler la mission").click()
        action.fill("#motif-annulation", "Recette du suivi en direct")
        action.once("dialog", lambda dialogue: dialogue.accept())
        action.get_by_role("button", name="Confirmer l'annulation").click()
        expect(action.get_by_text(re.compile("annulée")).first).to_be_visible()

        expect(suivi.locator("#suivi-annonce")).to_contain_text("Annulée", timeout=10000)
        expect(suivi.locator("tr", has_text=mission["numero"])).to_contain_text("Annulée", timeout=10000)
        # Le runserver de Daphne sert mal la police d'icônes à Firefox (repli sur un .ttf absent) ; en production,
        # Nginx sert les fichiers statiques, et le scénario B1 vérifie leur chargement dans chaque navigateur.
        verifier_console(suivi, sauf=("downloadable font", "/webfonts/"))
    finally:
        contexte.close()
