"""Logique métier de la flotte — conventions.md §2."""

from __future__ import annotations

import re
from datetime import date, timedelta

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from apps.audit import services as audit_services
from apps.audit.models import ActionChoices
from apps.core.search import filtrer_par_texte
from apps.core.services import etat_echeance

from apps.drivers.models import Chauffeur
from apps.parametres import services as parametres_services

from . import permissions
from .exceptions import (
    ActionNonAutorisee,
    DocumentInvalide,
    DoublonVehicule,
    KilometrageInvalide,
    VehiculeInvalide,
)
from .models import MARQUAGES, DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule


def vehicules_disponibles() -> QuerySet[Vehicule]:
    """Camions au statut « Disponible », pour l'affectation d'une mission."""
    return Vehicule.objects.filter(statut=StatutVehicule.DISPONIBLE).order_by(
        "immatriculation"
    )


def calculer_statut(
    statut_actuel: str, *, or_ouverts: bool, mission_active: bool, marquage: str = ""
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
    jamais à les importer. ``marquage`` : l'étiquette Immobilisé / Hors service
    posée à la main (``Vehicule.marquage``), qui survit à un passage « En
    maintenance » ; à défaut, un statut actuel Immobilisé / Hors service en tient lieu.
    """
    if or_ouverts:
        return StatutVehicule.EN_MAINTENANCE
    if mission_active:
        return StatutVehicule.EN_MISSION
    marque = marquage or (statut_actuel if statut_actuel in MARQUAGES else "")
    if marque:
        return marque
    return StatutVehicule.DISPONIBLE


def recalculer_statut(
    vehicule: Vehicule, *, or_ouverts: bool, mission_active: bool
) -> Vehicule:
    """Applique :func:`calculer_statut` et enregistre le résultat."""
    vehicule.statut = calculer_statut(
        vehicule.statut, or_ouverts=or_ouverts, mission_active=mission_active, marquage=vehicule.marquage
    )
    vehicule.save(update_fields=["statut", "updated_at"])
    return vehicule


def definir_statut(vehicule: Vehicule, statut: str) -> Vehicule:
    """Change le statut manuellement. Immobilisé / Hors service posent aussi le marquage, qui survivra à un
    passage « En maintenance » (règle 3 du CDC) jusqu'à :func:`lever_marquage`."""
    if statut not in StatutVehicule.values:
        raise ValueError(f"Statut véhicule inconnu : {statut!r}")
    vehicule.statut = statut
    champs = ["statut", "updated_at"]
    if statut in MARQUAGES:
        vehicule.marquage = statut
        champs.append("marquage")
    vehicule.save(update_fields=champs)
    return vehicule


def lever_marquage(vehicule: Vehicule) -> Vehicule:
    """Retire l'étiquette Immobilisé / Hors service (« Remettre en service ») ; le statut est à recalculer ensuite."""
    vehicule.marquage = ""
    vehicule.save(update_fields=["marquage", "updated_at"])
    return vehicule


def liberer_apres_mission(vehicule: Vehicule) -> Vehicule:
    """Fin de mission : « En mission » → « Disponible » (cahier-des-charges.md:139).

    Un camion passé entre-temps en maintenance, immobilisé ou hors service
    garde ce statut : seule la mission le libérait, pas le reste.
    """
    if vehicule.statut == StatutVehicule.EN_MISSION:
        return definir_statut(vehicule, StatutVehicule.DISPONIBLE)
    return vehicule


def distance_plausible(depuis_km: int, jusqu_a_km: int, *, ecart_max: int | None = None) -> bool:
    """Faux si la distance parcourue dépasse ``ecart_max`` (par défaut l'écart maximal des paramètres, 5 000 km
    dans le cahier des charges) : au-delà, c'est une faute de frappe plutôt qu'un trajet. Le compteur ne pouvant
    jamais reculer, une valeur trop haute le figerait définitivement (audit M5-10 / M6-09)."""
    if ecart_max is None:
        ecart_max = parametres_services.parametres().ecart_km_max
    return jusqu_a_km - depuis_km <= ecart_max


def enregistrer_kilometrage(vehicule: Vehicule, kilometrage: int) -> Vehicule:
    """Met à jour le compteur ; il ne peut jamais reculer (cahier-des-charges.md:139)."""
    if kilometrage < vehicule.kilometrage:
        raise ValueError("Le kilométrage ne peut pas diminuer.")
    vehicule.kilometrage = kilometrage
    vehicule.save(update_fields=["kilometrage", "updated_at"])
    return vehicule


def corriger_kilometrage(vehicule: Vehicule, acteur, *, kilometrage: int, motif: str) -> Vehicule:
    """Corrige le compteur d'un camion, y compris à la baisse (:func:`enregistrer_kilometrage` ne recule jamais).

    Pour rattraper une faute de frappe qui l'a gonflé (un chiffre en trop sur un plein ou un retour de mission) : sans
    cela, la valeur fausse sert ensuite de plancher à tous les relevés suivants. Réservé à l'ADMIN, motif obligatoire,
    tracé dans le journal d'audit (ancienne et nouvelle valeur, motif, auteur)."""
    if acteur.role_effectif not in permissions.CORRECTION_COMPTEUR:
        raise ActionNonAutorisee("Seul l'administrateur peut corriger le compteur d'un camion.")
    motif = motif.strip()
    if not motif:
        raise KilometrageInvalide("Le motif de la correction est obligatoire.")
    if kilometrage < 0:
        raise KilometrageInvalide("Le kilométrage ne peut pas être négatif.")
    ancien = vehicule.kilometrage
    if kilometrage == ancien:
        raise KilometrageInvalide("Ce kilométrage est déjà celui du compteur.")
    vehicule.kilometrage = kilometrage
    vehicule.save(update_fields=["kilometrage", "updated_at"])
    audit_services.log_action(
        action=ActionChoices.UPDATE, module="PARC_AUTO", entite="Vehicule", entite_id=vehicule.pk, utilisateur=acteur,
        ancienne_valeur={"correction_kilometrage": ancien},
        nouvelle_valeur={"correction_kilometrage": kilometrage, "motif": motif},
    )
    return vehicule


def documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int | None = None
) -> QuerySet[DocumentReglementaire]:
    """Documents expirant d'ici ``jours`` jours (par défaut le délai d'alerte des paramètres), ou déjà expirés.

    Alimente l'alerte préventive (30 jours dans le cahier-des-charges.md:95) et le
    centre d'alertes du tableau de bord (cahier-des-charges.md:231-232).
    """
    limite = (aujourd_hui or timezone.localdate()) + timedelta(days=parametres_services.delai_alerte(jours))
    return DocumentReglementaire.objects.select_related("vehicule").filter(
        date_expiration__lte=limite, vehicule__in=vehicules_suivis()
    )


