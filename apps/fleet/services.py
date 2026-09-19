"""Logique métier de la flotte — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS

from .models import DocumentReglementaire, StatutVehicule, Vehicule


def vehicules_disponibles() -> QuerySet[Vehicule]:
    """Camions au statut « Disponible », pour l'affectation d'une mission."""
    return Vehicule.objects.filter(statut=StatutVehicule.DISPONIBLE).order_by(
        "immatriculation"
    )


def calculer_statut(
    statut_actuel: str, *, or_ouverts: bool, mission_active: bool
) -> str:
    """Statut d'un camion selon l'algorithme du CDC (cahier-des-charges.md:96-100).

    Ordre strict des règles :
      1. d'autres OR ouverts            → En maintenance
      2. mission planifiée / en cours   → En mission
      3. marqué Immobilisé / Hors service → conservé
      4. sinon                          → Disponible

    Fonction pure : ``garage`` et ``missions`` (apps situées sous ``fleet``
    dans architecture.md:161-163) calculent ``or_ouverts`` et
    ``mission_active`` et les passent en paramètre, ``fleet`` n'a donc
    jamais à les importer.
    """
    if or_ouverts:
        return StatutVehicule.EN_MAINTENANCE
    if mission_active:
        return StatutVehicule.EN_MISSION
    if statut_actuel in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE):
        return statut_actuel
    return StatutVehicule.DISPONIBLE


def recalculer_statut(
    vehicule: Vehicule, *, or_ouverts: bool, mission_active: bool
) -> Vehicule:
    """Applique :func:`calculer_statut` et enregistre le résultat."""
    vehicule.statut = calculer_statut(
        vehicule.statut, or_ouverts=or_ouverts, mission_active=mission_active
    )
    vehicule.save(update_fields=["statut", "updated_at"])
    return vehicule


def definir_statut(vehicule: Vehicule, statut: str) -> Vehicule:
    """Change le statut manuellement (ex. Immobilisé, Hors service)."""
    if statut not in StatutVehicule.values:
        raise ValueError(f"Statut véhicule inconnu : {statut!r}")
    vehicule.statut = statut
    vehicule.save(update_fields=["statut", "updated_at"])
    return vehicule


def liberer_apres_mission(vehicule: Vehicule) -> Vehicule:
    """Fin de mission : « En mission » → « Disponible » (cahier-des-charges.md:139).

    Un camion passé entre-temps en maintenance, immobilisé ou hors service
    garde ce statut : seule la mission le libérait, pas le reste.
    """
    if vehicule.statut == StatutVehicule.EN_MISSION:
        return definir_statut(vehicule, StatutVehicule.DISPONIBLE)
    return vehicule


def enregistrer_kilometrage(vehicule: Vehicule, kilometrage: int) -> Vehicule:
    """Met à jour le compteur ; il ne peut jamais reculer (cahier-des-charges.md:139)."""
    if kilometrage < vehicule.kilometrage:
        raise ValueError("Le kilométrage ne peut pas diminuer.")
    vehicule.kilometrage = kilometrage
    vehicule.save(update_fields=["kilometrage", "updated_at"])
    return vehicule


def documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> QuerySet[DocumentReglementaire]:
    """Documents expirant d'ici ``jours`` jours, ou déjà expirés.

    Alimente l'alerte préventive à 30 jours (cahier-des-charges.md:95) et le
    centre d'alertes du tableau de bord (cahier-des-charges.md:231-232).
    """
    limite = (aujourd_hui or timezone.localdate()) + timedelta(days=jours)
    return DocumentReglementaire.objects.select_related("vehicule").filter(
        date_expiration__lte=limite
    )
