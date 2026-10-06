"""Cœur des outils du tutoriel : quel fichier appartient à quel chapitre, et dans quel état.

Le tutoriel (dossier ``tutoriel/``) est **généré depuis le code du dépôt** : aucun extrait n'est recopié
à la main, il ne peut donc pas diverger du projet. Ce module décide :

- à quel chapitre chaque fichier suivi par git appartient (``chapitre_de``) ;
- quels fichiers sont volontairement absents du tutoriel, et pourquoi (``EXCLUS``) ;
- l'état d'avancement de ``config/settings/base.py`` et ``config/urls.py`` à chaque chapitre
  (``etat_config``) : ces deux fichiers évoluent tout au long du projet, le tutoriel montre donc leur
  version du chapitre puis, ensuite, seulement ce qui s'ajoute ;
- les blocs dont l'apparition dans un fichier déjà présenté est volontairement retardée
  (``CHAMPS_DIFFERES``) : un champ (ou une section de documentation) qui référence une app pas encore
  créée à ce stade de la lecture est montré sans ce bloc à son chapitre, puis le bloc apparaît — comme la
  vraie migration qui l'ajoute — une fois l'app référencée créée.

Deux phases : d'abord le « cerveau » (modèles, règles métier, tests : chapitres 2 à 16), ensuite le
« visage » (écrans, gabarits, API : chapitres 17 à 31). Une app est créée dans l'ordre de ses dépendances
(``ORDRE_APPS``), vérifié par l'analyse des imports.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# --- chapitres -------------------------------------------------------------------------------------

# (identifiant, titre) dans l'ordre du tutoriel ; le numéro d'un chapitre est sa position dans la liste.
_LISTE = [
    ("prerequis", "Prérequis et vue d'ensemble"),
    ("squelette", "Le squelette du projet"),
    ("core", "Le socle : l'app core"),
    ("accounts", "Utilisateurs, rôles et sécurité de la connexion : l'app accounts"),
    ("audit", "Le journal d'audit : l'app audit"),
    ("hr", "Personnel et congés : l'app hr"),
    ("drivers", "Les chauffeurs : l'app drivers"),
    ("customers", "Les clients : l'app customers"),
    ("fleet", "Les camions : l'app fleet"),
    ("missions", "Les missions de transport : l'app missions"),
    ("garage", "Le garage : l'app garage"),
    ("inventory", "Le stock de pièces : l'app inventory"),
    ("fuel", "Le carburant : l'app fuel"),
    ("billing", "La facturation : l'app billing"),
    ("finance", "La trésorerie : l'app finance"),
    ("accounting", "La comptabilité en partie double : l'app accounting"),
    ("notifications", "Les notifications : l'app notifications"),
    ("interface", "Le socle de l'interface : gabarits, styles, connexion, notifications"),
    ("ecrans-rh", "Écrans : personnel et congés"),
    ("ecrans-chauffeurs", "Écrans : chauffeurs"),
    ("ecrans-clients", "Écrans : clients"),
    ("ecrans-flotte", "Écrans : flotte"),
    ("ecrans-missions", "Écrans : missions et codes QR"),
    ("ecrans-garage", "Écrans : garage, incidents et check-lists"),
    ("ecrans-stock", "Écrans : stock de pièces"),
    ("ecrans-carburant", "Écrans : carburant"),
    ("ecrans-finances", "Écrans : facturation, dépenses et trésorerie"),
    ("ecrans-comptabilite", "Écrans : plan comptable, opérations diverses et rapports comptables"),
    ("tableau-de-bord", "La page d'accueil : le tableau de bord"),
    ("mobile", "L'espace mobile du chauffeur"),
    ("api", "L'API REST"),
    ("importation", "L'import Excel des données : l'app importation"),
    ("finalisation", "Finalisation, vérifications et déploiement"),
]
CHAPITRES = {i: (slug, titre) for i, (slug, titre) in enumerate(_LISTE)}
NUM = {slug: i for i, (slug, _) in enumerate(_LISTE)}
DERNIER = len(_LISTE) - 1

# Ordre de création des apps (chaque app ne dépend que de celles qui la précèdent).
ORDRE_APPS = [
    "core", "accounts", "audit", "hr", "drivers", "customers", "fleet", "missions", "garage",
    "inventory", "fuel", "billing", "finance", "accounting", "notifications", "dashboard", "mobile_api", "api",
    "importation",
]
RANG = {a: i for i, a in enumerate(ORDRE_APPS)}

# Chapitre où la partie « métier » d'une app (modèles, services, tests) est écrite...
CH_METIER = {
    "core": NUM["core"], "accounts": NUM["accounts"], "audit": NUM["audit"], "hr": NUM["hr"],
    "drivers": NUM["drivers"], "customers": NUM["customers"], "fleet": NUM["fleet"],
    "missions": NUM["missions"], "garage": NUM["garage"], "inventory": NUM["inventory"],
    "fuel": NUM["fuel"], "billing": NUM["billing"], "finance": NUM["finance"],
    "accounting": NUM["accounting"],
    "notifications": NUM["notifications"], "dashboard": NUM["tableau-de-bord"],
    "mobile_api": NUM["mobile"], "api": NUM["api"], "importation": NUM["importation"],
}
# ... et où sa partie « écrans » (vues, adresses, formulaires, gabarits) est écrite.
CH_ECRANS = {
    "core": NUM["interface"], "accounts": NUM["interface"], "audit": NUM["interface"],
    "notifications": NUM["interface"], "hr": NUM["ecrans-rh"], "drivers": NUM["ecrans-chauffeurs"],
    "customers": NUM["ecrans-clients"], "fleet": NUM["ecrans-flotte"], "missions": NUM["ecrans-missions"],
    "garage": NUM["ecrans-garage"], "inventory": NUM["ecrans-stock"], "fuel": NUM["ecrans-carburant"],
    "billing": NUM["ecrans-finances"], "finance": NUM["ecrans-finances"],
    "accounting": NUM["ecrans-comptabilite"],
    "dashboard": NUM["tableau-de-bord"], "mobile_api": NUM["mobile"], "api": NUM["api"],
    "importation": NUM["importation"],
}
CH_TESTS_DASHBOARD = NUM["tableau-de-bord"]

# --- fichiers volontairement absents du tutoriel ----------------------------------------------------

EXCLUS = [
    (r"^static/vendor/", "généré par `npm run build` (bibliothèques Alpine.js et Font Awesome)"),
    (r"^static/css/tailwind\.css$", "généré par `npm run build` (Tailwind compilé)"),
    (r"^frontend/package-lock\.json$", "généré par `npm install`"),
    (r"^apps/[^/]+/migrations/(?!0002_plan_comptable_seed\.py$|0002_trigger_append_only\.py$)",
     "généré par `python manage.py makemigrations` (sauf les migrations écrites à la main : le plan comptable, "
     "voir le chapitre « La comptabilité en partie double », et les triggers PostgreSQL des journaux "
     "append-only, voir les chapitres « Le journal d'audit » et « Le stock de pièces »)"),
    (r"\.xlsx$", "classeur Excel modèle, généré par `python manage.py generer_modele_import` "
     "(voir le chapitre « L'import Excel des données »)"),
    (r"^static/img/", "identité visuelle de DEN Source Group : à copier depuis le dépôt (voir le chapitre « Le socle de l'interface »)"),
    (r"\.(docx|pptx)$", "documents de présentation, sans rapport avec le fonctionnement"),
    (r"^(cahier-des-charges|architecture|conventions|glossaire-metier|audit-checklist|GUIDE-INTERFACE|GUIDE-PARCOURS|GUIDE-DEPLOIEMENT|avenant-[\w-]+)\.md$",
     "documents de référence à lire (ils décrivent le besoin), pas à recopier"),
    (r"^(outils|tutoriel)/", "outils et sources de ce tutoriel"),
    (r"^(Dockerfile|\.dockerignore|docker-compose\.yml)$|^nginx/|^ops/",
     "mise en production (Docker, Nginx, Gunicorn) : hors périmètre de ce tutoriel de développement — voir GUIDE-DEPLOIEMENT.md"),
]

# --- classement des fichiers ------------------------------------------------------------------------

_EXTENSION_ECRAN = re.compile(
    r"(^|/)(views[^/]*\.py|urls[^/]*\.py|forms[^/]*\.py|context_processors\.py)$"
    r"|/templates/|/templatetags/"
)
_UTILISE_LE_WEB = re.compile(
    r"[(,]\s*(?:client|admin_client)\b(?!\s*=)|reverse\(|\bClient\(|APIClient|force_login|force_authenticate"
    r"|\.get\(\"/|\.post\(\"/"
)


def fichiers_suivis() -> list[str]:
    sortie = subprocess.run(
        ["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    return [f for f in sortie.split("\n") if f]


def raison_exclusion(chemin: str) -> str | None:
    for motif, raison in EXCLUS:
        if re.search(motif, chemin):
            return raison
    return None


def _imports_apps(chemin: str) -> set[str]:
    """Apps du projet importées par un fichier Python (imports de tête ou dans les fonctions)."""
    try:
        arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    trouvees: set[str] = set()
    for noeud in ast.walk(arbre):
        modules: list[str] = []
        if isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules = [noeud.module]
        elif isinstance(noeud, ast.Import):
            modules = [n.name for n in noeud.names]
        for module in modules:
            m = re.match(r"apps\.(\w+)", module)
            if m and m.group(1) in RANG:
                trouvees.add(m.group(1))
    return trouvees


def _aides_de_tests_importees(chemin: str) -> list[str]:
    """Fichiers ``apps/<app>/tests/<module>.py`` importés par chemin absolu (ex. ``apps.billing.tests.helpers``)."""
    try:
        arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    trouves = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            m = re.match(r"^apps\.(\w+)\.tests\.(\w+)$", noeud.module)
            if m and (RACINE / f"apps/{m.group(1)}/tests/{m.group(2)}.py").exists():
                trouves.append(f"apps/{m.group(1)}/tests/{m.group(2)}.py")
    return trouves


def _freres_importes(chemin: str) -> list[str]:
    """Modules du même dossier importés par ``from .module import ...`` (ex. tests qui réutilisent un autre test)."""
    try:
        arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    dossier = chemin.rsplit("/", 1)[0]
    freres = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.level == 1 and noeud.module:
            candidat = f"{dossier}/{noeud.module.split('.')[0]}.py"
            if (RACINE / candidat).exists():
                freres.append(candidat)
    return freres


# Préfixes d'adresses et espaces de noms d'URL → app qui les fournit (pour repérer les tests qui
# ouvrent les pages d'une autre app sans jamais l'importer).
_PREFIXES_URL = {
    "missions": "missions", "clients": "customers", "flotte": "fleet", "rh": "hr", "chauffeurs": "drivers",
    "garage": "garage", "carburant": "fuel", "stock": "inventory", "facturation": "billing",
    "finances": "finance", "comptabilite": "accounting", "chauffeur": "mobile_api", "api": "api",
    "notifications": "notifications", "import": "importation",
}
_ESPACES_NOMS = {
    "missions": "missions", "customers": "customers", "fleet": "fleet", "hr": "hr", "drivers": "drivers",
    "garage": "garage", "fuel": "fuel", "inventory": "inventory", "billing": "billing",
    "finance": "finance", "accounting": "accounting", "chauffeur": "mobile_api",
    "notifications": "notifications", "api": "api", "mobile": "api", "importation": "importation",
}


def _apps_dont_les_pages_sont_ouvertes(source: str) -> set[str]:
    trouvees = set()
    for m in re.finditer(r"""["']/(""" + "|".join(_PREFIXES_URL) + r""")/""", source):
        trouvees.add(_PREFIXES_URL[m.group(1)])
    for m in re.finditer(r"""["'](""" + "|".join(_ESPACES_NOMS) + r"""):[\w:]+["']""", source):
        trouvees.add(_ESPACES_NOMS[m.group(1)])
    return trouvees


