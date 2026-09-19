"""Logique métier de la flotte — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS
from apps.core.services import etat_echeance

from apps.drivers.models import Chauffeur

from .exceptions import (
    DocumentInvalide,
    DoublonVehicule,
    KilometrageInvalide,
    VehiculeInvalide,
)
from .models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule


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


# --- fiche véhicule (cahier-des-charges.md:88-90) ---


def vehicules_queryset() -> QuerySet[Vehicule]:
    """Camions avec leur chauffeur habituel chargé (évite les requêtes en boucle)."""
    return Vehicule.objects.select_related("chauffeur_habituel__personnel")


def _normaliser(immatriculation: str, vin: str) -> tuple[str, str]:
    return " ".join(immatriculation.upper().split()), vin.strip().upper()


def _verifier_fiche(
    *,
    immatriculation: str,
    vin: str,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    exclure: Vehicule | None = None,
) -> None:
    if not immatriculation:
        raise VehiculeInvalide("L'immatriculation est obligatoire.")
    if not vin:
        raise VehiculeInvalide("Le n° de châssis (VIN) est obligatoire.")
    if capacite_charge_t <= 0:
        raise VehiculeInvalide("La capacité de charge doit être strictement positive.")
    if reservoir_l <= 0:
        raise VehiculeInvalide("La capacité du réservoir doit être strictement positive.")
    # all_objects : l'unicité en base compte aussi les camions supprimés logiquement.
    autres = Vehicule.all_objects.exclude(pk=exclure.pk if exclure else None)
    if autres.filter(immatriculation=immatriculation).exists():
        raise DoublonVehicule(f"L'immatriculation {immatriculation} est déjà utilisée.")
    if autres.filter(vin=vin).exists():
        raise DoublonVehicule(f"Le n° de châssis {vin} est déjà utilisé.")


@transaction.atomic
def creer_vehicule(
    *,
    immatriculation: str,
    marque: str,
    modele: str,
    annee: int,
    vin: str,
    kilometrage: int,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    chauffeur_habituel: Chauffeur | None = None,
) -> Vehicule:
    """Crée un camion « Disponible ». Immatriculation et VIN sont normalisés
    (majuscules, espaces) pour qu'« ab 123 » et « AB 123 » ne fassent pas deux camions."""
    immatriculation, vin = _normaliser(immatriculation, vin)
    _verifier_fiche(
        immatriculation=immatriculation,
        vin=vin,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
    )
    return Vehicule.objects.create(
        immatriculation=immatriculation,
        marque=marque.strip(),
        modele=modele.strip(),
        annee=annee,
        vin=vin,
        kilometrage=kilometrage,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
        chauffeur_habituel=chauffeur_habituel,
    )


@transaction.atomic
def modifier_vehicule(
    vehicule: Vehicule,
    *,
    immatriculation: str,
    marque: str,
    modele: str,
    annee: int,
    vin: str,
    kilometrage: int,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    chauffeur_habituel: Chauffeur | None = None,
) -> Vehicule:
    """Met à jour la fiche (le statut ne se modifie pas ici : il est calculé).

    Le compteur ne peut pas reculer (cahier-des-charges.md:139)."""
    type(vehicule)._base_manager.select_for_update().filter(pk=vehicule.pk).first()
    vehicule.refresh_from_db()
    immatriculation, vin = _normaliser(immatriculation, vin)
    _verifier_fiche(
        immatriculation=immatriculation,
        vin=vin,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
        exclure=vehicule,
    )
    if kilometrage < vehicule.kilometrage:
        raise KilometrageInvalide(
            f"Le compteur ({vehicule.kilometrage} km) ne peut pas diminuer."
        )
    vehicule.immatriculation = immatriculation
    vehicule.marque = marque.strip()
    vehicule.modele = modele.strip()
    vehicule.annee = annee
    vehicule.vin = vin
    vehicule.kilometrage = kilometrage
    vehicule.capacite_charge_t = capacite_charge_t
    vehicule.reservoir_l = reservoir_l
    vehicule.chauffeur_habituel = chauffeur_habituel
    vehicule.save()
    return vehicule


def rechercher_vehicules(
    *, statut: str | None = None, recherche: str = "", documents_a_renouveler: bool = False
) -> QuerySet[Vehicule]:
    """Camions filtrés par statut, texte (immatriculation, marque, modèle, VIN)
    et/ou présence d'un document à renouveler."""
    vehicules = vehicules_queryset()
    if statut in StatutVehicule.values:
        vehicules = vehicules.filter(statut=statut)
    recherche = recherche.strip()
    if recherche:
        vehicules = vehicules.filter(
            Q(immatriculation__icontains=recherche)
            | Q(marque__icontains=recherche)
            | Q(modele__icontains=recherche)
            | Q(vin__icontains=recherche)
        )
    if documents_a_renouveler:
        vehicules = vehicules.filter(pk__in=vehicules_avec_documents_a_renouveler())
    return vehicules


# --- documents réglementaires (cahier-des-charges.md:93-95) ---


def vehicules_avec_documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> set[int]:
    """Identifiants des camions ayant au moins un document expiré ou expirant."""
    return set(
        documents_a_renouveler(aujourd_hui=aujourd_hui, jours=jours).values_list(
            "vehicule_id", flat=True
        )
    )


@transaction.atomic
def enregistrer_document(
    vehicule: Vehicule,
    *,
    type_document: str,
    date_delivrance: date,
    date_expiration: date,
) -> tuple[DocumentReglementaire, bool]:
    """Enregistre un document ou le renouvelle (un seul actif par type et par camion).

    Un renouvellement met à jour les dates ; l'historique des anciennes dates
    reste dans ``audit_log``. Retourne ``(document, cree)``.
    """
    if type_document not in TypeDocument.values:
        raise DocumentInvalide(f"Type de document inconnu : {type_document!r}")
    if date_expiration < date_delivrance:
        raise DocumentInvalide(
            "La date d'expiration ne peut pas précéder la date de délivrance."
        )
    document = DocumentReglementaire.objects.filter(
        vehicule=vehicule, type_document=type_document
    ).first()
    if document is None:
        document = DocumentReglementaire.objects.create(
            vehicule=vehicule,
            type_document=type_document,
            date_delivrance=date_delivrance,
            date_expiration=date_expiration,
        )
        return document, True
    document.date_delivrance = date_delivrance
    document.date_expiration = date_expiration
    document.save()
    return document, False


def etat_documents(
    vehicule: Vehicule, *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> list[dict]:
    """Situation des 4 documents réglementaires d'un camion, dans l'ordre du CDC.

    ``etat`` : EXPIRE (date dépassée), A_RENOUVELER (échéance dans ``jours``
    jours ou moins), VALIDE, MANQUANT (jamais enregistré).
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    existants = {
        d.type_document: d
        for d in DocumentReglementaire.objects.filter(vehicule=vehicule)
    }
    situation = []
    for code, libelle in TypeDocument.choices:
        document = existants.get(code)
        etat, restants = etat_echeance(
            document.date_expiration if document else None,
            aujourd_hui=aujourd_hui,
            jours=jours,
        )
        situation.append(
            {
                "code": code,
                "libelle": libelle,
                "document": document,
                "etat": etat,
                "jours_restants": restants,
            }
        )
    return situation
