"""Fichiers statiques versionnés en production : un fichier modifié change de nom, donc le cache de 30 jours de Nginx ne
sert plus jamais un ancien ``tailwind.css`` (les téléphones affichaient la barre du chauffeur en colonne)."""

import re

import pytest
from django.core.management import call_command
from django.test import override_settings

STOCKAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.statiques.StockageStatiqueVersionne"},
}


@pytest.fixture
def statiques(tmp_path):
    source, racine = tmp_path / "source", tmp_path / "collecte"
    (source / "css").mkdir(parents=True)
    (source / "css" / "site.css").write_text("body { color: red; }", encoding="utf-8")
    # une feuille de style qui cite une police absente, comme Font Awesome : ne doit pas faire échouer la collecte
    (source / "css" / "icones.css").write_text("@font-face { src: url(../polices/absente.woff2); }", encoding="utf-8")
    with override_settings(STORAGES=STOCKAGE, STATIC_ROOT=racine, STATICFILES_DIRS=[source]):
        yield source, racine


def _collecter():
    call_command("collectstatic", "--noinput", verbosity=0)


def test_un_fichier_statique_prend_une_empreinte_dans_son_nom(statiques):
    from django.templatetags.static import static

    _, racine = statiques
    _collecter()

    url = static("css/site.css")

    assert re.fullmatch(r"/static/css/site\.[0-9a-f]{12}\.css", url)
    assert (racine / url.removeprefix("/static/")).read_text(encoding="utf-8") == "body { color: red; }"


def test_le_nom_change_quand_le_contenu_change(statiques):
    from django.templatetags.static import static

    source, _ = statiques
    _collecter()
    avant = static("css/site.css")
    (source / "css" / "site.css").write_text("body { color: blue; }", encoding="utf-8")
    from django.contrib.staticfiles.storage import staticfiles_storage

    staticfiles_storage.hashed_files.clear()  # nouvelle collecte = nouveau processus
    _collecter()

    assert static("css/site.css") != avant


def test_une_police_citee_mais_absente_ne_fait_pas_echouer_la_collecte(statiques):
    _collecter()  # lèverait ValueError avec ManifestStaticFilesStorage nu


def test_la_production_utilise_ce_stockage(monkeypatch):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DJANGO_SETTINGS_MODULE")}
    env.update(
        SECRET_KEY="Zq9!" * 12, ALLOWED_HOSTS="erp.example.org", DATABASE_URL="postgres://u:p@localhost:5432/d",
        REDIS_URL="redis://localhost:6379/0",
    )
    code = "import config.settings.prod as p; print(p.STORAGES['staticfiles']['BACKEND'])"
    resultat = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[3], env=env, capture_output=True, text=True,
        timeout=60,
    )

    assert resultat.stdout.strip() == "apps.core.statiques.StockageStatiqueVersionne", resultat.stderr
