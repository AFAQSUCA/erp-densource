"""Logique métier du garage — cahier-des-charges.md:161-168.

Ouverture d'un OR → camion « En maintenance ». Clôture → recalcul automatique
du statut selon l'algorithme du CDC (cahier-des-charges.md:96-100), dont
``garage`` fournit les deux faits : « d'autres OR ouverts » (lui-même) et
« mission active » (``missions``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.services import prochain_numero
from apps.fleet import services as fleet_services
from apps.fleet.models import StatutVehicule, Vehicule
from apps.missions import services as missions_services

from .exceptions import CoutInvalide, StatutVehiculeInvalide, TransitionOrInterdite
from .models import OrdreReparation, StatutOr, TypeOr, LieuReparation

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


# --- consultation des OR ---


def ordres_queryset() -> QuerySet[OrdreReparation]:
    """OR avec leur camion chargé (évite les requêtes en boucle)."""
    return OrdreReparation.objects.select_related("vehicule")


def rechercher_ordres(
    *,
    statut: str | None = None,
    type_or: str | None = None,
    lieu: str | None = None,
    recherche: str = "",
) -> QuerySet[OrdreReparation]:
    """OR filtrés par statut, type, lieu et texte (n°, immatriculation, motif)."""
    ordres = ordres_queryset()
    if statut in StatutOr.values:
        ordres = ordres.filter(statut=statut)
    if type_or in TypeOr.values:
        ordres = ordres.filter(type_or=type_or)
    if lieu in LieuReparation.values:
        ordres = ordres.filter(lieu=lieu)
    recherche = recherche.strip()
    if recherche:
        ordres = ordres.filter(
            Q(numero__icontains=recherche)
            | Q(vehicule__immatriculation__icontains=recherche)
            | Q(motif__icontains=recherche)
        )
    return ordres


def ordres_du_vehicule(vehicule: Vehicule, *, limite: int = 5) -> QuerySet[OrdreReparation]:
    """Derniers OR d'un camion, du plus récent au plus ancien."""
    return OrdreReparation.objects.filter(vehicule=vehicule).order_by("-numero")[:limite]


# --- immobilisation et remise en service (cahier-des-charges.md:91-92, 96-100) ---


def _refuser_si_mission_active(vehicule: Vehicule, action: str) -> None:
    """Un camion réservé ou en route ne s'immobilise pas : sa mission serait bloquée.

    Une panne en route s'enregistre en ouvrant un OR (statut « En maintenance »)."""
    if missions_services.vehicule_a_mission_active(vehicule):
        raise StatutVehiculeInvalide(
            f"Impossible de {action} : le camion {vehicule.immatriculation} est réservé "
            "ou en route pour une mission. En cas de panne, ouvrez un OR."
        )


@transaction.atomic
def immobiliser_vehicule(vehicule: Vehicule) -> Vehicule:
    """Marque le camion « Immobilisé » (ex. accident, saisie, document expiré)."""
    _verrouiller(vehicule)
    if vehicule.statut == StatutVehicule.IMMOBILISE:
        raise StatutVehiculeInvalide("Ce camion est déjà immobilisé.")
    _refuser_si_mission_active(vehicule, "immobiliser")
    return fleet_services.definir_statut(vehicule, StatutVehicule.IMMOBILISE)


@transaction.atomic
def mettre_hors_service(vehicule: Vehicule) -> Vehicule:
    """Marque le camion « Hors service » (réforme, épave)."""
    _verrouiller(vehicule)
    if vehicule.statut == StatutVehicule.HORS_SERVICE:
        raise StatutVehiculeInvalide("Ce camion est déjà hors service.")
    _refuser_si_mission_active(vehicule, "mettre hors service")
    return fleet_services.definir_statut(vehicule, StatutVehicule.HORS_SERVICE)


@transaction.atomic
def remettre_en_service(vehicule: Vehicule) -> Vehicule:
    """Sort un camion d'« Immobilisé » ou « Hors service » et recalcule son statut.

    La règle 3 du CDC conserve ces deux statuts tant qu'on ne les lève pas : on
    repart donc de « Disponible », puis l'algorithme complet s'applique (OR
    ouvert → En maintenance, mission → En mission, sinon Disponible).
    """
    _verrouiller(vehicule)
    if vehicule.statut not in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE):
        raise StatutVehiculeInvalide(
            "Seul un camion immobilisé ou hors service peut être remis en service."
        )
    fleet_services.definir_statut(vehicule, StatutVehicule.DISPONIBLE)
    return fleet_services.recalculer_statut(
        vehicule,
        or_ouverts=vehicule_a_or_ouvert(vehicule),
        mission_active=missions_services.vehicule_a_mission_active(vehicule),
    )
