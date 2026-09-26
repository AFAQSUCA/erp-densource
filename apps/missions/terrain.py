"""Prévision de trésorerie des missions (R4) : avances, dépenses prévues et imprévus.

Réf. avenant-separation-des-taches.md (R4). Séparation des tâches : celui qui déclare ou planifie
un frais n'est jamais celui qui le valide. Une avance de route ou une dépense prévue est
planifiée par le Parc Auto puis validée par la Finance seule ; un imprévu est déclaré par le
chauffeur (mobile, avec preuve) puis validé deux fois — Parc Auto d'abord, Finance ensuite. Un
encaissement est un simple reflet d'un règlement déjà enregistré, créé directement confirmé
(``finance.receivers``, aucune double saisie).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.files.base import File
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.drivers.models import Chauffeur

from . import permissions, signals
from .exceptions import ActionFraisNonAutorisee, FraisInvalide
from .models import FraisMission, Mission, StatutFraisMission, TypeFraisMission

TYPES_PLANIFIABLES = (TypeFraisMission.AVANCE_ROUTE, TypeFraisMission.DEPENSE_PREVUE)


def _recharger(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_role(acteur, roles, action: str) -> None:
    """Contrôle strict (``acteur.role``) : ni l'ADMIN ni un superutilisateur ne valident un
    frais de mission à la place du Parc Auto ou de la Finance (même logique que la facturation)."""
    if acteur.role not in roles:
        raise ActionFraisNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def frais_queryset(mission: Mission) -> QuerySet[FraisMission]:
    return mission.frais.select_related(
        "chauffeur__personnel", "saisi_par", "valide_parcauto_par", "valide_finances_par"
    )


def frais_a_traiter() -> QuerySet[FraisMission]:
    """Lignes ``PREVU`` toutes missions confondues (tableau de bord Parc Auto / Finance)."""
    return (
        FraisMission.objects.filter(statut=StatutFraisMission.PREVU)
        .select_related("mission", "chauffeur__personnel", "saisi_par")
        .order_by("created_at", "pk")
    )


def totaux(mission: Mission) -> dict:
    """Sorties et encaissement confirmés, et nombre de lignes encore en attente."""
    lignes = list(frais_queryset(mission))
    sorties = sum(
        (f.montant for f in lignes if f.est_sortie and f.statut == StatutFraisMission.CONFIRME),
        Decimal("0"),
    )
    encaisse = sum(
        (
            f.montant
            for f in lignes
            if f.type_frais == TypeFraisMission.ENCAISSEMENT and f.statut == StatutFraisMission.CONFIRME
        ),
        Decimal("0"),
    )
    en_attente = sum(1 for f in lignes if f.statut == StatutFraisMission.PREVU)
    return {"sorties": sorties, "encaisse": encaisse, "solde": encaisse - sorties, "en_attente": en_attente}


# --- déclaration (chauffeur) et planification (Parc Auto) ---


@transaction.atomic
def declarer_imprevu(
    mission: Mission, chauffeur: Chauffeur, *, montant: Decimal, justificatif: File, description: str = ""
) -> FraisMission:
    """Le chauffeur déclare un imprévu (panne, incident) sur sa mission, avec une preuve.

    Jamais validé par lui-même : Parc Auto puis Finance confirment (double validation).
    """
    if mission.chauffeur_id != chauffeur.pk:
        raise ActionFraisNonAutorisee("Cette mission n'est pas affectée à ce chauffeur.")
    montant = Decimal(montant)
    if montant <= 0:
        raise FraisInvalide("Le montant doit être strictement positif.")
    if not justificatif:
        raise FraisInvalide("Une preuve (photo, facture) est obligatoire pour un imprévu.")
    frais = FraisMission.objects.create(
        mission=mission,
        type_frais=TypeFraisMission.IMPREVU,
        montant=montant,
        description=description.strip(),
        justificatif=justificatif,
        chauffeur=chauffeur,
    )
    signals.emettre(signals.frais_mission_declare, frais=frais)
    return frais


@transaction.atomic
def planifier_frais(
    mission: Mission, acteur, *, type_frais: str, montant: Decimal, description: str = ""
) -> FraisMission:
    """Le Parc Auto planifie une avance de route ou une dépense prévue avant le départ."""
    _exiger_role(acteur, permissions.FRAIS_SAISIE_PREVISION, "planifier un frais de mission")
    if type_frais not in TYPES_PLANIFIABLES:
        raise FraisInvalide("Seules une avance de route ou une dépense prévue se planifient ainsi.")
    montant = Decimal(montant)
    if montant <= 0:
        raise FraisInvalide("Le montant doit être strictement positif.")
    return FraisMission.objects.create(
        mission=mission,
        type_frais=type_frais,
        montant=montant,
        description=description.strip(),
        saisi_par=acteur,
    )


# --- validation ---


@transaction.atomic
def valider_parcauto(frais: FraisMission, acteur) -> FraisMission:
    """Première validation d'un imprévu par le Parc Auto : la Finance confirme ensuite."""
    _exiger_role(acteur, permissions.FRAIS_VALIDATION_PARCAUTO, "valider un frais de mission")
    _recharger(frais)
    if frais.type_frais != TypeFraisMission.IMPREVU:
        raise FraisInvalide("Seul un imprévu passe par une validation du Parc Auto.")
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    frais.valide_parcauto_par = acteur
    frais.date_validation_parcauto = timezone.now()
    frais.save(update_fields=["valide_parcauto_par", "date_validation_parcauto", "updated_at"])
    signals.emettre(signals.frais_mission_valide_parcauto, frais=frais)
    return frais


