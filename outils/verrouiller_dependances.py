"""Calcule ``requirements/prod.lock`` : la version exacte de chaque paquet installé en production — audit TECH-84.

Les fichiers ``requirements/*.txt`` ne donnent que des minimums (``>=``) : deux installations à quelques semaines
d'écart obtenaient des versions différentes. Le Dockerfile installe désormais ``prod.txt`` sous la contrainte de
``prod.lock`` (``pip install -r requirements/prod.txt -c requirements/prod.lock``).

Le verrou part des paquets installés dans ``.venv`` et parcourt l'arbre de leurs dépendances en évaluant les
conditions de plateforme comme sous **Linux** (le serveur), avec le Python du poste (3.14, comme l'image).

Usage, après une mise à jour des dépendances dans ``.venv`` :

    .venv/Scripts/python.exe outils/verrouiller_dependances.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import sys
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RACINE = Path(__file__).resolve().parents[1]
ENVIRONNEMENT_LINUX = {
    **default_environment(),
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}


def _exigences(fichier: Path) -> list[Requirement]:
    exigences = []
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if not ligne:
            continue
        if ligne.startswith("-r "):
            exigences += _exigences(fichier.parent / ligne[3:].strip())
        else:
            exigences.append(Requirement(ligne))
    return exigences


def _applicable(exigence: Requirement, extras: set[str]) -> bool:
    if exigence.marker is None:
        return True
    return any(exigence.marker.evaluate({**ENVIRONNEMENT_LINUX, "extra": extra}) for extra in (extras or {""}))


def verrouiller(fichier: Path) -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {}
    manquants: list[str] = []
    a_voir = [(exigence, set(exigence.extras)) for exigence in _exigences(fichier)]
    vus: set[tuple[str, frozenset[str]]] = set()
    while a_voir:
        exigence, extras = a_voir.pop()
        nom = canonicalize_name(exigence.name)
        if (nom, frozenset(extras)) in vus:
            continue
        vus.add((nom, frozenset(extras)))
        try:
            distribution = metadata.distribution(exigence.name)
        except metadata.PackageNotFoundError:
            manquants.append(str(exigence))
            continue
        versions[nom] = distribution.version
        for sous_exigence in map(Requirement, distribution.requires or []):
            if _applicable(sous_exigence, extras):
                a_voir.append((sous_exigence, set(sous_exigence.extras)))
    return dict(sorted(versions.items())), manquants


def main() -> int:
    versions, manquants = verrouiller(RACINE / "requirements" / "prod.txt")
    if manquants:
        print("Paquets requis sous Linux mais absents de .venv : " + ", ".join(sorted(manquants)), file=sys.stderr)
        return 1
    entete = [
        "# Fichier généré par outils/verrouiller_dependances.py : ne pas modifier à la main (audit TECH-84).",
        f"# Versions exactes des paquets de production, pour Linux et Python {platform.python_version()}.",
        "# Utilisé comme contrainte : pip install -r requirements/prod.txt -c requirements/prod.lock",
    ]
    lignes = entete + [f"{nom}=={version}" for nom, version in versions.items()]
    (RACINE / "requirements" / "prod.lock").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"requirements/prod.lock : {len(versions)} paquets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
