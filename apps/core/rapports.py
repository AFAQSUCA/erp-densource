"""Aides communes aux rapports imprimables (trésorerie, tableau de bord, listes, journal d'audit).

Chaque rapport est une page HTML autonome (pas `base.html` : pas de menu ni de barre latérale dans le
tirage), avec le bouton « Imprimer » (`data-imprimer`, voir `static/js/app.js`) qui ouvre l'impression du
navigateur — l'utilisateur choisit « Enregistrer au format PDF » ou une imprimante. Même mécanisme que
`billing.facture_print` ; ce module en généralise l'en-tête pour ne pas le récrire à chaque rapport.

Le seul cas qui a besoin d'une mise en page pixel-près (document envoyé à un tiers) reste
`apps.missions.documents` (ReportLab) ; un rapport interne n'en a pas besoin.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone


def contexte_entreprise() -> dict:
    return {
        "nom": settings.ENTREPRISE_NOM,
        "adresse": settings.ENTREPRISE_ADRESSE,
        "ncc": settings.ENTREPRISE_NCC,
    }


def contexte_rapport(request, *, titre: str, sous_titre: str = "") -> dict:
    """Contexte commun à tout gabarit de `templates/rapports/` : en-tête entreprise, titre, généré le/par."""
    utilisateur = request.user
    return {
        "entreprise": contexte_entreprise(),
        "titre": titre,
        "sous_titre": sous_titre,
        "genere_par": utilisateur.get_full_name() or utilisateur.get_username(),
        "genere_le": timezone.now(),
    }
