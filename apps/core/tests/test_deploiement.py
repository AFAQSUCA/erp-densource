"""Réglages de déploiement sûrs par défaut — audits TECH-47 et TECH-49."""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def test_les_points_d_entree_des_serveurs_partent_sur_la_production_par_defaut():
    for fichier in ("config/wsgi.py", "config/asgi.py", "config/celery.py"):
        texte = (RACINE / fichier).read_text(encoding="utf-8")
        assert "config.settings.prod" in texte and "config.settings.dev" not in texte, fichier


def test_les_secrets_ne_partent_pas_dans_l_image_docker():
    exclus = (RACINE / ".dockerignore").read_text(encoding="utf-8").split()

    for secret in ("certs/", "*.pem", "*.key", "COMPTES-ESSAI.md", ".env"):
        assert secret in exclus, secret


def test_le_verrou_couvre_chaque_paquet_de_production_et_l_image_l_utilise():
    """Audit TECH-84 : versions exactes figées, pour des constructions de l'image reproductibles."""
    import re

    verrou = {
        ligne.split("==")[0]
        for ligne in (RACINE / "requirements" / "prod.lock").read_text(encoding="utf-8").splitlines()
        if "==" in ligne and not ligne.startswith("#")
    }
    for fichier in ("base.txt", "prod.txt"):
        for ligne in (RACINE / "requirements" / fichier).read_text(encoding="utf-8").splitlines():
            ligne = ligne.split("#", 1)[0].strip()
            if ligne and not ligne.startswith("-r"):
                nom = re.split(r"[\[<>=!~ ]", ligne, maxsplit=1)[0].lower().replace("_", "-")
                assert nom in verrou, f"{nom} absent de requirements/prod.lock"
    assert "-c requirements/prod.lock" in (RACINE / "Dockerfile").read_text(encoding="utf-8")