def vehicules_suivis() -> QuerySet[Vehicule]:
    """Camions dont les documents sont surveillés : ni supprimés, ni hors service (réformés) — audit M2-22."""
    return Vehicule.objects.exclude(statut=StatutVehicule.HORS_SERVICE).exclude(marquage=StatutVehicule.HORS_SERVICE)


def documents_manquants() -> list[tuple[Vehicule, str, str]]:
    """Documents réglementaires jamais enregistrés pour un camion suivi (les 4 du CDC sont attendus) :
    ``(camion, code, libellé)``, par immatriculation. Un document manquant est plus grave qu'un document qui
    expire : il ne déclenchait aucune alerte et le camion paraissait « À jour » (audit M2-22)."""
    presents = set(DocumentReglementaire.objects.values_list("vehicule_id", "type_document"))
    return [
        (vehicule, code, libelle)
        for vehicule in vehicules_suivis().order_by("immatriculation")
        for code, libelle in TypeDocument.choices
        if (vehicule.pk, code) not in presents
    ]


def vehicules_avec_documents_manquants() -> set[int]:
    return {vehicule.pk for vehicule, _code, _libelle in documents_manquants()}


# --- fiche véhicule (cahier-des-charges.md:88-90) ---


def vehicules_queryset() -> QuerySet[Vehicule]:
    """Camions avec leur chauffeur habituel chargé (évite les requêtes en boucle)."""
    return Vehicule.objects.select_related("chauffeur_habituel__personnel")


def _normaliser(immatriculation: str, vin: str) -> tuple[str, str]:
    return " ".join(immatriculation.upper().split()), vin.strip().upper()


def cle_immatriculation(immatriculation: str) -> str:
    """Immatriculation sans séparateur, en majuscules : « AB-123-CD », « AB 123 CD » et « ab123cd » sont le même
    camion (audit M2-02)."""
    return re.sub(r"[^0-9A-Z]", "", immatriculation.upper())


