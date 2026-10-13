"""Limitation des essais de connexion et de double authentification (anti force brute).

Cahier-des-charges.md:277 « Rate limiting anti force brute ». Les compteurs vivent dans le cache
Django (Redis en production, partagé entre les processus ; en mémoire locale en développement).
Chaque compteur porte sa propre fenêtre : dès que le plafond est atteint, l'accès reste refusé
jusqu'à la fin de la fenêtre, même avec le bon mot de passe. Cette couche complète celle du
serveur web (Nginx, étape 7 lot 3) et ne la remplace pas.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time

from django.conf import settings
from django.core.cache import cache

from apps.core.middleware import get_client_ip

logger = logging.getLogger(__name__)


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.strip().lower().encode("utf-8")).hexdigest()[:32]


def _cle_compte(request, identifiant: str) -> str:
    return f"throttle:login:{get_client_ip(request)}:{_empreinte(identifiant or '')}"


def _cle_adresse(request) -> str:
    return f"throttle:login-ip:{get_client_ip(request)}"


def _cle_mfa(utilisateur) -> str:
    return f"throttle:mfa:{utilisateur.pk}"


# Cache (Redis) en panne : les compteurs ne bloquent plus rien, plutôt que d'empêcher toute connexion au site
# (erreur 500). La limite de débit de Nginx sur les pages d'authentification continue de freiner la force brute ;
# la panne est signalée dans les journaux (audit TECH-65).


def _cache_get(cle: str):
    try:
        return cache.get(cle)
    except Exception:
        logger.error("Cache indisponible : limitation des essais suspendue.", exc_info=True)
        return None


def _cache_set(cle: str, valeur, timeout: int) -> None:
    try:
        cache.set(cle, valeur, timeout=timeout)
    except Exception:
        logger.error("Cache indisponible : limitation des essais suspendue.", exc_info=True)


def _cache_delete(cle: str) -> None:
    try:
        cache.delete(cle)
    except Exception:
        logger.error("Cache indisponible : limitation des essais suspendue.", exc_info=True)


def _incrementer(cle: str, fenetre: int) -> None:
    maintenant = time.time()
    etat = _cache_get(cle)
    if etat is None or etat[1] <= maintenant:
        etat = (0, maintenant + fenetre)
    etat = (etat[0] + 1, etat[1])
    _cache_set(cle, etat, timeout=max(1, math.ceil(etat[1] - maintenant)))


def _secondes_restantes(cle: str, plafond: int) -> int:
    etat = _cache_get(cle)
    if etat is None:
        return 0
    reste = etat[1] - time.time()
    if etat[0] >= plafond and reste > 0:
        return math.ceil(reste)
    return 0


# --- connexion par mot de passe ---


def connexion_secondes_restantes(request, identifiant: str) -> int:
    """Secondes avant de pouvoir réessayer ; 0 si la connexion n'est pas bloquée."""
    return max(
        _secondes_restantes(_cle_compte(request, identifiant), settings.LOGIN_MAX_ECHECS_COMPTE),
        _secondes_restantes(_cle_adresse(request), settings.LOGIN_MAX_ECHECS_ADRESSE),
    )


def connexion_enregistrer_echec(request, identifiant: str) -> None:
    _incrementer(_cle_compte(request, identifiant), settings.LOGIN_FENETRE)
    _incrementer(_cle_adresse(request), settings.LOGIN_FENETRE)


def connexion_reinitialiser(request, identifiant: str) -> None:
    """Une connexion réussie efface les échecs du couple (adresse, identifiant), pas ceux de l'adresse."""
    _cache_delete(_cle_compte(request, identifiant))


# --- mot de passe oublié (audit TECH-46) ---


def _cles_reinitialisation(request, email: str) -> list[tuple[str, int]]:
    return [
        (f"throttle:reset-ip:{get_client_ip(request)}", settings.REINITIALISATION_MAX_PAR_ADRESSE),
        (f"throttle:reset-email:{_empreinte(email or '')}", settings.REINITIALISATION_MAX_PAR_EMAIL),
    ]


def reinitialisation_secondes_restantes(request, email: str) -> int:
    """Secondes avant de pouvoir redemander un lien ; 0 si la demande est permise. Chaque demande compte, que
    l'adresse ait un compte ou non (la réponse ne doit jamais le révéler)."""
    return max(_secondes_restantes(cle, plafond) for cle, plafond in _cles_reinitialisation(request, email))


def reinitialisation_enregistrer(request, email: str) -> None:
    for cle, _plafond in _cles_reinitialisation(request, email):
        _incrementer(cle, settings.REINITIALISATION_FENETRE)


# --- double authentification ---


def mfa_secondes_restantes(utilisateur) -> int:
    return _secondes_restantes(_cle_mfa(utilisateur), settings.MFA_MAX_ECHECS)


def mfa_enregistrer_echec(utilisateur) -> None:
    _incrementer(_cle_mfa(utilisateur), settings.MFA_FENETRE)


def mfa_reinitialiser(utilisateur) -> None:
    _cache_delete(_cle_mfa(utilisateur))


def phrase_attente(secondes: int) -> str:
    """« 1 minute » / « 4 minutes » : arrondi vers le haut, en français."""
    minutes = max(1, math.ceil(secondes / 60))
    return f"{minutes} minute{'s' if minutes > 1 else ''}"