def _app_de(chemin: str) -> str | None:
    m = re.match(r"^apps/(\w+)/", chemin)
    return m.group(1) if m else None


# Fichiers « écran » par leur nom mais nécessaires plus tôt (importés au démarrage par ``apps.py`` ou par
# des sections d'une autre app) : ils sont présentés avec la partie métier.
FORCES_AU_METIER = {"apps/core/forms.py": 2, "apps/inventory/forms.py": 11}

# Tests qui ouvrent des pages d'une autre app *indirectement* : le récepteur qu'ils exercent construit
# un lien (``reverse(...)``) vers une app dont les écrans n'existent pas encore, mais le test lui-même
# ne contient ni ``reverse(`` ni de chaîne "app:route" — rien dans sa source ne le révèle à
# ``_chapitre_test_seul``. Ancré par nom de fichier plutôt que deviné.
FORCES_AUX_ECRANS = {
    "apps/notifications/tests/test_receivers_proforma.py": NUM["ecrans-finances"],
    "apps/notifications/tests/test_receivers_demandes.py": NUM["ecrans-finances"],
    "apps/notifications/tests/test_receivers_frais_mission.py": NUM["ecrans-missions"],
}


def chapitre_de(chemin: str) -> int | None:
    """Numéro du chapitre qui présente ce fichier (``None`` : fichier exclu)."""
    if raison_exclusion(chemin):
        return None
    if chemin in FORCES_AU_METIER:
        return FORCES_AU_METIER[chemin]
    # --- hors des apps ---
    if not chemin.startswith("apps/"):
        if chemin.startswith("templates/importation/"):
            return NUM["importation"]
        if chemin.startswith(("templates/", "frontend/")) or chemin in ("static/js/app.js",):
            return NUM["interface"]
        if chemin in ("static/js/sw-register.js", "static/js/scanner.js"):
            return NUM["mobile"]
        if chemin == "static/js/suivi-missions.js":
            return NUM["ecrans-missions"]
        if chemin == "README.md":
            return NUM["finalisation"]
        return 1  # squelette : manage.py, config/, requirements/, .gitignore, pytest.ini...
    if chemin == "apps/__init__.py":
        return 1
    app = _app_de(chemin)
    if app is None:
        return 1
    # --- l'app « dashboard », mobile_api et api sont présentées d'un seul tenant ---
    if app in ("dashboard", "mobile_api", "api"):
        base = CH_METIER[app]
        if "/tests/" in chemin:
            return _chapitre_test(chemin, app)
        return base
    # --- tests ---
    if "/tests/" in chemin:
        return _chapitre_test(chemin, app)
    # --- écrans ou métier ---
    if _EXTENSION_ECRAN.search(chemin):
        return CH_ECRANS[app]
    return CH_METIER[app]


