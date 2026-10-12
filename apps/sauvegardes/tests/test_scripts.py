"""Scripts de sauvegarde (ops/) : le mot de passe de la base ne doit jamais apparaître dans la liste des processus
(audit AUD-18). Exécutés seulement si bash est disponible."""

import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

BASH = shutil.which("bash")
FONCTIONS = Path(settings.BASE_DIR) / "ops" / "fonctions-sauvegarde.sh"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent")


def _executer(script: str) -> list[str]:
    resultat = subprocess.run(
        [BASH, "-c", f". '{FONCTIONS.as_posix()}'\n{script}"], capture_output=True, text=True, check=True
    )
    return resultat.stdout.splitlines()


def test_le_mot_de_passe_quitte_l_url_pour_un_fichier_pgpass_prive():
    url, pgpass, droits = _executer(
        "preparer_connexion 'postgres://erp:p%40ss:w\\rd@db:5432/erp_densource'\n"
        'echo "$URL_SANS_MOT_DE_PASSE"; cat "$PGPASSFILE"; stat -c %a "$PGPASSFILE"; supprimer_temporaires'
    )

    assert url == "postgres://erp@db:5432/erp_densource"
    assert pgpass == "*:*:*:*:p@ss\\:w\\\\rd"  # %40 décodé ; « : » et « \\ » échappés (format .pgpass)
    assert droits == "600"


def test_une_url_sans_mot_de_passe_reste_telle_quelle():
    (url,) = _executer("preparer_connexion 'postgres://erp@db/erp'; echo \"$URL_SANS_MOT_DE_PASSE${PGPASSFILE:-}\"")

    assert url == "postgres://erp@db/erp"


def test_les_fichiers_temporaires_sont_supprimes():
    (restant,) = _executer(
        "SAUVEGARDE_PASSPHRASE=secret; preparer_phrase_de_passe; preparer_connexion 'postgres://a:b@h/d'\n"
        'supprimer_temporaires; ls "$SAUVEGARDE_PASSPHRASE_FILE" "$PGPASSFILE" 2>/dev/null | wc -l'
    )

    assert restant.strip() == "0"
