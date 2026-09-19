"""Logique métier des chauffeurs — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS
from apps.core.services import etat_echeance
from apps.hr.models import Personnel

from .exceptions import CategorieInvalide, StatutNonModifiable
from .models import CategoriePermis, Chauffeur, StatutChauffeur


@transaction.atomic
def assurer_fiche_chauffeur(personnel: Personnel) -> tuple[Chauffeur, bool]:
    """Garantit qu'un employé « Chauffeur » a une fiche chauffeur liée.

    cahier-des-charges.md:108 : poste « Chauffeur » → fiche créée
    automatiquement. Idempotent : ``all_objects`` évite de violer l'unicité
    du lien 1-1 si une fiche existe déjà, y compris supprimée logiquement
    (dans ce cas elle est restaurée plutôt que dupliquée).

    Retourne ``(fiche, creee)``.
    """
    fiche, creee = Chauffeur.all_objects.get_or_create(personnel=personnel)
    if fiche.is_deleted:
        fiche.restore()
    return fiche, creee


def changer_statut(chauffeur: Chauffeur, statut: str) -> Chauffeur:
    """Change le statut (Disponible, En mission, En congé, Suspendu, Inactif)."""
    if statut not in StatutChauffeur.values:
        raise ValueError(f"Statut chauffeur inconnu : {statut!r}")
    chauffeur.statut = statut
    chauffeur.save(update_fields=["statut", "updated_at"])
    return chauffeur


def chauffeurs_actifs() -> QuerySet[Chauffeur]:
    """Chauffeurs non inactifs, pour les listes de choix (ex. chauffeur habituel)."""
    return (
        Chauffeur.objects.select_related("personnel")
        .exclude(statut=StatutChauffeur.INACTIF)
        .order_by("personnel__nom", "personnel__prenom")
    )


def chauffeurs_disponibles() -> QuerySet[Chauffeur]:
    """Chauffeurs au statut « Disponible », pour l'affectation d'une mission."""
    return Chauffeur.objects.select_related("personnel").filter(
        statut=StatutChauffeur.DISPONIBLE
    )


def mettre_en_mission(chauffeur: Chauffeur) -> Chauffeur:
    """Départ d'une mission : statut « En mission » (cahier-des-charges.md:135)."""
    return changer_statut(chauffeur, StatutChauffeur.EN_MISSION)


def rappeler_de_mission(chauffeur: Chauffeur) -> Chauffeur:
    """Fin de mission : « Disponible », sauf statut changé entre-temps
    (En congé, Suspendu, Inactif), qui reste alors conservé."""
    if chauffeur.statut == StatutChauffeur.EN_MISSION:
        return changer_statut(chauffeur, StatutChauffeur.DISPONIBLE)
    return chauffeur


def mettre_en_conge(chauffeur: Chauffeur) -> Chauffeur:
    """Début d'un congé : statut « En congé »."""
    return changer_statut(chauffeur, StatutChauffeur.EN_CONGE)


def rappeler_de_conge(chauffeur: Chauffeur) -> Chauffeur:
    """Fin d'un congé : « Disponible », sauf si le statut a changé entre-temps
    (ex. Suspendu ou Inactif), qui reste alors conservé."""
    if chauffeur.statut == StatutChauffeur.EN_CONGE:
        return changer_statut(chauffeur, StatutChauffeur.DISPONIBLE)
    return chauffeur


def chauffeurs_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> QuerySet[Chauffeur]:
    """Chauffeurs dont permis OU visite médicale expire d'ici ``jours`` jours.

    Inclut les documents déjà expirés (alerte préventive à 30 jours,
    cahier-des-charges.md:95 et glossaire-metier.md:10-11).
    """
    limite = (aujourd_hui or timezone.localdate()) + timedelta(days=jours)
    return Chauffeur.objects.select_related("personnel").filter(
        Q(date_expiration_permis__lte=limite)
        | Q(date_expiration_visite_medicale__lte=limite)
    )


# --- fiche chauffeur (cahier-des-charges.md:105-113) ---

# Statuts posés à la main. « En mission » et « En congé » sont posés par les
# missions et les congés : les modifier à la main casserait ces workflows.
STATUTS_MANUELS = (
    StatutChauffeur.DISPONIBLE,
    StatutChauffeur.SUSPENDU,
    StatutChauffeur.INACTIF,
)
STATUTS_VERROUILLES = (StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE)


