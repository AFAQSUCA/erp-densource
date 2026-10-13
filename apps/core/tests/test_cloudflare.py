"""Derrière Cloudflare (cahier-des-charges.md:295 « CDN Cloudflare » ; décision du 13/10/2026, audit TECH-71)."""

import ipaddress
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.core.middleware import get_client_ip

NGINX = Path(settings.BASE_DIR) / "nginx"

# Liste officielle relevée le 13/10/2026 (https://www.cloudflare.com/ips/).
PLAGES_CLOUDFLARE = {
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22", "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
}


def _sans_commentaires(texte: str) -> str:
    return "\n".join(ligne.split("#")[0] for ligne in texte.splitlines())


def _configuration_nginx() -> str:
    return _sans_commentaires((NGINX / "nginx.conf").read_text(encoding="utf-8"))


def test_nginx_ne_croit_la_vraie_adresse_que_venant_de_cloudflare():
    conf = _sans_commentaires((NGINX / "cloudflare-ips.conf").read_text(encoding="utf-8"))
    plages = re.findall(r"set_real_ip_from\s+(\S+);", conf)

    assert set(plages) == PLAGES_CLOUDFLARE
    for plage in plages:
        reseau = ipaddress.ip_network(plage)  # plage valide
        assert reseau.is_global and reseau.prefixlen >= 13  # jamais 0.0.0.0/0 ni un réseau privé
    assert re.search(r"^\s*real_ip_header CF-Connecting-IP;", conf, re.M)
    assert "real_ip_recursive" not in conf  # on prend l'adresse donnée par Cloudflare, rien d'écrit par le client


def test_la_liste_est_incluse_avant_les_limites_et_embarquee_dans_l_image():
    conf = _configuration_nginx()
    http = conf.split("http {", 1)[1]

    assert http.index("include /etc/nginx/cloudflare-ips.conf;") < http.index("limit_req_zone")
    assert "COPY cloudflare-ips.conf /etc/nginx/cloudflare-ips.conf" in (NGINX / "Dockerfile").read_text(encoding="utf-8")


def test_seuls_les_fichiers_statiques_sont_publics_pour_le_cache():
    conf = _configuration_nginx()
    statiques = conf.split("location /static/ {", 1)[1].split("}", 1)[0]

    assert 'add_header Cache-Control "public, max-age=2592000, immutable";' in statiques
    assert conf.count("public") == 1


def test_le_defi_lets_encrypt_est_aussi_servi_en_https():
    https = _configuration_nginx().split("listen 443 ssl;", 1)[1]

    assert "location /.well-known/acme-challenge/ {" in https


def test_le_script_de_mise_a_jour_ne_remplace_la_liste_que_si_elle_est_valide():
    script = (NGINX / "maj-ips-cloudflare.sh").read_text(encoding="utf-8")

    assert "set -eu" in script and "https://www.cloudflare.com/ips-v4" in script and "https://www.cloudflare.com/ips-v6" in script
    assert "liste inattendue" in script and script.index("liste inattendue") < script.index('mv "${TEMP}" "${CIBLE}"')


@pytest.mark.django_db
def test_les_pages_de_l_application_ne_vont_jamais_dans_un_cache_partage(client):
    assert "private" in client.get(reverse("accounts:login"))["Cache-Control"]
    client.force_login(UserFactory(is_superuser=True))
    assert "private" in client.get(reverse("home"))["Cache-Control"]
    assert "private" in client.get(reverse("hr:personnel_imprimer"))["Cache-Control"]


@pytest.mark.django_db
def test_une_politique_de_cache_deja_posee_est_gardee(client):
    """Le service worker du chauffeur garde « no-cache » ; seules les réponses muettes reçoivent « private »."""
    assert client.get(reverse("chauffeur:sw"))["Cache-Control"] == "no-cache"


def test_l_adresse_transmise_par_nginx_est_celle_du_visiteur(rf, settings):
    """Nginx a remplacé l'adresse de Cloudflare par celle du visiteur et l'a ajoutée en fin de X-Forwarded-For :
    Django la lit avec TRUSTED_PROXY_COUNT=1, même si le visiteur a écrit une fausse adresse en tête de liste."""
    settings.TRUSTED_PROXY_COUNT = 1
    requete = rf.get("/", HTTP_X_FORWARDED_FOR="10.9.9.9, 41.202.1.7, 41.202.1.7", REMOTE_ADDR="172.18.0.5")

    assert get_client_ip(requete) == "41.202.1.7"
