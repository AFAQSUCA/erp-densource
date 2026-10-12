"""Garde-fous pour PostgreSQL (la production), que la suite lancée sur SQLite ne voit pas.

``select_for_update()`` combiné à ``select_related`` verrouille aussi les tables jointes ; PostgreSQL refuse de
verrouiller le côté facultatif d'une jointure (« FOR UPDATE cannot be applied to the nullable side of an outer
join ») alors que SQLite ne verrouille rien : la sortie du personnel plantait en production (erreur 500). Il faut
``select_for_update(of=("self",))``.
"""

import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]

# Une même expression (sans point-virgule ni ligne vide) qui verrouille sans « of= » et charge une relation.
VERROU_AVEC_JOINTURE = re.compile(
    r"select_for_update\(\)[^;\n]*select_related|select_related\([^)]*\)[^;\n]*select_for_update\(\)"
)


def test_aucun_verrou_sans_of_sur_une_requete_avec_jointure():
    fautifs = []
    for fichier in APPS.rglob("*.py"):
        if "tests" in fichier.parts or "migrations" in fichier.parts:
            continue
        texte = fichier.read_text(encoding="utf-8")
        for correspondance in VERROU_AVEC_JOINTURE.finditer(texte):
            ligne = texte.count("\n", 0, correspondance.start()) + 1
            fautifs.append(f"{fichier.relative_to(APPS.parent)}:{ligne}")

    assert not fautifs, "select_for_update(of=(\"self\",)) attendu : " + ", ".join(fautifs)
