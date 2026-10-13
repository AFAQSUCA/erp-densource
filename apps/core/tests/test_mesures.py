"""Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24)."""

import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
import yaml
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.core import mesures
from apps.sauvegardes import services as sauvegardes

pytestmark = pytest.mark.django_db

JETON = "jeton-de-test-0123456789"
RACINE = Path(settings.BASE_DIR)
# Une ligne de mesure : nom{étiquettes} valeur (format texte de Prometheus 0.0.4).
LIGNE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{([a-zA-Z_][a-zA-Z0-9_]*="(\\.|[^"\\])*",?)*\})? -?[0-9.e+Inf]+$')


@pytest.fixture(autouse=True)
def _cache_vide(settings):
    settings.METRIQUES_JETON = JETON
    cache.clear()
    yield
    cache.clear()


def _lire(client, jeton=JETON):
    entetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"} if jeton is not None else {}
    return client.get(mesures.CHEMIN, **entetes)


def _valeurs(texte: str) -> dict[str, float]:
    return {ligne.rsplit(" ", 1)[0]: float(ligne.rsplit(" ", 1)[1]) for ligne in texte.splitlines() if not ligne.startswith("#")}


def test_les_requetes_sont_comptees_par_ecran_methode_et_statut(client):
    client.get(reverse("accounts:login"))
    client.get(reverse("accounts:login"))
    client.post(reverse("accounts:login"), {"username": "personne", "password": "x"})
    client.get("/adresse-inconnue/")

    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs['erp_requetes_total{vue="accounts:login",methode="GET",statut="2xx"}'] == 2
    assert valeurs['erp_requetes_total{vue="accounts:login",methode="POST",statut="2xx"}'] == 1
    assert valeurs['erp_requetes_total{vue="aucune",methode="GET",statut="4xx"}'] == 1
    assert valeurs['erp_requete_duree_secondes_count'] == 4 and valeurs['erp_requete_duree_secondes_bucket{le="+Inf"}'] == 4
    assert valeurs['erp_vue_duree_secondes_total{vue="accounts:login"}'] > 0


def test_l_histogramme_est_cumulatif(client):
    for duree in (0.01, 0.3, 3, 30):
        mesures.enregistrer_requete("accounts:login", "GET", 200, duree)

    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs['erp_requete_duree_secondes_bucket{le="0.05"}'] == 1
    assert valeurs['erp_requete_duree_secondes_bucket{le="0.5"}'] == 2
    assert valeurs['erp_requete_duree_secondes_bucket{le="5"}'] == 3
    assert valeurs['erp_requete_duree_secondes_bucket{le="10"}'] == 3
    assert valeurs['erp_requete_duree_secondes_bucket{le="+Inf"}'] == 4
    assert valeurs["erp_requete_duree_secondes_sum"] == pytest.approx(33.31)


def test_les_erreurs_serveur_sont_classees_5xx():
    mesures.enregistrer_requete("accounts:login", "PATCH", 503, 0.1)

    assert 'erp_requetes_total{vue="accounts:login",methode="autre",statut="5xx"} 1' in mesures.exposition()