def chauffeurs_queryset() -> QuerySet[Chauffeur]:
    """Chauffeurs avec leur fiche personnel chargée."""
    return Chauffeur.objects.select_related("personnel")


def rechercher_chauffeurs(
    *,
    statut: str | None = None,
    recherche: str = "",
    a_renouveler: bool = False,
) -> QuerySet[Chauffeur]:
    """Chauffeurs filtrés par statut, texte (matricule, nom, prénom, n° de permis)
    et/ou permis ou visite médicale à renouveler."""
    chauffeurs = chauffeurs_queryset()
    if statut in StatutChauffeur.values:
        chauffeurs = chauffeurs.filter(statut=statut)
    recherche = recherche.strip()
    if recherche:
        chauffeurs = chauffeurs.filter(
            Q(personnel__matricule__icontains=recherche)
            | Q(personnel__nom__icontains=recherche)
            | Q(personnel__prenom__icontains=recherche)
            | Q(numero_permis__icontains=recherche)
        )
    if a_renouveler:
        chauffeurs = chauffeurs.filter(pk__in=chauffeurs_avec_echeance_proche())
    return chauffeurs.order_by("personnel__nom", "personnel__prenom")


def chauffeurs_avec_echeance_proche(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> set[int]:
    """Identifiants des chauffeurs dont le permis ou la visite médicale expire."""
    return set(
        chauffeurs_a_renouveler(aujourd_hui=aujourd_hui, jours=jours).values_list(
            "pk", flat=True
        )
    )


def etat_echeances(
    chauffeur: Chauffeur, *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> list[dict]:
    """Situation du permis et de la visite médicale (cahier-des-charges.md:110-111)."""
    lignes = []
    for libelle, expiration in (
        ("Permis de conduire", chauffeur.date_expiration_permis),
        ("Visite médicale", chauffeur.date_expiration_visite_medicale),
    ):
        etat, restants = etat_echeance(expiration, aujourd_hui=aujourd_hui, jours=jours)
        lignes.append(
            {
                "libelle": libelle,
                "date_expiration": expiration,
                "etat": etat,
                "jours_restants": restants,
            }
        )
    return lignes


@transaction.atomic
def modifier_chauffeur(
    chauffeur: Chauffeur,
    *,
    telephone: str = "",
    contact_urgence: str = "",
    numero_permis: str = "",
    categories_permis: list[str] | None = None,
    date_expiration_permis: date | None = None,
    date_expiration_visite_medicale: date | None = None,
) -> Chauffeur:
    """Met à jour les informations propres au chauffeur.

    Matricule, nom et prénom viennent de la fiche du personnel (source de vérité,
    cahier-des-charges.md:107) : ils ne se modifient pas ici. Les catégories de
    permis (C, E) sont validées, sans doublon, triées.
    """
    categories = sorted(set(categories_permis or []))
    inconnues = [c for c in categories if c not in CategoriePermis.values]
    if inconnues:
        raise CategorieInvalide(
            f"Catégorie(s) de permis inconnue(s) : {', '.join(inconnues)} (autorisées : C, E)."
        )
    type(chauffeur)._base_manager.select_for_update().filter(pk=chauffeur.pk).first()
    chauffeur.refresh_from_db()
    chauffeur.telephone = telephone.strip()
    chauffeur.contact_urgence = contact_urgence.strip()
    chauffeur.numero_permis = numero_permis.strip()
    chauffeur.categories_permis = categories
    chauffeur.date_expiration_permis = date_expiration_permis
    chauffeur.date_expiration_visite_medicale = date_expiration_visite_medicale
    chauffeur.save()
    return chauffeur


@transaction.atomic
def changer_statut_manuel(chauffeur: Chauffeur, statut: str) -> Chauffeur:
    """Suspend, désactive ou remet un chauffeur « Disponible » à la main.

    Refusé si le chauffeur est en mission ou en congé (statuts posés par les
    missions et les congés), ou si ``statut`` n'est pas un statut manuel.
    """
    if statut not in STATUTS_MANUELS:
        raise StatutNonModifiable(
            "Seuls les statuts Disponible, Suspendu et Inactif se posent à la main."
        )
    type(chauffeur)._base_manager.select_for_update().filter(pk=chauffeur.pk).first()
    chauffeur.refresh_from_db()
    if chauffeur.statut in STATUTS_VERROUILLES:
        raise StatutNonModifiable(
            f"Le chauffeur est « {chauffeur.get_statut_display()} » : ce statut est géré "
            "par les missions et les congés."
        )
    return changer_statut(chauffeur, statut)
