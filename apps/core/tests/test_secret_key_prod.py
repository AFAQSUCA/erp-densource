"""Le réglage de production refuse de démarrer avec une SECRET_KEY publique (audit : SECRET_KEY par défaut)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
CLE_SURE = "k" * 10 + "Z" * 10 + "9" * 10 + "!" * 10 + "abcdef"


def _importer_prod(**variables):
    env = {
        k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DJANGO_SETTINGS_MODULE")
    }
    env.update(
        ALLOWED_HOSTS="erp.example.org",
        DATABASE_URL="postgres://u:p@localhost:5432/d",
        REDIS_URL="redis://localhost:6379/0",
        **variables,
    )
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=RACINE, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.mark.parametrize(
    "cle",
    ["django-insecure-change-me-in-env", "django-insecure-autre", "change-me", "trop-courte"],
)
def test_la_production_refuse_une_cle_par_defaut_ou_trop_courte(cle):
    resultat = _importer_prod(SECRET_KEY=cle)

    assert resultat.returncode != 0
    assert "SECRET_KEY" in resultat.stderr and "ImproperlyConfigured" in resultat.stderr


def test_la_production_refuse_l_absence_de_cle():
    resultat = _importer_prod()  # ni .env ni variable : la valeur par défaut du dépôt s'applique

    assert resultat.returncode != 0
    assert "ImproperlyConfigured" in resultat.stderr


def test_la_production_demarre_avec_une_vraie_cle():
    resultat = _importer_prod(SECRET_KEY=CLE_SURE)

    assert resultat.returncode == 0, resultat.stderr