def test_le_format_est_lisible_par_prometheus(client):
    client.get(reverse("accounts:login"))

    reponse = _lire(client)

    assert reponse["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert reponse["Cache-Control"] == "no-store"
    noms_declares = set()
    for ligne in reponse.content.decode().splitlines():
        if ligne.startswith("# TYPE "):
            _, _, nom, sorte = ligne.split(" ")
            assert sorte in ("counter", "gauge", "histogram") and nom not in noms_declares
            noms_declares.add(nom)
        elif not ligne.startswith("# HELP "):
            assert LIGNE.match(ligne), ligne
    assert {"erp_requetes_total", "erp_requete_duree_secondes", "erp_base_de_donnees_disponible",
            "erp_cache_disponible", "erp_pdf_en_preparation"} <= noms_declares


def test_les_jauges_du_socle(client):
    valeurs = _valeurs(_lire(client).content.decode())

    assert valeurs["erp_base_de_donnees_disponible"] == 1 and valeurs["erp_cache_disponible"] == 1
    assert valeurs["erp_pdf_en_preparation"] == 0
    assert "erp_celery_file_attente" not in valeurs  # pas de courtier en test (tâches exécutées sur place)


def test_une_jauge_en_panne_est_omise_sans_casser_les_autres(client):
    mesures.enregistrer_jauge("erp_essai_en_panne", "Essai.", mock.Mock(side_effect=RuntimeError("panne")))
    try:
        texte = _lire(client).content.decode()
    finally:
        mesures._JAUGES[:] = [j for j in mesures._JAUGES if j[0] != "erp_essai_en_panne"]

    assert "erp_essai_en_panne" not in texte and "erp_base_de_donnees_disponible 1" in texte


def test_une_panne_du_cache_ne_bloque_aucune_requete(client):
    with mock.patch.object(mesures.cache, "incr", side_effect=ConnectionError("Redis arrêté")):
        assert client.get(reverse("accounts:login")).status_code == 200


def test_sans_le_bon_jeton_rien_n_est_publie(client):
    client.force_login(UserFactory(is_superuser=True))  # même connecté en administrateur

    assert _lire(client, jeton=None).status_code == 401
    assert _lire(client, jeton="faux").status_code == 401
    assert b"erp_" not in _lire(client, jeton="faux").content


def test_sans_jeton_configure_l_adresse_n_existe_pas(client, settings):
    settings.METRIQUES_JETON = ""

    assert _lire(client, jeton="").status_code == 404


def test_prometheus_lit_les_mesures_sans_nom_de_domaine_ni_https(client, settings):
    """Prometheus appelle web:8000 en HTTP : ni ALLOWED_HOSTS ni la redirection HTTPS ne doivent l'en empêcher."""
    settings.ALLOWED_HOSTS = ["erp.densourcegroup.ci"]
    settings.SECURE_SSL_REDIRECT = True

    reponse = client.get(mesures.CHEMIN, HTTP_HOST="web:8000", HTTP_AUTHORIZATION=f"Bearer {JETON}")

    assert reponse.status_code == 200 and b"erp_requetes_total" in reponse.content


def test_tous_les_ecrans_sont_connus():
    noms = mesures.noms_des_vues()

    assert "accounts:login" in noms and "home" in noms and "missions:detail" in noms
    assert noms[-2:] == (mesures.SANS_NOM, mesures.AUCUNE)


def test_age_de_la_derniere_sauvegarde(settings):
    maintenant = timezone.now()
    settings.SAUVEGARDES_SURVEILLEES = True
    with mock.patch.object(sauvegardes, "derniere_reussie", return_value={"fin": maintenant - timedelta(hours=3)}):
        assert sauvegardes.age_derniere_sauvegarde(maintenant=maintenant) == 3 * 3600
    with mock.patch.object(sauvegardes, "derniere_reussie", return_value=None):
        assert sauvegardes.age_derniere_sauvegarde() is None
    settings.SAUVEGARDES_SURVEILLEES = False
    assert sauvegardes.age_derniere_sauvegarde() is None


def test_la_jauge_de_sauvegarde_est_enregistree():
    assert "erp_sauvegarde_age_secondes" in [nom for nom, _, _ in mesures._JAUGES]


def test_le_middleware_passe_en_premier():
    assert settings.MIDDLEWARE[0] == "apps.core.mesures.MesuresMiddleware"


def test_nginx_refuse_les_mesures_depuis_internet():
    conf = (RACINE / "nginx/nginx.conf").read_text(encoding="utf-8")

    bloc = conf.split("location ^~ /metriques {", 1)[1].split("}", 1)[0]
    assert "return 404;" in bloc


def test_prometheus_est_configure_et_ses_alertes_portent_sur_des_mesures_publiees():
    compose = yaml.safe_load((RACINE / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["prometheus"]
    assert service["ports"] == ["127.0.0.1:9090:9090"]  # jamais exposé sur Internet
    assert re.fullmatch(r"prom/prometheus:v\d+\.\d+\.\d+", service["image"])  # version figée
    assert "prometheus_data" in compose["volumes"]

    configuration = yaml.safe_load((RACINE / "ops/prometheus.yml").read_text(encoding="utf-8"))
    erp = next(job for job in configuration["scrape_configs"] if job["job_name"] == "erp")
    assert erp["metrics_path"] == mesures.CHEMIN and erp["static_configs"][0]["targets"] == ["web:8000"]
    assert erp["authorization"]["credentials_file"] == "/prometheus/jeton"
    assert "/prometheus/jeton" in " ".join(service["command"])

    alertes = yaml.safe_load((RACINE / "ops/prometheus-alertes.yml").read_text(encoding="utf-8"))
    expressions = " ".join(regle["expr"] for groupe in alertes["groups"] for regle in groupe["rules"])
    publiees = set(re.findall(r"^# TYPE (\S+)", mesures.exposition(), re.M)) | {"erp_celery_file_attente", "erp_sauvegarde_age_secondes", "up"}
    for nom in set(re.findall(r"\b(erp_[a-z_]+|up)\b", expressions)):
        assert re.sub(r"_(bucket|sum|count)$", "", nom) in publiees, nom
