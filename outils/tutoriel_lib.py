"""Cœur des outils du tutoriel : quel fichier appartient à quel chapitre, et dans quel état.

Le tutoriel (dossier ``tutoriel/``) est **généré depuis le code du dépôt** : aucun extrait n'est recopié
à la main, il ne peut donc pas diverger du projet. Ce module décide :

- à quel chapitre chaque fichier suivi par git appartient (``chapitre_de``) ;
- quels fichiers sont volontairement absents du tutoriel, et pourquoi (``EXCLUS``) ;
- l'état d'avancement de ``config/settings/base.py`` et ``config/urls.py`` à chaque chapitre
  (``etat_config``) : ces deux fichiers évoluent tout au long du projet, le tutoriel montre donc leur
  version du chapitre puis, ensuite, seulement ce qui s'ajoute.

Deux phases : d'abord le « cerveau » (modèles, règles métier, tests : chapitres 2 à 15), ensuite le
« visage » (écrans, gabarits, API : chapitres 16 à 29). Une app est créée dans l'ordre de ses dépendances
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
    ("tableau-de-bord", "La page d'accueil : le tableau de bord"),
    ("mobile", "L'espace mobile du chauffeur"),
    ("api", "L'API REST"),
    ("finalisation", "Finalisation, vérifications et déploiement"),
]
CHAPITRES = {i: (slug, titre) for i, (slug, titre) in enumerate(_LISTE)}
NUM = {slug: i for i, (slug, _) in enumerate(_LISTE)}
DERNIER = len(_LISTE) - 1

# Ordre de création des apps (chaque app ne dépend que de celles qui la précèdent).
ORDRE_APPS = [
    "core", "accounts", "audit", "hr", "drivers", "customers", "fleet", "missions", "garage",
    "inventory", "fuel", "billing", "finance", "notifications", "dashboard", "mobile_api", "api",
]
RANG = {a: i for i, a in enumerate(ORDRE_APPS)}

# Chapitre où la partie « métier » d'une app (modèles, services, tests) est écrite...
CH_METIER = {
    "core": NUM["core"], "accounts": NUM["accounts"], "audit": NUM["audit"], "hr": NUM["hr"],
    "drivers": NUM["drivers"], "customers": NUM["customers"], "fleet": NUM["fleet"],
    "missions": NUM["missions"], "garage": NUM["garage"], "inventory": NUM["inventory"],
    "fuel": NUM["fuel"], "billing": NUM["billing"], "finance": NUM["finance"],
    "notifications": NUM["notifications"], "dashboard": NUM["tableau-de-bord"],
    "mobile_api": NUM["mobile"], "api": NUM["api"],
}
# ... et où sa partie « écrans » (vues, adresses, formulaires, gabarits) est écrite.
CH_ECRANS = {
    "core": NUM["interface"], "accounts": NUM["interface"], "audit": NUM["interface"],
    "notifications": NUM["interface"], "hr": NUM["ecrans-rh"], "drivers": NUM["ecrans-chauffeurs"],
    "customers": NUM["ecrans-clients"], "fleet": NUM["ecrans-flotte"], "missions": NUM["ecrans-missions"],
    "garage": NUM["ecrans-garage"], "inventory": NUM["ecrans-stock"], "fuel": NUM["ecrans-carburant"],
    "billing": NUM["ecrans-finances"], "finance": NUM["ecrans-finances"],
    "dashboard": NUM["tableau-de-bord"], "mobile_api": NUM["mobile"], "api": NUM["api"],
}
CH_TESTS_DASHBOARD = NUM["tableau-de-bord"]

# --- fichiers volontairement absents du tutoriel ----------------------------------------------------

EXCLUS = [
    (r"^static/vendor/", "généré par `npm run build` (bibliothèques Alpine.js et Font Awesome)"),
    (r"^static/css/tailwind\.css$", "généré par `npm run build` (Tailwind compilé)"),
    (r"^frontend/package-lock\.json$", "généré par `npm install`"),
    (r"^apps/[^/]+/migrations/", "généré par `python manage.py makemigrations`"),
    (r"^static/img/", "identité visuelle de DEN Source Group : à copier depuis le dépôt (voir le chapitre « Le socle de l'interface »)"),
    (r"\.(docx|pptx)$", "documents de présentation, sans rapport avec le fonctionnement"),
    (r"^(cahier-des-charges|architecture|conventions|glossaire-metier|audit-checklist|GUIDE-INTERFACE|GUIDE-PARCOURS)\.md$",
     "documents de référence à lire (ils décrivent le besoin), pas à recopier"),
    (r"^(outils|tutoriel)/", "outils et sources de ce tutoriel"),
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
    "finances": "finance", "chauffeur": "mobile_api", "api": "api", "notifications": "notifications",
}
_ESPACES_NOMS = {
    "missions": "missions", "customers": "customers", "fleet": "fleet", "hr": "hr", "drivers": "drivers",
    "garage": "garage", "fuel": "fuel", "inventory": "inventory", "billing": "billing",
    "finance": "finance", "chauffeur": "mobile_api", "notifications": "notifications", "api": "api",
    "mobile": "api",
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


def chapitre_de(chemin: str) -> int | None:
    """Numéro du chapitre qui présente ce fichier (``None`` : fichier exclu)."""
    if raison_exclusion(chemin):
        return None
    if chemin in FORCES_AU_METIER:
        return FORCES_AU_METIER[chemin]
    # --- hors des apps ---
    if not chemin.startswith("apps/"):
        if chemin.startswith(("templates/", "frontend/")) or chemin in ("static/js/app.js",):
            return NUM["interface"]
        if chemin in ("static/js/sw-register.js", "static/js/scanner.js"):
            return NUM["mobile"]
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
    (r'apps\.dashboard|DashboardView', NUM["tableau-de-bord"]),
    (r'apps\.accounts\.urls', NUM["interface"]), (r'apps\.notifications\.urls', NUM["interface"]),
    (r'apps\.hr\.urls', NUM["ecrans-rh"]), (r'apps\.drivers\.urls', NUM["ecrans-chauffeurs"]),
    (r'apps\.customers\.urls', NUM["ecrans-clients"]), (r'apps\.fleet\.urls', NUM["ecrans-flotte"]),
    (r'apps\.missions\.urls', NUM["ecrans-missions"]), (r'apps\.garage\.urls', NUM["ecrans-garage"]),
    (r'apps\.inventory\.urls', NUM["ecrans-stock"]), (r'apps\.fuel\.urls', NUM["ecrans-carburant"]),
    (r'apps\.billing\.urls', NUM["ecrans-finances"]), (r'apps\.finance\.urls', NUM["ecrans-finances"]),
    (r'apps\.mobile_api\.urls_web', NUM["mobile"]), (r'apps\.api\.urls', NUM["api"]),
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


def fence(contenu: str) -> str:
    """Délimiteur de bloc de code assez long pour ne pas être coupé par le contenu (fichiers Markdown)."""
    plus_long = max((len(m) for m in re.findall(r"`+", contenu)), default=0)
    return "`" * max(3, plus_long + 1)
