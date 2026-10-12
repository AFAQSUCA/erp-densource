"""Protection contre la double saisie (double clic, formulaire renvoyé) — audit AUD-06.

Le navigateur n'envoie un formulaire qu'une fois (``static/js/app.js``), mais seule une vérification côté
serveur est sûre : un enregistrement **identique** créé il y a moins de :data:`DELAI_DOUBLON` est refusé. Un
second règlement réel du même montant le même jour reste possible une minute plus tard.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .exceptions import ErreurMetier

DELAI_DOUBLON = timedelta(seconds=60)


def exiger_pas_de_doublon_recent(
    identiques: QuerySet, *, quoi: str, erreur: type[Exception] = ErreurMetier
) -> None:
    """``identiques`` : les enregistrements qui auraient exactement les mêmes valeurs (le modèle a ``created_at``)."""
    if identiques.filter(created_at__gte=timezone.now() - DELAI_DOUBLON).exists():
        raise erreur(
            f"{quoi} identique vient d'être enregistré(e) : saisie en double (double clic) ignorée. "
            "S'il s'agit vraiment d'une seconde opération, recommencez dans une minute."
        )
