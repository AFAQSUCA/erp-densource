"""Logique métier des chauffeurs — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS
from apps.hr.models import Personnel

from .models import Chauffeur, StatutChauffeur


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