def _chapitre_test(chemin: str, app: str, _en_cours: frozenset = frozenset()) -> int:
    base = _chapitre_test_seul(chemin, app)
    for frere in _freres_importes(chemin) + _aides_de_tests_importees(chemin):
        if frere not in _en_cours and frere != chemin:
            base = max(base, _chapitre_test(frere, app, _en_cours | {chemin}))
    return base


def _chapitre_test_seul(chemin: str, app: str) -> int:
    """Un test est présenté dès que tout ce qu'il importe existe ; s'il ouvre des pages, avec les écrans."""
    if chemin in FORCES_AUX_ECRANS:
        return FORCES_AUX_ECRANS[chemin]
    utilises = _imports_apps(chemin) | {app}
    plus_haute = max(utilises, key=lambda a: RANG[a])
    if plus_haute == "dashboard":
        return CH_TESTS_DASHBOARD
    source = (RACINE / chemin).read_text(encoding="utf-8")
    pages_ouvertes = _apps_dont_les_pages_sont_ouvertes(source)
    ouvre_des_pages = bool(_UTILISE_LE_WEB.search(source)) or any(
        re.search(r"from apps\.\w+ import .*\b(views|forms|urls|serializers)\b", ligne)
        or re.search(r"from apps\.\w+\.(views|forms|urls|serializers)\b", ligne)
        for ligne in source.split("\n")
    )
    if ouvre_des_pages or pages_ouvertes:
        return max([CH_ECRANS[plus_haute], CH_ECRANS[app]] + [CH_ECRANS[a] for a in pages_ouvertes])
    # fichier d'aide (factories, helpers) ou test sans page : au chapitre métier de l'app la plus haute
    return max(CH_METIER[plus_haute], CH_METIER[app])


