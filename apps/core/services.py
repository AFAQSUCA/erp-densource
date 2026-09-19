"""Services transverses."""

from django.db import transaction
from django.utils import timezone

from .models import CompteurNumero


@transaction.atomic
def prochain_numero(prefixe: str, annee: int | None = None) -> str:
    """Numéro suivant au format ``PREFIXE-ANNEE-0001`` (remis à 1 chaque année).

    Formats du CDC : ``MIS-2026-XXXX`` (cahier-des-charges.md:129),
    ``OR-2026-XXXX`` (:165), ``FACT-2026-XXXX`` (:183).

    ``get_or_create`` puis verrou de ligne : deux appels simultanés ne
    peuvent pas obtenir le même numéro (verrou effectif sous PostgreSQL).
    """
    annee = annee or timezone.localdate().year
    compteur, _ = CompteurNumero.objects.get_or_create(prefixe=prefixe, annee=annee)
    compteur = CompteurNumero.objects.select_for_update().get(pk=compteur.pk)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])
    return f"{prefixe}-{annee}-{compteur.dernier:04d}"
