"""Mesures techniques pour Prometheus (cahier-des-charges.md:256 ; décision du 13/10/2026, audit TECH-24).

Sans dépendance : l'application écrit elle-même le format texte que lit Prometheus.

- **Requêtes** (:class:`MesuresMiddleware`, en tête de ``MIDDLEWARE``) : nombre par écran, méthode et classe de
  statut (``2xx``... ``5xx``), temps passé par écran, histogramme global des temps de réponse. Les compteurs sont
  dans le cache (Redis en production) : partagés entre les processus Gunicorn, qui sinon compteraient chacun de leur
  côté. Une panne du cache ne bloque jamais une requête : la mesure est simplement perdue.
- **Jauges**, calculées à chaque lecture : base de données et cache joignables, file d'attente Celery, PDF en
  préparation ; d'autres apps ajoutent les leurs (:func:`enregistrer_jauge`, ex. âge de la dernière sauvegarde).

Lecture : ``GET /metriques/`` avec ``Authorization: Bearer <METRIQUES_JETON>``. Sans jeton configuré, l'adresse
n'existe pas ; Nginx la refuse de toute façon depuis l'extérieur (nginx/nginx.conf). Le middleware répond avant
tout le reste : Prometheus appelle ``web:8000`` en HTTP sur le réseau interne, sans passer par le contrôle du nom de
domaine (ALLOWED_HOSTS) ni la redirection HTTPS.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.urls import URLPattern, URLResolver, get_resolver

logger = logging.getLogger(__name__)

CHEMIN = "/metriques/"
PREFIXE = "mesures"
METHODES = ("GET", "POST", "autre")
STATUTS = ("1xx", "2xx", "3xx", "4xx", "5xx")
SEUILS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)  # secondes ; le CDC vise < 500 ms et < 2 s
SANS_NOM = "sans_nom"  # écran sans nom d'URL
AUCUNE = "aucune"  # adresse inconnue (404 avant tout écran)

_JAUGES: list[tuple[str, str, Callable[[], float | None]]] = []


def enregistrer_jauge(nom: str, aide: str, fonction: Callable[[], float | None]) -> None:
    """Ajoute une jauge, calculée à chaque lecture ; ``None`` = valeur indisponible, la ligne est omise."""
    if all(existant != nom for existant, _, _ in _JAUGES):
        _JAUGES.append((nom, aide, fonction))


# --- compteurs ---


def _incrementer(cle: str, valeur: int = 1) -> None:
    try:
        cache.incr(cle, valeur)
    except ValueError:  # première fois : la clé n'existe pas encore
        cache.add(cle, 0, timeout=None)
        cache.incr(cle, valeur)


def _cle_requetes(vue: str, methode: str, statut: str) -> str:
    return f"{PREFIXE}:req:{vue}:{methode}:{statut}"


def _cle_duree(vue: str) -> str:
    return f"{PREFIXE}:duree_ms:{vue}"


def _cle_seuil(indice: int) -> str:
    return f"{PREFIXE}:seuil:{indice}"


def enregistrer_requete(vue: str, methode: str, code: int, duree: float) -> None:
    methode = methode if methode in METHODES else "autre"
    statut = f"{code // 100}xx" if 100 <= code < 600 else "5xx"
    indice = next((i for i, seuil in enumerate(SEUILS) if duree <= seuil), len(SEUILS))
    try:
        _incrementer(_cle_requetes(vue, methode, statut))
        _incrementer(_cle_duree(vue), round(duree * 1000))
        _incrementer(_cle_seuil(indice))
    except Exception:  # le cache ne doit jamais faire échouer une requête
        logger.debug("Mesure perdue (cache indisponible)", exc_info=True)


@lru_cache(maxsize=1)
def noms_des_vues() -> tuple[str, ...]:
    """Tous les noms d'écran possibles (``espace:nom``) : les compteurs se relisent sans liste des clés existantes."""
    noms = set()

    def parcourir(motifs, prefixe=""):
        for motif in motifs:
            if isinstance(motif, URLResolver):
                parcourir(motif.url_patterns, f"{prefixe}{motif.namespace}:" if motif.namespace else prefixe)
            elif isinstance(motif, URLPattern) and motif.name:
                noms.add(f"{prefixe}{motif.name}")

    parcourir(get_resolver().url_patterns)
    return tuple(sorted(noms)) + (SANS_NOM, AUCUNE)


# --- jauges du socle ---


def _base_disponible() -> float:
    try:
        with connection.cursor() as curseur:
            curseur.execute("SELECT 1")
        return 1
    except Exception:
        return 0


def _cache_disponible() -> float:
    try:
        cache.set(f"{PREFIXE}:sonde", 1, timeout=60)
        return 1 if cache.get(f"{PREFIXE}:sonde") == 1 else 0
    except Exception:
        return 0