def est_vide(chemin: str) -> bool:
    return (RACINE / chemin).read_text(encoding="utf-8").strip() == ""


_ORDRE_METIER = [
    "README.md", "constants.py", "models.py", "exceptions.py", "search.py", "formats.py", "services.py",
    "signals.py", "permissions.py", "sections.py", "navigation.py", "mixins.py", "throttle.py", "mfa.py",
    "middleware.py", "receivers.py", "taches.py", "terrain.py", "registry.py", "admin.py", "apps.py",
]
_ORDRE_ECRAN = ["forms", "views", "urls", "templatetags", "templates"]


def cle_ordre(chemin: str) -> tuple:
    """Ordre de présentation dans un chapitre : métier → écrans → aides de test → tests."""
    parties = chemin.split("/")
    nom = parties[-1]
    if "/tests/" in chemin:
        aide = 0 if nom in ("factories.py", "helpers.py", "helpers_mfa.py", "conftest.py") else 1
        return (4, aide, chemin)
    if "/management/commands/" in chemin:
        return (2, 0, chemin)
    if _EXTENSION_ECRAN.search(chemin):
        rang = next((i for i, m in enumerate(_ORDRE_ECRAN) if m in chemin), len(_ORDRE_ECRAN))
        return (3, rang, chemin)
    if nom in _ORDRE_METIER:
        return (1, _ORDRE_METIER.index(nom), chemin)
    return (1, len(_ORDRE_METIER), chemin)