@transaction.atomic
def valider_finances(frais: FraisMission, acteur) -> FraisMission:
    """La Finance confirme la ligne : avance/dépense prévue directement, imprévu seulement une
    fois validé par le Parc Auto (seconde validation)."""
    _exiger_role(acteur, permissions.FRAIS_VALIDATION_FINANCES, "valider un frais de mission")
    _recharger(frais)
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    if frais.type_frais == TypeFraisMission.IMPREVU and frais.valide_parcauto_par_id is None:
        raise FraisInvalide("Cet imprévu n'a pas encore été validé par le Parc Auto.")
    frais.valide_finances_par = acteur
    frais.date_validation_finances = timezone.now()
    frais.statut = StatutFraisMission.CONFIRME
    frais.save()
    # Envoi non protégé (comme garage.or_cloture) : si la dépense automatique ne peut pas
    # s'écrire, la confirmation est annulée plutôt que de laisser une sortie d'argent non comptée.
    for _recepteur, resultat in signals.frais_mission_confirme.send(sender=FraisMission, frais=frais):
        if isinstance(resultat, Exception):
            raise resultat
    return frais


@transaction.atomic
def rejeter(frais: FraisMission, acteur, *, motif: str) -> FraisMission:
    """Rejette une ligne encore ``PREVU`` : le Parc Auto pour un imprévu pas encore transmis à la
    Finance, la Finance dans tous les autres cas."""
    _recharger(frais)
    if frais.statut != StatutFraisMission.PREVU:
        raise FraisInvalide(f"Cette ligne est « {frais.get_statut_display()} », déjà traitée.")
    attend_le_parcauto = frais.type_frais == TypeFraisMission.IMPREVU and frais.valide_parcauto_par_id is None
    roles = permissions.FRAIS_VALIDATION_PARCAUTO if attend_le_parcauto else permissions.FRAIS_VALIDATION_FINANCES
    _exiger_role(acteur, roles, "rejeter un frais de mission")
    if not motif.strip():
        raise FraisInvalide("Le motif du rejet est obligatoire.")
    frais.statut = StatutFraisMission.REJETE
    frais.motif_rejet = motif.strip()
    frais.save(update_fields=["statut", "motif_rejet", "updated_at"])
    signals.emettre(signals.frais_mission_rejete, frais=frais)
    return frais


def creer_encaissement(mission: Mission, *, montant: Decimal, libelle: str, saisi_par=None) -> FraisMission:
    """Reflet automatique d'un règlement reçu pour la facture de cette mission : aucune double
    saisie, directement confirmé (appelé par ``finance.receivers``)."""
    return FraisMission.objects.create(
        mission=mission,
        type_frais=TypeFraisMission.ENCAISSEMENT,
        montant=montant,
        description=libelle,
        statut=StatutFraisMission.CONFIRME,
        saisi_par=saisi_par,
    )
