"""Porte de la double authentification : refus par défaut tant que la MFA n'est pas passée.

Un ADMIN ou une DIRECTION qui vient de saisir son mot de passe est connecté, mais sa session n'est
pas « vérifiée » : toute page, hors quelques exceptions, le renvoie vers la saisie du code (ou vers
l'activation de la MFA s'il n'a pas encore d'application). Comme la règle est un refus par défaut
appliqué à chaque requête, elle couvre aussi l'espace d'administration et la documentation de l'API,
sans que chaque vue ait à y penser.

Les requêtes de l'API authentifiées par jeton (JWT) ne passent pas ici : la MFA y est contrôlée à
l'émission du jeton (``apps.api.auth``).
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from . import mfa

# Pages accessibles avant la vérification : la MFA elle-même, la connexion et la déconnexion.
_PREFIXES_LIBRES = ("/mfa/", "/connexion/", "/deconnexion/")
# Pages de l'API ouvertes dans un navigateur (documentation) : redirigées, comme le reste du site.
_PAGES_API_NAVIGATEUR = ("/api/v1/docs/", "/api/v1/schema/")


class MFARequiseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = request.user
        if (
            mfa.mfa_requise(utilisateur)
            and not mfa.est_verifiee(request)
            and not self._est_libre(request.path)
        ):
            if request.path.startswith("/api/") and not request.path.startswith(_PAGES_API_NAVIGATEUR):
                return JsonResponse(
                    {"code": "mfa_requise", "detail": "Double authentification requise."}, status=403
                )
            page = "accounts:mfa_verifier" if mfa.appareil_actif(utilisateur) else "accounts:mfa_activer"
            cible = reverse(page)
            if request.method == "GET":
                cible += f"?next={quote(request.get_full_path(), safe='/')}"
            return redirect(cible)
        return self.get_response(request)

    @staticmethod
    def _est_libre(chemin: str) -> bool:
        return chemin.startswith(_PREFIXES_LIBRES) or chemin.startswith(settings.STATIC_URL)