def fichiers_du_chapitre(numero: int, suivis: list[str] | None = None) -> list[str]:
    suivis = suivis if suivis is not None else fichiers_suivis()
    return sorted((f for f in suivis if chapitre_de(f) == numero), key=cle_ordre)


# --- rôle d'un fichier (première ligne de son docstring) -------------------------------------------

def role_du_fichier(chemin: str) -> str:
    fichier = RACINE / chemin
    texte = fichier.read_text(encoding="utf-8")
    if chemin.endswith(".py"):
        try:
            doc = ast.get_docstring(ast.parse(texte))
        except SyntaxError:
            doc = None
        if doc:
            return doc.strip().split("\n")[0].strip()
    elif chemin.endswith(".md"):
        for ligne in texte.split("\n"):
            if ligne.startswith("# "):
                return ligne[2:].strip()
    elif chemin.endswith(".html"):
        m = re.match(r"\s*\{#\s*(.*?)\s*#\}", texte)
        if m:
            return m.group(1)
    return ""


LANGAGES = {
    ".py": "python", ".html": "django", ".js": "javascript", ".css": "css", ".md": "markdown",
    ".json": "json", ".txt": "text", ".ini": "ini", ".example": "bash",
}


def langage(chemin: str) -> str:
    if chemin.endswith(".gitignore") or chemin.endswith(".env.example"):
        return "bash"
    return LANGAGES.get(Path(chemin).suffix, "text")


# --- état des fichiers de configuration à chaque chapitre -------------------------------------------

