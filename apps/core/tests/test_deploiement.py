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
