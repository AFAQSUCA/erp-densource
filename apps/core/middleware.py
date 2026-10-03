import logging
import threading

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .exceptions import ErreurMetier

logger = logging.getLogger(__name__)

_local = threading.local()


class CurrentRequestMiddleware:
    """Stocke la requête courante en thread-local.

    Permet aux signaux ``post_save``/``post_delete`` (déclenchés hors du
    cycle requête/réponse classique, ex. tâches Celery) d'accéder à
    l'utilisateur, l'IP et le user-agent pour alimenter ``audit_log``
    (ADR-003, architecture.md:488-493) sans coupler chaque modèle au
    framework de requêtes HTTP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


class ErreurMetierMiddleware:
    """Filet de sécurité : une erreur métier non interceptée par son écran devient un message.

    L'opération est déjà annulée (les services sont atomiques). L'utilisateur revient à la page d'où
    il vient avec le message de l'erreur, au lieu d'une erreur 500. L'API a son propre gestionnaire
    (``apps.api.exceptions``) et n'est pas concernée.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, ErreurMetier) or request.path.startswith("/api/"):
            return None
        origine = request.META.get("HTTP_REFERER", "")
        if not url_has_allowed_host_and_scheme(
            origine, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            origine = ""
        # Un GET qui échoue ne doit pas se renvoyer vers lui-même (boucle de redirections).
        if request.method == "GET" and (not origine or origine.split("?")[0].endswith(request.path)):
            return None
        logger.warning("Erreur métier non interceptée sur %s : %s", request.path, exception)
        messages.error(request, str(exception))
        return redirect(origine or "/")


def get_current_request():
    return getattr(_local, "request", None)


def get_current_user():
    request = get_current_request()
    if request is not None and request.user.is_authenticated:
        return request.user
    return None


def get_client_ip(request):
    """Adresse du client, sans se laisser tromper par un en-tête forgé.

    ``X-Forwarded-For`` est écrit par le client aussi bien que par les proxys : le lire aveuglément
    permettrait de prendre n'importe quelle adresse (et d'échapper à la limitation d'essais).
    On ne l'utilise donc que si ``TRUSTED_PROXY_COUNT`` proxys de confiance sont déclarés, et on
    prend l'adresse ajoutée par le dernier d'entre eux (en partant de la fin de la liste).
    """
    proxys = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxys > 0:
        adresses = [
            a.strip() for a in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()
        ]
        if len(adresses) >= proxys:
            return adresses[-proxys]
    return request.META.get("REMOTE_ADDR")


class SecurityHeadersMiddleware:
    """Ajoute la politique de sécurité du contenu (CSP) et la politique des fonctions du navigateur.

    Les autres en-têtes (HSTS, X-Frame-Options, nosniff, Referrer-Policy) sont posés par Django
    (``SecurityMiddleware``, ``XFrameOptionsMiddleware``) selon les réglages de ``settings``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        nom = (
            "Content-Security-Policy-Report-Only"
            if settings.CSP_REPORT_ONLY
            else "Content-Security-Policy"
        )
        politique = settings.CSP_DOCS if request.path.startswith("/api/v1/docs/") else settings.CSP
        if nom not in reponse:
            reponse[nom] = politique
        if "Permissions-Policy" not in reponse:
            reponse["Permissions-Policy"] = settings.PERMISSIONS_POLICY
        return reponse