# (motif de ligne, chapitre à partir duquel la ligne existe)
_REGLES_SETTINGS = [
    (r'^\s*"apps\.%s",' % app, CH_METIER[app]) for app in ORDRE_APPS
] + [
    (r'^AUTH_USER_MODEL\b', NUM["accounts"]),
    (r'apps\.core\.middleware\.', NUM["core"]), (r'apps\.accounts\.middleware\.', NUM["accounts"]),
    (r'apps\.accounts\.context_processors\.', NUM["interface"]),
    (r'apps\.notifications\.context_processors\.', NUM["interface"]),
]
_REGLES_URLS = [
    (r'MediaProtegeView', NUM["core"]),
    (r'apps\.dashboard|Dashboard\w*View', NUM["tableau-de-bord"]),
    (r'apps\.accounts\.urls', NUM["interface"]), (r'apps\.notifications\.urls', NUM["interface"]),
    (r'apps\.audit\.urls', NUM["interface"]),
    (r'apps\.hr\.urls', NUM["ecrans-rh"]), (r'apps\.drivers\.urls', NUM["ecrans-chauffeurs"]),
    (r'apps\.customers\.urls', NUM["ecrans-clients"]), (r'apps\.fleet\.urls', NUM["ecrans-flotte"]),
    (r'apps\.missions\.urls', NUM["ecrans-missions"]), (r'apps\.garage\.urls', NUM["ecrans-garage"]),
    (r'apps\.inventory\.urls', NUM["ecrans-stock"]), (r'apps\.fuel\.urls', NUM["ecrans-carburant"]),
    (r'apps\.billing\.urls', NUM["ecrans-finances"]), (r'apps\.finance\.urls', NUM["ecrans-finances"]),
    (r'apps\.accounting\.urls', NUM["ecrans-comptabilite"]),
    (r'apps\.mobile_api\.urls_web', NUM["mobile"]), (r'apps\.api\.urls', NUM["api"]),
    (r'apps\.importation\.urls', NUM["importation"]),
]
# Fichier écrit seulement pour le tutoriel : une page d'accueil provisoire, le temps que les écrans
# (vers lesquels le tableau de bord renvoie) existent. Elle est supprimée au chapitre du tableau de bord.
ACCUEIL_PROVISOIRE = "templates/accueil_provisoire.html"
ACCUEIL_PROVISOIRE_CONTENU = """{% extends "base.html" %}
{% block titre %}Accueil{% endblock %}
{% block entete %}Accueil{% endblock %}

{% block contenu %}
<h1 class="text-2xl font-bold text-slate-900">Bienvenue</h1>
<p class="mt-2 text-sm text-slate-700">
  Page d'accueil provisoire : le tableau de bord la remplacera au chapitre « La page d'accueil : le tableau de bord ».
</p>
{% endblock %}
"""
CH_ACCUEIL_DEBUT = NUM["interface"]
CH_ACCUEIL_FIN = NUM["tableau-de-bord"]  # supprimée à ce chapitre

# (motif de ligne, premier chapitre, chapitre où l'on revient à la vraie ligne, ligne provisoire)
_REMPLACEMENTS_URLS = [
    (r'^from django\.views\.generic import RedirectView$', CH_ACCUEIL_DEBUT, CH_ACCUEIL_FIN,
     "from django.views.generic import RedirectView, TemplateView"),
    (r'DashboardView\.as_view\(\)', CH_ACCUEIL_DEBUT, CH_ACCUEIL_FIN,
     '    path("", TemplateView.as_view(template_name="accueil_provisoire.html"), name="home"),'),
]
FICHIERS_PROGRESSIFS = {
    "config/settings/base.py": _REGLES_SETTINGS,
    "config/urls.py": _REGLES_URLS,
}


def etat_config(chemin: str, chapitre: int) -> str:
    """Contenu de ``chemin`` tel qu'il doit être à la fin du ``chapitre`` (lignes des chapitres suivants retirées)."""
    regles = FICHIERS_PROGRESSIFS[chemin]
    remplacements = _REMPLACEMENTS_URLS if chemin == "config/urls.py" else []
    lignes = (RACINE / chemin).read_text(encoding="utf-8").split("\n")
    gardees = []
    for ligne in lignes:
        provisoire = next(
            (nouvelle for motif, debut, fin, nouvelle in remplacements
             if re.search(motif, ligne) and debut <= chapitre < fin),
            None,
        )
        if provisoire is not None:
            gardees.append(provisoire)
            continue
        exclue = any(re.search(motif, ligne) and chapitre < debut for motif, debut in regles)
        if not exclue:
            gardees.append(ligne)
    return "\n".join(gardees)


def chapitres_ou_config_change(chemin: str) -> list[int]:
    """Chapitres où l'état de ``chemin`` change (le premier est toujours 1)."""
    etats = {}
    changements = []
    precedent = None
    for k in range(1, DERNIER + 1):
        etat = etat_config(chemin, k)
        if etat != precedent:
            changements.append(k)
        precedent = etat
    return changements


# --- blocs dont l'apparition dans un fichier déjà présenté est retardée -----------------------------