def _file_celery() -> float | None:
    """Tâches en attente dans la file Celery par défaut (Redis) ; rien sans courtier (développement)."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return None
    try:
        from celery import current_app

        with current_app.connection_for_write() as connexion:
            return connexion.default_channel.client.llen(current_app.conf.task_default_queue or "celery")
    except Exception:
        return None


def _pdf_en_preparation() -> float:
    from .models import DocumentPdf, StatutDocumentPdf

    return DocumentPdf.objects.filter(statut=StatutDocumentPdf.EN_ATTENTE).count()


enregistrer_jauge("erp_base_de_donnees_disponible", "1 si la base de données répond, 0 sinon.", _base_disponible)
enregistrer_jauge("erp_cache_disponible", "1 si le cache (Redis) répond, 0 sinon.", _cache_disponible)
enregistrer_jauge("erp_celery_file_attente", "Tâches Celery en attente d'un worker.", _file_celery)
enregistrer_jauge("erp_pdf_en_preparation", "PDF demandés, pas encore prêts (tâche de fond).", _pdf_en_preparation)


# --- format texte de Prometheus ---


def _echapper(valeur: str) -> str:
    return valeur.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _nombre(valeur: float) -> str:
    return str(int(valeur)) if float(valeur).is_integer() else repr(float(valeur))


def exposition() -> str:
    """Toutes les mesures, au format texte de Prometheus (version 0.0.4)."""
    vues = noms_des_vues()
    cles_requetes = {
        _cle_requetes(v, m, s): (v, m, s) for v in vues for m in METHODES for s in STATUTS
    }
    cles_durees = {_cle_duree(v): v for v in vues}
    cles_seuils = [_cle_seuil(i) for i in range(len(SEUILS) + 1)]
    try:
        valeurs = cache.get_many([*cles_requetes, *cles_durees, *cles_seuils])
    except Exception:
        valeurs = {}

    lignes = [
        "# HELP erp_requetes_total Requêtes traitées, par écran, méthode et classe de statut.",
        "# TYPE erp_requetes_total counter",
    ]
    for cle, (vue, methode, statut) in cles_requetes.items():
        if cle in valeurs:
            lignes.append(
                f'erp_requetes_total{{vue="{_echapper(vue)}",methode="{methode}",statut="{statut}"}} {valeurs[cle]}'
            )

    lignes += [
        "# HELP erp_vue_duree_secondes_total Temps total passé dans chaque écran (moyenne = rapport au nombre de requêtes).",
        "# TYPE erp_vue_duree_secondes_total counter",
    ]
    somme_ms = 0
    for cle, vue in cles_durees.items():
        if cle in valeurs:
            somme_ms += valeurs[cle]
            lignes.append(f'erp_vue_duree_secondes_total{{vue="{_echapper(vue)}"}} {_nombre(valeurs[cle] / 1000)}')

    lignes += [
        "# HELP erp_requete_duree_secondes Temps de réponse des requêtes.",
        "# TYPE erp_requete_duree_secondes histogram",
    ]
    cumul = 0
    for indice, cle in enumerate(cles_seuils):
        cumul += valeurs.get(cle, 0)
        borne = "+Inf" if indice == len(SEUILS) else _nombre(SEUILS[indice])
        lignes.append(f'erp_requete_duree_secondes_bucket{{le="{borne}"}} {cumul}')
    lignes.append(f"erp_requete_duree_secondes_sum {_nombre(somme_ms / 1000)}")
    lignes.append(f"erp_requete_duree_secondes_count {cumul}")

    for nom, aide, fonction in _JAUGES:
        try:
            valeur = fonction()
        except Exception:
            logger.warning("Jauge %s indisponible", nom, exc_info=True)
            valeur = None
        if valeur is not None:
            lignes += [f"# HELP {nom} {aide}", f"# TYPE {nom} gauge", f"{nom} {_nombre(valeur)}"]
    return "\n".join(lignes) + "\n"


def _jeton_valide(request) -> bool:
    attendu = settings.METRIQUES_JETON
    entete = request.META.get("HTTP_AUTHORIZATION", "")
    return bool(attendu) and entete.startswith("Bearer ") and hmac.compare_digest(entete[7:].encode(), attendu.encode())


class MesuresMiddleware:
    """Compte chaque requête et sert ``/metriques/`` ; à placer en premier dans ``MIDDLEWARE``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == CHEMIN and settings.METRIQUES_JETON:
            if not _jeton_valide(request):
                reponse = HttpResponse("Jeton manquant ou invalide.\n", status=401, content_type="text/plain")
                reponse["WWW-Authenticate"] = 'Bearer realm="metriques"'
                return reponse
            reponse = HttpResponse(exposition(), content_type="text/plain; version=0.0.4; charset=utf-8")
            reponse["Cache-Control"] = "no-store"
            return reponse

        debut = time.perf_counter()
        reponse = self.get_response(request)
        correspondance = getattr(request, "resolver_match", None)
        if correspondance is None:
            vue = AUCUNE
        else:
            vue = correspondance.view_name if correspondance.url_name else SANS_NOM
        enregistrer_requete(vue, request.method, reponse.status_code, time.perf_counter() - debut)
        return reponse
