"""Génère le tutoriel (dossier ``tutoriel/``) à partir de ses sources et du code du dépôt.

    python outils/generer_tutoriel.py

Chaque chapitre est écrit à la main dans ``tutoriel/sources/NN-identifiant.md`` : explications, commandes,
vérifications. Le **code**, lui, n'est jamais recopié : des directives l'insèrent depuis le dépôt, ce qui
garantit que le tutoriel montre exactement le projet.

Directives (une par ligne dans une source) :

    {{FICHIER chemin}}     insère un fichier (titre, rôle, code complet)
    {{VIDES}}              commandes de création des fichiers vides du chapitre
    {{RESTANTS}}           insère tous les autres fichiers du chapitre, dans l'ordre de présentation
    {{CONFIG}}             état (chapitre 1) ou modifications de config/settings/base.py et config/urls.py
    {{TESTS}}              résultat attendu de pytest pour ce chapitre, et tests différés le cas échéant
    {{PYTEST}}             commande pytest sur les fichiers de tests du chapitre + résultat attendu
    {{RESULTAT_FINAL}}     nombre total de tests du projet (mesuré par tester_tutoriel.py)
    {{ARBORESCENCE}}       arbre complet du projet, avec le chapitre de chaque fichier
    {{INDEX}}              liste des chapitres (pour le README)
    {{COUVERTURE}}         fichiers exclus du tutoriel et pourquoi
    {{ACCUEIL_PROVISOIRE}} page d'accueil provisoire (ajoutée puis retirée)

Le générateur vérifie que **chaque fichier suivi par git** est soit présenté exactement une fois, soit
exclu pour une raison écrite dans ``tutoriel_lib.EXCLUS``. Il échoue sinon.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tutoriel_lib as t  # noqa: E402

SOURCES = t.RACINE / "tutoriel" / "sources"
SORTIE = t.RACINE / "tutoriel"


def nom_fichier(numero: int) -> str:
    return f"{numero:02d}-{t.CHAPITRES[numero][0]}.md"


def lire(chemin: str) -> str:
    return (t.RACINE / chemin).read_text(encoding="utf-8").replace("\r\n", "\n")


def resultats() -> dict:
    fichier = t.RACINE / "outils" / "tutoriel_resultats.json"
    return json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}


def differes() -> dict:
    fichier = t.RACINE / "outils" / "tests_differes.json"
    return json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}


# --- blocs ------------------------------------------------------------------------------------------

def bloc_fichier(chemin: str) -> str:
    contenu = lire(chemin)
    if not contenu.endswith("\n"):
        contenu += "\n"
    role = t.role_du_fichier(chemin)
    lignes = contenu.count("\n")
    delim = t.fence(contenu)
    entete = f"#### `{chemin}`\n\n"
    detail = f"*{lignes} ligne{'s' if lignes > 1 else ''}*" + (f" — {role}" if role else "")
    return f"{entete}{detail}\n\n{delim}{t.langage(chemin)}\n{contenu}{delim}\n"


def bloc_fichiers_vides(fichiers: list[str]) -> str:
    if not fichiers:
        return ""
    dossiers = sorted({str(Path(f).parent) for f in fichiers})
    lignes = "\n".join(f"touch {f}" for f in fichiers)
    return (
        "#### Fichiers vides à créer\n\n"
        "Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* "
        "(sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :\n\n"
        "```bash\n"
        f"mkdir -p {' '.join(dossiers)}\n"
        f"{lignes}\n"
        "```\n\n"
        "> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` "
        "s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.\n"
    )


def bloc_config(numero: int) -> str:
    sortie = []
    for chemin in t.FICHIERS_PROGRESSIFS:
        changements = t.chapitres_ou_config_change(chemin)
        if numero not in changements:
            continue
        etat = t.etat_config(chemin, numero)
        if numero == changements[0]:
            delim = t.fence(etat)
            sortie.append(
                f"#### `{chemin}` — état au chapitre {numero}\n\n"
                f"*Ce fichier évolue au fil du tutoriel : voici sa version à ce stade. "
                f"Les chapitres suivants n'en montrent que les ajouts.*\n\n"
                f"{delim}python\n{etat}\n{delim}\n"
            )
        else:
            avant = t.etat_config(chemin, numero - 1)
            diff = list(difflib.unified_diff(
                avant.split("\n"), etat.split("\n"), fromfile=f"{chemin} (avant)", tofile=f"{chemin} (après)",
                lineterm="", n=2,
            ))
            corps = "\n".join(diff)
            delim = t.fence(corps)
            sortie.append(
                f"#### `{chemin}` — modifications\n\n"
                f"*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*\n\n"
                f"{delim}diff\n{corps}\n{delim}\n"
            )
    return "\n".join(sortie)


def bloc_tests(numero: int) -> str:
    res = resultats().get(str(numero))
    if not res:
        return ""
    ligne = f"**Résultat attendu :** `{res['reussis']} passed`"
    if res["differes"]:
        ligne = f"**Résultat attendu :** `{res['reussis']} passed, {res['differes']} failed`"
    ligne += f" (pour les {res['fichiers_de_tests']} fichier(s) de tests présentés dans ce chapitre)."
    lignes = [ligne]
    en_attente = {
        k: v for k, v in differes().items() if v["presente_au"] == numero and v["vert_au"] not in (None, numero)
    }
    if en_attente:
        lignes.append(
            "\nDes tests échouent à ce stade, **c'est normal** : ils vérifient des écrans qui n'existent pas encore "
            "(par exemple la page d'accueil). Ils passeront au chapitre indiqué :\n"
        )
        for identifiant, info in sorted(en_attente.items()):
            cible = t.CHAPITRES[info["vert_au"]][1]
            lignes.append(f"- `{identifiant.split('/')[-1]}` → chapitre {info['vert_au']} (« {cible} »)")
    return "\n".join(lignes) + "\n"


def bloc_pytest(numero: int, du_chapitre: list[str]) -> str:
    """Commande pytest limitée aux fichiers de tests du chapitre, puis résultat attendu."""
    tests = [f for f in du_chapitre if "/tests/" in f and Path(f).name.startswith("test_")]
    if not tests:
        return ""
    commande = "python -m pytest " + " ".join(tests) + " -q --no-cov"
    return "```bash\n" + commande + "\n```\n\n" + bloc_tests(numero)


def bloc_resultat_final() -> str:
    total = resultats().get("total")
    if not total:
        return ""
    return f"**Résultat attendu :** `{total} passed` (tous les tests du projet)."


def bloc_arborescence(suivis: list[str]) -> str:
    """Arbre du projet ; chaque fichier porte le numéro du chapitre qui le présente."""
    arbre: dict = {}
    for chemin in sorted(suivis):
        if chemin.startswith(("outils/", "tutoriel/")):
            continue
        noeud = arbre
        for partie in chemin.split("/"):
            noeud = noeud.setdefault(partie, {})
    lignes = ["```text", "erp-densource/"]

    def ecrire(noeud: dict, prefixe: str, chemin: str) -> None:
        elements = sorted(noeud.items(), key=lambda kv: (not kv[1], kv[0]))
        for i, (nom, enfants) in enumerate(elements):
            dernier = i == len(elements) - 1
            branche = "└── " if dernier else "├── "
            complet = f"{chemin}{nom}"
            if enfants:
                lignes.append(f"{prefixe}{branche}{nom}/")
                ecrire(enfants, prefixe + ("    " if dernier else "│   "), complet + "/")
            else:
                ch = t.chapitre_de(complet)
                etiquette = f"  ← ch. {ch}" if ch is not None else f"  ← ({t.raison_exclusion(complet).split(' (')[0]})"
                lignes.append(f"{prefixe}{branche}{nom}{etiquette}")

    ecrire(arbre, "", "")
    lignes.append("```")
    return "\n".join(lignes) + "\n"


def bloc_index() -> str:
    suivis = t.fichiers_suivis()
    lignes = ["| N° | Chapitre | Fichiers | Lignes de code |", "|---|---|---|---|"]
    for k in range(0, t.DERNIER + 1):
        fichiers = t.fichiers_du_chapitre(k, suivis)
        total = sum(len(lire(f).split("\n")) for f in fichiers)
        lignes.append(
            f"| {k} | [{t.CHAPITRES[k][1]}]({nom_fichier(k)}) | {len(fichiers) or '—'} | {total or '—'} |"
        )
    return "\n".join(lignes) + "\n"


def bloc_couverture(suivis: list[str]) -> str:
    excl: dict[str, list[str]] = {}
    for f in suivis:
        r = t.raison_exclusion(f)
        if r and not f.startswith(("outils/", "tutoriel/")):
            excl.setdefault(r, []).append(f)
    lignes = ["| Fichiers | Raison |", "|---|---|"]
    for raison, fs in sorted(excl.items(), key=lambda kv: -len(kv[1])):
        exemples = ", ".join(f"`{f}`" for f in fs[:3]) + (" …" if len(fs) > 3 else "")
        lignes.append(f"| {len(fs)} ({exemples}) | {raison} |")
    return "\n".join(lignes) + "\n"


# --- assemblage -------------------------------------------------------------------------------------

def generer_chapitre(numero: int, suivis: list[str], deja: set[str]) -> str:
    source_fichier = SOURCES / nom_fichier(numero)
    if not source_fichier.exists():
        raise SystemExit(f"Source manquante : {source_fichier.relative_to(t.RACINE)}")
    source = source_fichier.read_text(encoding="utf-8")
    du_chapitre = t.fichiers_du_chapitre(numero, suivis)
    slug, titre = t.CHAPITRES[numero]
    # les fichiers de configuration progressifs sont présentés par {{CONFIG}}, pas par {{FICHIER}}
    deja.update(f for f in t.FICHIERS_PROGRESSIFS if f in du_chapitre)

    def remplacer(m: re.Match) -> str:
        directive, _, argument = m.group(1).partition(" ")
        argument = argument.strip()
        if directive == "FICHIER":
            if argument not in du_chapitre:
                raise SystemExit(f"{source_fichier.name} : « {argument} » n'appartient pas au chapitre {numero}")
            if argument in deja:
                raise SystemExit(f"{source_fichier.name} : « {argument} » est déjà présenté")
            deja.add(argument)
            return bloc_fichier(argument)
        if directive == "VIDES":
            vides = [f for f in du_chapitre if t.est_vide(f) and f not in deja]
            deja.update(vides)
            return bloc_fichiers_vides(vides)
        if directive == "RESTANTS":
            restants = [f for f in du_chapitre if f not in deja]
            vides = [f for f in restants if t.est_vide(f)]
            pleins = [f for f in restants if f not in vides]
            deja.update(restants)
            return bloc_fichiers_vides(vides) + ("\n" if vides else "") + "\n".join(bloc_fichier(f) for f in pleins)
        if directive == "CONFIG":
            return bloc_config(numero)
        if directive == "TESTS":
            return bloc_tests(numero)
        if directive == "RESULTAT_FINAL":
            return bloc_resultat_final()
        if directive == "PYTEST":
            return bloc_pytest(numero, du_chapitre)
        if directive == "ARBORESCENCE":
            return bloc_arborescence(suivis)
        if directive == "INDEX":
            return bloc_index()
        if directive == "COUVERTURE":
            return bloc_couverture(suivis)
        if directive == "ACCUEIL_PROVISOIRE":
            contenu = t.ACCUEIL_PROVISOIRE_CONTENU
            return (
                f"#### `{t.ACCUEIL_PROVISOIRE}`\n\n*Fichier provisoire, propre au tutoriel : il sera supprimé au chapitre "
                f"« {t.CHAPITRES[t.CH_ACCUEIL_FIN][1]} ».*\n\n```django\n{contenu}```\n"
            )
        raise SystemExit(f"{source_fichier.name} : directive inconnue « {directive} »")

    corps = re.sub(r"^\{\{(.+?)\}\}\s*$", remplacer, source, flags=re.M)
    total = sum(len(lire(f).split("\n")) for f in du_chapitre)
    pied = []
    if numero > 0:
        pied.append(f"[← Chapitre {numero - 1}]({nom_fichier(numero - 1)})")
    pied.append("[Sommaire](README.md)")
    if numero < t.DERNIER:
        pied.append(f"[Chapitre {numero + 1} →]({nom_fichier(numero + 1)})")
    entete = f"# Chapitre {numero} — {titre}\n\n"
    if du_chapitre:
        entete += f"> {len(du_chapitre)} fichier(s) dans ce chapitre, {total} lignes de code.\n\n"
    return entete + corps.strip() + "\n\n---\n\n" + " · ".join(pied) + "\n"


def main() -> int:
    suivis = [f for f in t.fichiers_suivis() if not f.startswith("tutoriel/")]
    # tous les fichiers suivis (hors tutoriel) sont-ils couverts ?
    sans_chapitre = [f for f in suivis if t.chapitre_de(f) is None and not t.raison_exclusion(f)]
    if sans_chapitre:
        raise SystemExit(f"Fichiers sans chapitre : {sans_chapitre}")

    deja: set[str] = set()
    SORTIE.mkdir(exist_ok=True)
    for ancien in SORTIE.glob("[0-9][0-9]-*.md"):
        ancien.unlink()
    for numero in range(0, t.DERNIER + 1):
        (SORTIE / nom_fichier(numero)).write_text(generer_chapitre(numero, suivis, deja), encoding="utf-8", newline="\n")

    # couverture : tout fichier attendu a-t-il été présenté ?
    attendus = {f for f in suivis if t.chapitre_de(f) is not None}
    manquants = sorted(attendus - deja)
    if manquants:
        raise SystemExit(f"Fichiers non présentés (ajoutez {{{{RESTANTS}}}} à la source du chapitre) : {manquants[:10]}")

    # README
    source_readme = SOURCES / "README.md"
    if not source_readme.exists():
        raise SystemExit("Source manquante : tutoriel/sources/README.md")
    readme = re.sub(
        r"^\{\{(.+?)\}\}\s*$",
        lambda m: {"INDEX": bloc_index, "COUVERTURE": lambda: bloc_couverture(suivis)}[m.group(1).strip()](),
        source_readme.read_text(encoding="utf-8"),
        flags=re.M,
    )
    (SORTIE / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    lignes = sum(len((SORTIE / nom_fichier(k)).read_text(encoding="utf-8").split("\n")) for k in range(t.DERNIER + 1))
    print(f"{t.DERNIER + 1} chapitres générés, {len(attendus)} fichiers présentés, {lignes} lignes de Markdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