# ``apps/missions/models.py`` déclare ``Mission.proforma`` et ``FraisMission.reglement``, qui référencent
# ``billing.Proforma`` et ``billing.Reglement`` — mais
# l'app ``billing`` n'existe qu'au chapitre 13, bien après ``missions`` (chapitre 9). Ce n'est pas un
# accident : ``billing`` dépend elle-même de ``missions`` (``billing.services`` importe ``Mission``),
# donc les deux apps ne peuvent pas être réordonnées l'une avant l'autre dans ``ORDRE_APPS``. C'est
# exactement ce que montre la vraie migration : ``apps/missions/migrations/0002_mission_proforma.py``
# (qui ajoute ce champ) dépend de ``billing.0004_proforma``, alors que ``missions.0001_initial`` (qui crée
# ``Mission``) n'en dépend pas. Le tutoriel reproduit cet ordre : le modèle (et la section du README qui
# décrit ce champ) sont montrés sans lui au chapitre 9, puis il est ajouté — avec une seconde migration —
# au chapitre 13.
#
# (motif de début, motif de fin, premier chapitre où le bloc apparaît, la ligne de fin fait-elle partie
# du bloc retiré ?) Fin incluse (``True``) : la ligne de fin — ex. la parenthèse qui referme un champ —
# est retirée avec le bloc. Fin exclue (``False``) : la ligne de fin — ex. le prochain titre ``###`` —
# n'appartient pas au bloc et reste toujours affichée ; elle ne sert qu'à borner la recherche.
CHAMPS_DIFFERES: dict[str, list[tuple[str, str, int, bool]]] = {
    "apps/missions/models.py": [
        (r'^\s*proforma = models\.OneToOneField\(\s*$', r'^\s*\)\s*$', NUM["billing"], True),
        (r'^\s*reglement = models\.ForeignKey\(\s*$', r'^\s*\)\s*$', NUM["billing"], True),
    ],
    # ``accounts`` branche l'audit sur ``User`` dans ``ready()`` ; ``audit`` n'existe qu'au chapitre 4 (et c'est lui
    # qui importe ``accounts``, pas l'inverse) : l'import et l'abonnement apparaissent donc à ce chapitre.
    "apps/accounts/apps.py": [
        (r'^\s*from apps\.audit\.registry import audit_model$', r'^$', NUM["audit"], True),
        (r'^\s*# Création de compte, changement de rôle', r'audit_model\(User, ', NUM["audit"], True),
    ],
    "apps/missions/README.md": [
        (r'^### Mission créée depuis un devis accepté \(R6\)$', r'^### ', NUM["billing"], False),
    ],
}


def sans_champs_differes(chemin: str, chapitre: int) -> str:
    """Contenu de ``chemin`` tel qu'il doit apparaître au ``chapitre`` : les blocs de ``CHAMPS_DIFFERES``
    pas encore disponibles à ce chapitre sont retirés."""
    blocs = CHAMPS_DIFFERES.get(chemin, [])
    lignes = (RACINE / chemin).read_text(encoding="utf-8").split("\n")
    gardees = []
    en_bloc = False
    disponible = True
    fin_regex = ""
    fin_incluse = True
    for ligne in lignes:
        if en_bloc:
            fin_ici = re.search(fin_regex, ligne) is not None
            if fin_ici and fin_incluse:
                if disponible:
                    gardees.append(ligne)
                en_bloc = False
                continue
            if not fin_ici:
                if disponible:
                    gardees.append(ligne)
                continue
            en_bloc = False  # fin exclue : cette ligne n'appartient pas au bloc, traitée normalement plus bas
        debut = next((b for b in blocs if re.search(b[0], ligne)), None)
        if debut is not None:
            _, fin_regex, chapitre_disponible, fin_incluse = debut
            disponible = chapitre >= chapitre_disponible
            en_bloc = True
            if disponible:
                gardees.append(ligne)
            continue
        gardees.append(ligne)
    return "\n".join(gardees)


def chapitres_ou_champ_differe(chemin: str) -> list[int]:
    """Chapitres où il faut (ré)écrire ``chemin`` à cause de ses ``CHAMPS_DIFFERES`` : son chapitre
    d'apparition, puis celui où chaque bloc retardé devient disponible."""
    return sorted({chapitre_de(chemin), *(c for _, _, c, _ in CHAMPS_DIFFERES.get(chemin, []))})


def fence(contenu: str) -> str:
    """Délimiteur de bloc de code assez long pour ne pas être coupé par le contenu (fichiers Markdown)."""
    plus_long = max((len(m) for m in re.findall(r"`+", contenu)), default=0)
    return "`" * max(3, plus_long + 1)
