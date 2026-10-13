"""Le graphe des dépendances entre apps : sans cycle, et tel que le décrit architecture.md — audit AUD-20.

Une dépendance = un import ``apps.<autre>`` hors tests et migrations. Le schéma du document (§ 3) ne trace pas les
flèches vers le socle (``core``, ``accounts``, ``audit``, ``parametres``), dont dépendent toutes les apps.
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
SOCLE = {"core", "accounts", "audit", "parametres"}
NOEUDS = {  # nœud du schéma -> app
    "CORE": "core", "ACC": "accounts", "AUDIT": "audit", "PARAM": "parametres", "SAUV": "sauvegardes",
    "HR": "hr", "DRV": "drivers", "CUST": "customers", "FLEET": "fleet",
    "MISSION": "missions", "FUEL": "fuel", "GARAGE": "garage", "INV": "inventory",
    "BILL": "billing", "FIN": "finance", "ACCT": "accounting",
    "NOTIF": "notifications", "DASH": "dashboard", "IMPORT": "importation",
    "APIV1": "api", "MOBAPI": "mobile_api",
}


def dependances() -> dict[str, set[str]]:
    apps = {p.name for p in (RACINE / "apps").iterdir() if (p / "apps.py").exists()}
    graphe = {app: set() for app in apps}
    for app in apps:
        for fichier in (RACINE / "apps" / app).rglob("*.py"):
            if "tests" in fichier.parts or "migrations" in fichier.parts:
                continue
            for autre in re.findall(r"(?:from|import)\s+apps\.(\w+)", fichier.read_text(encoding="utf-8")):
                if autre != app and autre in apps:
                    graphe[app].add(autre)
    return graphe


def test_aucune_dependance_circulaire_entre_apps():
    graphe, etat = dependances(), {}

    def visiter(app, chemin):
        etat[app] = "en cours"
        for autre in graphe[app]:
            assert etat.get(autre) != "en cours", "cycle : " + " -> ".join([*chemin, app, autre])
            if autre not in etat:
                visiter(autre, [*chemin, app])
        etat[app] = "fait"

    for app in sorted(graphe):
        if app not in etat:
            visiter(app, [])


def test_le_schema_d_architecture_decrit_les_dependances_reelles():
    texte = (RACINE / "architecture.md").read_text(encoding="utf-8")
    schema = texte.split("## 3. VUE COMPOSANTS", 1)[1].split("```", 2)[1]
    documentees = {(NOEUDS[a], NOEUDS[b]) for a, b in re.findall(r"^\s*(\w+) --> (\w+)\s*$", schema, re.M)}
    reelles = {(dep, app) for app, deps in dependances().items() for dep in deps if dep not in SOCLE}

    assert not reelles - documentees, f"dépendances absentes du schéma : {sorted(reelles - documentees)}"
    assert not documentees - reelles, f"flèches du schéma sans import réel : {sorted(documentees - reelles)}"