def vehicule_par_immatriculation(immatriculation: str, *, sauf: Vehicule | None = None) -> Vehicule | None:
    """Le camion (supprimé logiquement compris) qui porte déjà cette immatriculation, quelle que soit son écriture."""
    cle = cle_immatriculation(immatriculation)
    candidats = Vehicule.all_objects.exclude(pk=sauf.pk if sauf else None).only("pk", "immatriculation")
    return next((v for v in candidats if cle_immatriculation(v.immatriculation) == cle), None)


ANNEE_MIN = 1950
VIN_LONGUEUR_MAX = 17  # longueur d'un VIN normalisé, et de la colonne en base


def _verifier_fiche(
    *,
    immatriculation: str,
    vin: str,
    annee: int,
    capacite_charge_t: Decimal,
    reservoir_l: int,
    exclure: Vehicule | None = None,
) -> None:
    if not immatriculation:
        raise VehiculeInvalide("L'immatriculation est obligatoire.")
    if len(immatriculation) > Vehicule._meta.get_field("immatriculation").max_length:
        raise VehiculeInvalide("L'immatriculation est trop longue.")
    if not vin:
        raise VehiculeInvalide("Le n° de châssis (VIN) est obligatoire.")
    if len(vin) > VIN_LONGUEUR_MAX:
        raise VehiculeInvalide(f"Le n° de châssis (VIN) compte au plus {VIN_LONGUEUR_MAX} caractères.")
    annee_max = timezone.localdate().year + 1
    if not ANNEE_MIN <= annee <= annee_max:
        raise VehiculeInvalide(f"L'année doit être comprise entre {ANNEE_MIN} et {annee_max}.")
    if capacite_charge_t <= 0:
        raise VehiculeInvalide("La capacité de charge doit être strictement positive.")
    if reservoir_l <= 0:
        raise VehiculeInvalide("La capacité du réservoir doit être strictement positive.")
    # all_objects : l'unicité en base compte aussi les camions supprimés logiquement.
    autres = Vehicule.all_objects.exclude(pk=exclure.pk if exclure else None)
    existant = vehicule_par_immatriculation(immatriculation, sauf=exclure)
    if existant is not None:
        raise DoublonVehicule(
            f"L'immatriculation {immatriculation} est déjà utilisée (camion {existant.immatriculation})."
        )
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
        annee=annee,
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
        annee=annee,
        capacite_charge_t=capacite_charge_t,
        reservoir_l=reservoir_l,
        exclure=vehicule,
    )
    if kilometrage < vehicule.kilometrage:
        raise KilometrageInvalide(
            f"Le compteur ({vehicule.kilometrage} km) ne peut pas diminuer."
        )
    # Une faute de frappe (un chiffre en trop) figerait le compteur : au-delà de l'écart maximal des paramètres,
    # la hausse passe par la correction du compteur de l'ADMIN, tracée (audit M2-07).
    ecart_max = parametres_services.parametres().ecart_km_max
    if not distance_plausible(vehicule.kilometrage, kilometrage, ecart_max=ecart_max):
        raise KilometrageInvalide(
            f"Le compteur passerait de {vehicule.kilometrage} à {kilometrage} km (plus de {ecart_max} km) : "
            "vérifiez la saisie, ou faites corriger le compteur par l'administrateur."
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
    vehicules = filtrer_par_texte(
        vehicules, recherche, "immatriculation", "marque", "modele", "vin"
    )
    if documents_a_renouveler:  # à renouveler ou manquants : tout ce qui demande une action
        vehicules = vehicules.filter(
            pk__in=vehicules_avec_documents_a_renouveler() | vehicules_avec_documents_manquants()
        )
    return vehicules


# --- documents réglementaires (cahier-des-charges.md:93-95) ---


def repartition_statuts() -> dict[str, int]:
    """Nombre de camions par statut (tous les statuts, y compris à 0) et total.

    Tableau de bord d'exploitation : disponibles / en mission / au garage
    (cahier-des-charges.md:229-230).
    """
    comptes = dict.fromkeys(StatutVehicule.values, 0)
    for statut, nombre in Vehicule.objects.values_list("statut").annotate(n=Count("pk")):
        comptes[statut] = nombre
    comptes["total"] = sum(comptes.values())
    return comptes


def vehicules_avec_documents_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int | None = None
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
    vehicule: Vehicule, *, aujourd_hui: date | None = None, jours: int | None = None
) -> list[dict]:
    """Situation des 4 documents réglementaires d'un camion, dans l'ordre du CDC.

    ``etat`` : EXPIRE (date dépassée), A_RENOUVELER (échéance dans ``jours``
    jours ou moins), VALIDE, MANQUANT (jamais enregistré).
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    jours = parametres_services.delai_alerte(jours)
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
