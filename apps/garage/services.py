"""Logique métier du garage — cahier-des-charges.md:161-168.

Ouverture d'un OR → camion « En maintenance ». Clôture → recalcul automatique
du statut selon l'algorithme du CDC (cahier-des-charges.md:96-100), dont
``garage`` fournit les deux faits : « d'autres OR ouverts » (lui-même) et
« mission active » (``missions``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.services import prochain_numero
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule, Vehicule
from apps.missions import services as missions_services

from .exceptions import CoutInvalide, TransitionOrInterdite
from .models import OrdreReparation, StatutOr

PREFIXE_NUMERO = "OR"


def vehicule_a_or_ouvert(vehicule: Vehicule) -> bool:
    """Vrai si au moins un OR ouvert existe pour ce camion."""
    return OrdreReparation.objects.filter(
        vehicule=vehicule, statut=StatutOr.OUVERT
    ).exists()


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


@transaction.atomic
def ouvrir_or(
    vehicule: Vehicule, *, type_or: str, lieu: str, motif: str
) -> OrdreReparation:
    """Ouvre un OR (numéro OR-AAAA-XXXX) et passe le camion « En maintenance ».

    Autorisé même si le camion est en mission : c'est le cas d'une panne en
    route. La mission continue ; le statut sera recalculé à la clôture.
    """
    _verrouiller(vehicule)
    ordre = OrdreReparation.objects.create(
        numero=prochain_numero(PREFIXE_NUMERO),
        vehicule=vehicule,
        type_or=type_or,
        lieu=lieu,
        motif=motif,
    )
    fleet_services.definir_statut(vehicule, StatutVehicule.EN_MAINTENANCE)
    return ordre


@transaction.atomic
def cloturer_or(
    ordre: OrdreReparation, *, cout_main_oeuvre: Decimal = Decimal("0")
) -> OrdreReparation:
    """Clôture l'OR, enregistre la main-d'œuvre et recalcule le statut du camion.

    Recalcul (cahier-des-charges.md:96-100) : d'autres OR ouverts → En
    maintenance ; sinon mission affectée/en cours → En mission ; sinon
    Immobilisé / Hors service conservé ; sinon Disponible.
    """
    if cout_main_oeuvre < 0:
        raise CoutInvalide("Le coût de la main-d'œuvre ne peut pas être négatif.")
    _verrouiller(ordre)
    if ordre.statut != StatutOr.OUVERT:
        raise TransitionOrInterdite(f"L'OR {ordre.numero} est déjà clôturé.")
    vehicule = _verrouiller(ordre.vehicule)

    ordre.statut = StatutOr.CLOTURE
    ordre.date_cloture = timezone.now()
    ordre.cout_main_oeuvre = cout_main_oeuvre
    ordre.save(
        update_fields=["statut", "date_cloture", "cout_main_oeuvre", "updated_at"]
    )

    fleet_services.recalculer_statut(
        vehicule,
        or_ouverts=vehicule_a_or_ouvert(vehicule),
        mission_active=missions_services.vehicule_a_mission_active(vehicule),
    )
    return ordre
