"""Blocs d'affichage enregistrables dans la fiche d'une autre app.

Une fiche (ex. celle d'un camion, app ``fleet``) expose un ``RegistreSections`` ;
les apps situées « en dessous » (ex. ``garage``) y enregistrent un fournisseur de
bloc dans leur ``AppConfig.ready()``. La fiche affiche alors ces blocs sans
jamais importer ces apps (sens des dépendances, architecture.md:161-163).

Un fournisseur reçoit les arguments passés à :meth:`RegistreSections.sections` et
retourne ``{"template": "...", "contexte": {...}}`` ou ``None`` (rien à afficher,
par exemple selon le rôle).
"""

from __future__ import annotations

from typing import Any, Callable

from django.template import TemplateDoesNotExist
from django.template.loader import get_template

Fournisseur = Callable[..., "dict[str, Any] | None"]


class RegistreSections:
    def __init__(self) -> None:
        self._fournisseurs: list[Fournisseur] = []

    def enregistrer(self, fournisseur: Fournisseur) -> None:
        """Ajoute un fournisseur (idempotent : sûr si ``ready()`` est rappelé)."""
        if fournisseur not in self._fournisseurs:
            self._fournisseurs.append(fournisseur)

    def sections(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Blocs à afficher, dans l'ordre d'enregistrement.

        Un bloc dont le gabarit n'existe pas est ignoré : la fiche reste affichable même si l'écran de
        l'app qui fournit ce bloc n'est pas (encore) installé.
        """
        blocs = []
        for fournisseur in self._fournisseurs:
            bloc = fournisseur(*args, **kwargs)
            if not bloc:
                continue
            try:
                get_template(bloc["template"])
            except TemplateDoesNotExist:
                continue
            blocs.append(bloc)
        return blocs
