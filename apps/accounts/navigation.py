"""Menu latéral, filtré selon le rôle de l'utilisateur.

Chaque app déclare ses entrées dans ``AppConfig.ready()`` avec
:func:`enregistrer` : ``accounts`` n'importe ainsi aucune app métier
(sens des dépendances, architecture.md:161-163) et une entrée n'existe que si
son écran existe.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class EntreeMenu:
    libelle: str
    url_name: str
    icone: str  # classe FontAwesome, ex. "fa-truck-fast"
    roles: frozenset[str] | None  # None = tous les rôles connectés
    ordre: int = 100


_ENTREES: dict[str, EntreeMenu] = {}


def enregistrer(entree: EntreeMenu) -> None:
    """Ajoute (ou remplace) une entrée : idempotent, sûr si ``ready()`` est rappelé."""
    _ENTREES[entree.url_name] = entree


def entrees_pour(role: str, chemin: str) -> list[dict]:
    """Entrées visibles pour ``role``, triées, avec l'indicateur ``actif``."""
    visibles = sorted(
        (e for e in _ENTREES.values() if e.roles is None or role in e.roles),
        key=lambda e: (e.ordre, e.libelle),
    )
    resultat = []
    for entree in visibles:
        url = reverse(entree.url_name)
        actif = chemin == url if url == "/" else chemin.startswith(url)
        resultat.append(
            {
                "libelle": entree.libelle,
                "url": url,
                "icone": entree.icone,
                "actif": actif,
            }
        )
    return resultat


enregistrer(EntreeMenu("Accueil", "home", "fa-house", None, ordre=0))
