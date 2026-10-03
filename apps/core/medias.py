"""Fichiers téléversés (devis, justificatifs) : servis par l'application, jamais en accès libre.

Chaque app qui stocke des fichiers déclare le préfixe de son ``upload_to`` et les rôles autorisés à les
lire (``enregistrer_media``). Un fichier dont le préfixe n'est déclaré nulle part n'est servi à personne.
En production, Django ne lit pas le fichier : il répond ``X-Accel-Redirect`` et Nginx l'envoie depuis un
emplacement interne (``MEDIA_ACCEL_REDIRECT``), inaccessible directement depuis l'extérieur.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join
from django.views import View

_PREFIXES: dict[str, frozenset[str]] = {}

# Types affichés dans le navigateur ; tout le reste (HTML, SVG...) est téléchargé, jamais exécuté.
TYPES_AFFICHABLES = frozenset({"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"})


def enregistrer_media(prefixe: str, roles: Iterable[str]) -> None:
    _PREFIXES[prefixe.strip("/") + "/"] = frozenset(roles)


class MediaProtegeView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, chemin):
        # Le rôle se contrôle sur le préfixe : un « .. » permettrait d'en sortir tout en restant dans MEDIA_ROOT.
        segments = chemin.replace("\\", "/").split("/")
        if "\0" in chemin or any(s in ("", ".", "..") for s in segments):
            raise Http404
        roles = next((r for prefixe, r in _PREFIXES.items() if chemin.startswith(prefixe)), None)
        if roles is None or request.user.role_effectif not in roles:
            raise Http404
        try:
            fichier = safe_join(settings.MEDIA_ROOT, chemin)
        except SuspiciousFileOperation:
            raise Http404
        type_mime = mimetypes.guess_type(fichier)[0] or "application/octet-stream"
        affichable = type_mime in TYPES_AFFICHABLES
        if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
            reponse = HttpResponse(content_type=type_mime)
            reponse["X-Accel-Redirect"] = "/medias-internes/" + chemin
            reponse["Content-Disposition"] = _disposition(affichable, chemin)
        else:
            try:
                reponse = FileResponse(open(fichier, "rb"), content_type=type_mime)
            except (FileNotFoundError, IsADirectoryError):
                raise Http404
            reponse["Content-Disposition"] = _disposition(affichable, chemin)
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, no-store"
        return reponse


def _disposition(affichable: bool, chemin: str) -> str:
    nom = chemin.rsplit("/", 1)[-1].replace('"', "")
    return f'{"inline" if affichable else "attachment"}; filename="{nom}"'
