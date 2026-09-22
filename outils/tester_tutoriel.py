"""Rejoue le tutoriel : reconstruit le projet chapitre par chapitre dans un dossier vide et vérifie chaque étape.

À chaque chapitre, on ajoute les fichiers de ce chapitre (tels que le tutoriel les donne), puis on lance
les commandes que le tutoriel demande au lecteur : ``manage.py check``, ``makemigrations``, ``migrate``,
et les tests du chapitre. Si une étape échoue, c'est le tutoriel qui est faux : il faut le corriger.

    python outils/tester_tutoriel.py                     # tous les chapitres, à partir du code du dépôt
    python outils/tester_tutoriel.py --source tutoriel   # à partir des chapitres générés (tutoriel/*.md)
    python outils/tester_tutoriel.py --jusqu-a 8         # s'arrêter au chapitre 8
    python outils/tester_tutoriel.py --garder            # ne pas supprimer le dossier de travail
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tutoriel_lib as t  # noqa: E402

NPM = shutil.which("npm") or "npm"
PYTHON = str(t.RACINE / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable

# Apps qui ont des modèles à migrer, par chapitre où leurs modèles sont écrits.
MIGRATIONS = {
    t.NUM[a]: [a] for a in (
        "core", "accounts", "audit", "hr", "drivers", "customers", "fleet", "missions", "garage",
        "inventory", "fuel", "billing", "finance", "notifications",
    )
}


# --- lecture du contenu des fichiers -----------------------------------------------------------------

def contenu_depot(chemin: str) -> str:
    return (t.RACINE / chemin).read_text(encoding="utf-8")


def contenus_tutoriel() -> dict[str, str]:
    """Extrait tous les fichiers présentés dans tutoriel/NN-*.md (titre ``#### `chemin` `` suivi d'un bloc)."""
    trouves: dict[str, str] = {}
    for md in sorted((t.RACINE / "tutoriel").glob("[0-9][0-9]-*.md")):
        lignes = md.read_text(encoding="utf-8").split("\n")
        i = 0
        while i < len(lignes):
            m = re.match(r"^#### `([^`]+)`( — .*)?$", lignes[i])
            if m and not m.group(2):
                # cherche l'ouverture du bloc
                j = i + 1
                while j < len(lignes) and not lignes[j].startswith("```"):
                    j += 1
                ouverture = re.match(r"^(`{3,})", lignes[j]).group(1)
                k = j + 1
                corps = []
                while lignes[k] != ouverture:
                    corps.append(lignes[k])
                    k += 1
                trouves[m.group(1)] = "\n".join(corps) + "\n"
                i = k
            i += 1
    return trouves


# --- exécution ---------------------------------------------------------------------------------------

def lancer(cmd: list[str], cwd: Path, titre: str, timeout: int = 900) -> tuple[bool, str]:
    debut = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    duree = time.time() - debut
    ok = p.returncode == 0
    print(f"    {'OK ' if ok else 'ÉCHEC'} {titre} ({duree:.0f} s)")
    return ok, (p.stdout + "\n" + p.stderr)


def ecrire(destination: Path, chemin: str, contenu: str) -> None:
    cible = destination / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["depot", "tutoriel"], default="depot")
    parser.add_argument("--jusqu-a", type=int, default=t.DERNIER)
    parser.add_argument("--garder", action="store_true")
    args = parser.parse_args()

    suivis = t.fichiers_suivis()
    if args.source == "tutoriel":
        presentes = contenus_tutoriel()
        # les fichiers vides ne sont pas présentés en bloc de code : le tutoriel donne les commandes `touch`
        # les fichiers progressifs (settings, urls) sont présentés par étapes : leur état est écrit plus bas
        lire = lambda f: "" if t.est_vide(f) or f in t.FICHIERS_PROGRESSIFS else presentes[f]  # noqa: E731
    else:
        lire = contenu_depot

    resultats: dict = {}
    en_attente: set[str] = set()
    differes: dict[str, dict] = {}
    destination = Path(tempfile.mkdtemp(prefix="tuto_"))
    print(f"Dossier de travail : {destination}")
    echecs = 0
    try:
        for k in range(1, args.jusqu_a + 1):
            nom = t.CHAPITRES[k][1]
            print(f"\n=== Chapitre {k} : {nom}")
            fichiers = t.fichiers_du_chapitre(k, suivis)
            for f in fichiers:
                ecrire(destination, f, lire(f))
            for f in t.FICHIERS_PROGRESSIFS:
                if k in t.chapitres_ou_config_change(f):
                    ecrire(destination, f, t.etat_config(f, k))
            if k == t.CH_ACCUEIL_DEBUT:
                ecrire(destination, t.ACCUEIL_PROVISOIRE, t.ACCUEIL_PROVISOIRE_CONTENU)
            if k == t.CH_ACCUEIL_FIN:
                (destination / t.ACCUEIL_PROVISOIRE).unlink()
            print(f"    {len(fichiers)} fichiers écrits")

            if k == t.NUM["interface"]:
                # images de la marque : copiées depuis le dépôt, puis compilation des styles (npm)
                for img in sorted((t.RACINE / "static" / "img").iterdir()):
                    (destination / "static" / "img").mkdir(parents=True, exist_ok=True)
                    shutil.copy(img, destination / "static" / "img" / img.name)
                ok, sortie = lancer([NPM, "install", "--no-audit", "--no-fund"], destination / "frontend", "npm install", 600)
                if ok:
                    ok, sortie = lancer([NPM, "run", "build"], destination / "frontend", "npm run build", 600)
                if not ok:
                    print(sortie[-1500:]); echecs += 1; break

            if t.NUM["interface"] < k < t.DERNIER:
                # de nouveaux gabarits sont arrivés : Tailwind doit recompiler les styles (c'est aussi ce que le tutoriel demande)
                ok, sortie = lancer([NPM, "run", "build:css"], destination / "frontend", "npm run build:css", 600)
                if not ok:
                    print(sortie[-1500:]); echecs += 1; break

            ok_chapitre = True
            if k >= 1:
                ok, sortie = lancer([PYTHON, "manage.py", "check"], destination, "manage.py check")
                if not ok:
                    print(sortie[-2500:]); echecs += 1; break
            for app in MIGRATIONS.get(k, []):
                ok, sortie = lancer([PYTHON, "manage.py", "makemigrations", app], destination, f"makemigrations {app}")
                if not ok:
                    print(sortie[-2500:]); echecs += 1; ok_chapitre = False; break
            if not ok_chapitre:
                break
            if k in MIGRATIONS and k >= t.NUM["accounts"]:
                ok, sortie = lancer([PYTHON, "manage.py", "migrate", "--noinput"], destination, "migrate")
                if not ok:
                    print(sortie[-2500:]); echecs += 1; break
            # 1) les tests déjà en attente (échoués plus tôt) : passent-ils maintenant ?
            if en_attente:
                ok, sortie = lancer(
                    [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-cov", "-rf", *sorted(en_attente)],
                    destination, f"pytest ({len(en_attente)} tests en attente)",
                )
                encore = set(re.findall(r"^FAILED (\S+)", sortie, re.M))
                for identifiant in sorted(en_attente - encore):
                    differes[identifiant]["vert_au"] = k
                    print(f"       vert au chapitre {k} : {identifiant}")
                en_attente = en_attente & encore
            # 2) les tests présentés dans ce chapitre
            tests = [f for f in fichiers if "/tests/" in f and Path(f).name.startswith("test_")]
            if tests:
                ok, sortie = lancer(
                    [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-cov", "-rf", *tests],
                    destination, f"pytest ({len(tests)} fichiers de tests du chapitre)",
                )
                resume = [l for l in sortie.split("\n") if re.search(r"\d+ (passed|failed|error)", l)]
                print("      ", resume[-1] if resume else "")
                reussis = re.search(r"(\d+) passed", resume[-1]) if resume else None
                echoues = re.search(r"(\d+) failed", resume[-1]) if resume else None
                resultats[str(k)] = {
                    "fichiers_de_tests": len(tests),
                    "reussis": int(reussis.group(1)) if reussis else 0,
                    "differes": int(echoues.group(1)) if echoues else 0,
                }
                if re.search(r"^ERROR ", sortie, re.M) or (not ok and not re.search(r"^FAILED ", sortie, re.M)):
                    print(sortie[-3500:]); echecs += 1; break  # erreur de collecte : un fichier ne s'importe pas
                for identifiant in re.findall(r"^FAILED (\S+)", sortie, re.M):
                    en_attente.add(identifiant)
                    differes[identifiant] = {"presente_au": k, "vert_au": None}
                    print(f"       en attente : {identifiant}")
        else:
            print("\n=== Vérification finale")
            ok, sortie = lancer([PYTHON, "manage.py", "makemigrations", "--check", "--dry-run"], destination, "makemigrations --check")
            if not ok:
                print(sortie[-1500:]); echecs += 1
            ok, sortie = lancer([PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-cov"], destination, "pytest (tous les tests)", 1800)
            resume = [l for l in sortie.split("\n") if re.search(r"\d+ (passed|failed|error)", l)]
            print("      ", resume[-1] if resume else "")
            total = re.search(r"(\d+) passed", resume[-1]) if resume else None
            if total:
                resultats["total"] = int(total.group(1))
            if not ok:
                print(sortie[-3000:]); echecs += 1
            if en_attente:
                print("Tests jamais devenus verts :", sorted(en_attente)); echecs += 1
            if args.jusqu_a == t.DERNIER:
                (t.RACINE / "outils" / "tests_differes.json").write_text(
                    json.dumps(differes, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
                )
                (t.RACINE / "outils" / "tutoriel_resultats.json").write_text(
                    json.dumps(resultats, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
                )
                print(f"{len(differes)} tests différés enregistrés dans outils/tests_differes.json")
    finally:
        if args.garder:
            print(f"\nDossier conservé : {destination}")
        else:
            shutil.rmtree(destination, ignore_errors=True)
    print("\nRÉSULTAT :", "tout est vert" if echecs == 0 else "échec")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
