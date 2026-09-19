"""Logique métier RH : recrutement et workflow de congés en 3 niveaux.

Réf. cahier-des-charges.md:204-221, glossaire-metier.md:133-144.

Statuts : DEMANDE → VALIDATION_N1 → APPROUVE → EN_COURS → TERMINE
(ou REFUSE). Les passages à EN_COURS / TERMINE sont automatiques
(:func:`synchroniser_statuts_conges`, à planifier par Celery Beat).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role

from .exceptions import ActionNonAutorisee, CongeError, SoldeInsuffisant, TransitionInterdite
from .models import (
    Conge,
    DecisionConge,
    NiveauValidation,
    Personnel,
    StatutConge,
    ValidationConge,
)

DELAI_VALIDATION_N1 = timedelta(hours=48)  # cahier-des-charges.md:213
DELAI_VALIDATION_N2 = timedelta(hours=24)  # cahier-des-charges.md:214


# --- recrutement ---


@transaction.atomic
def recruter(
    *,
    matricule: str,
    nom: str,
    prenom: str,
    poste: str,
    departement: str,
    type_contrat: str,
    date_embauche: date,
    salaire_base: Decimal,
    solde_conges_jours: int = 0,
) -> Personnel:
    """Enregistre un recrutement (cahier-des-charges.md:209-210).

    Si le poste est « Chauffeur », la fiche chauffeur est créée par le signal
    de ``drivers`` (cahier-des-charges.md:108).
    """
    return Personnel.objects.create(
        matricule=matricule,
        nom=nom,
        prenom=prenom,
        poste=poste,
        departement=departement,
        type_contrat=type_contrat,
        date_embauche=date_embauche,
        salaire_base=salaire_base,
        solde_conges_jours=solde_conges_jours,
    )


# --- droits des validateurs ---


def _fiche_de(acteur) -> Personnel | None:
    return getattr(acteur, "personnel", None)


def _est_chef_de(acteur, employe: Personnel) -> bool:
    """Chef du département de l'employé, jamais pour sa propre demande."""
    fiche = _fiche_de(acteur)
    return bool(
        fiche
        and fiche.est_chef_departement
        and fiche.departement == employe.departement
        and fiche.pk != employe.pk
    )


def _est_rh_pour(acteur, employe: Personnel) -> bool:
    """Utilisateur de rôle RH, jamais pour sa propre demande."""
    if acteur is None or acteur.role != Role.RH:
        return False
    fiche = _fiche_de(acteur)
    return fiche is None or fiche.pk != employe.pk


def _recharger(conge: Conge) -> Conge:
    """Verrouille et relit le congé pour éviter deux décisions concurrentes."""
    Conge.objects.select_for_update().filter(pk=conge.pk).first()
    conge.refresh_from_db()
    return conge


def _verrouiller_employe(employe: Personnel) -> Personnel:
    Personnel.objects.select_for_update().filter(pk=employe.pk).first()
    employe.refresh_from_db()
    return employe


def _exiger_solde(employe: Personnel, jours: int) -> None:
    if jours > employe.solde_conges_jours:
        raise SoldeInsuffisant(
            f"Solde insuffisant : {jours} jour(s) demandé(s), "
            f"{employe.solde_conges_jours} disponible(s)."
        )


# --- workflow ---


def calculer_jours(date_debut: date, date_fin: date) -> int:
    """Jours calendaires, bornes incluses."""
    return (date_fin - date_debut).days + 1


@transaction.atomic
def demander_conge(
    employe: Personnel,
    *,
    date_debut: date,
    date_fin: date,
    motif: str,
    maintenant: datetime | None = None,
) -> Conge:
    """Étape 1 : demande de l'employé (dates + motif), bloquée si solde insuffisant."""
    if date_fin < date_debut:
        raise CongeError("La date de fin précède la date de début.")
    jours = calculer_jours(date_debut, date_fin)
    _exiger_solde(_verrouiller_employe(employe), jours)

    maintenant = maintenant or timezone.now()
    return Conge.objects.create(
        employe=employe,
        date_debut=date_debut,
        date_fin=date_fin,
        jours=jours,
        motif=motif,
        date_limite_n1=maintenant + DELAI_VALIDATION_N1,
    )


@transaction.atomic
def valider_n1(
    conge: Conge, acteur, *, commentaire: str = "", maintenant: datetime | None = None
) -> Conge:
    """Étape 2 : validation N1 par le chef du département de l'employé (48 h)."""
    _recharger(conge)
    if conge.statut != StatutConge.DEMANDE:
        raise TransitionInterdite("Seule une demande peut être validée en N1.")
    if not _est_chef_de(acteur, conge.employe):
        raise ActionNonAutorisee(
            "Validation N1 réservée au chef du département de l'employé."
        )

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N1,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
    )
    conge.statut = StatutConge.VALIDATION_N1
    conge.date_limite_n2 = (maintenant or timezone.now()) + DELAI_VALIDATION_N2
    conge.save(update_fields=["statut", "date_limite_n2", "updated_at"])
    return conge


@transaction.atomic
def valider_n2(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Étape 3 : validation N2 par la RH (24 h). Décompte le solde de congés."""
    _recharger(conge)
    if conge.statut != StatutConge.VALIDATION_N1:
        raise TransitionInterdite("Seul un congé validé N1 peut être validé en N2.")
    if not _est_rh_pour(acteur, conge.employe):
        raise ActionNonAutorisee("Validation N2 réservée à la RH.")

    employe = _verrouiller_employe(conge.employe)
    _exiger_solde(employe, conge.jours)
    employe.solde_conges_jours -= conge.jours
    employe.save(update_fields=["solde_conges_jours", "updated_at"])

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N2,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
    )
    conge.statut = StatutConge.APPROUVE
    conge.save(update_fields=["statut", "updated_at"])
    return conge


@transaction.atomic
def refuser(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Refus par le validateur du niveau en cours (N1 sur DEMANDE, N2 sur VALIDATION_N1)."""
    _recharger(conge)
    if conge.statut == StatutConge.DEMANDE:
        niveau, autorise = NiveauValidation.N1, _est_chef_de(acteur, conge.employe)
    elif conge.statut == StatutConge.VALIDATION_N1:
        niveau, autorise = NiveauValidation.N2, _est_rh_pour(acteur, conge.employe)
    else:
        raise TransitionInterdite("Ce congé n'est plus en attente de validation.")
    if not autorise:
        raise ActionNonAutorisee("Vous n'êtes pas le validateur de ce niveau.")

    ValidationConge.objects.create(
        conge=conge,
        niveau=niveau,
        validateur=acteur,
        decision=DecisionConge.REFUSE,
        commentaire=commentaire,
    )
    conge.statut = StatutConge.REFUSE
    conge.motif_decision = commentaire
    conge.save(update_fields=["statut", "motif_decision", "updated_at"])
    return conge


@transaction.atomic
def annuler_conge_approuve(conge: Conge, acteur, *, motif: str = "") -> Conge:
    """Annulation d'un congé approuvé : RH uniquement (cahier-des-charges.md:220-221).

    Le CDC ne prévoit pas de statut « annulé » : le congé passe à REFUSE avec
    le motif, et les jours décomptés sont restitués au solde.
    """
    _recharger(conge)
    if conge.statut != StatutConge.APPROUVE:
        raise TransitionInterdite("Seul un congé approuvé peut être annulé.")
    if not _est_rh_pour(acteur, conge.employe):
        raise ActionNonAutorisee("Annulation d'un congé approuvé réservée à la RH.")

    employe = _verrouiller_employe(conge.employe)
    employe.solde_conges_jours += conge.jours
    employe.save(update_fields=["solde_conges_jours", "updated_at"])

    conge.statut = StatutConge.REFUSE
    conge.motif_decision = motif
    conge.save(update_fields=["statut", "motif_decision", "updated_at"])
    return conge


def synchroniser_statuts_conges(*, aujourd_hui: date | None = None) -> dict[str, int]:
    """Fait avancer les congés selon le calendrier : APPROUVE → EN_COURS → TERMINE.

    À exécuter chaque jour (Celery Beat, étape 5). Chaque changement de statut
    déclenche un signal : ``drivers`` y met le chauffeur « En congé » puis le
    remet « Disponible ».
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {"demarres": 0, "termines": 0}
    candidats = Conge.objects.select_related("employe").filter(
        statut__in=[StatutConge.APPROUVE, StatutConge.EN_COURS]
    )
    for conge in candidats:
        if conge.date_fin < aujourd_hui:
            conge.statut = StatutConge.TERMINE
            resultat["termines"] += 1
        elif conge.statut == StatutConge.APPROUVE and conge.date_debut <= aujourd_hui:
            conge.statut = StatutConge.EN_COURS
            resultat["demarres"] += 1
        else:
            continue
        conge.save(update_fields=["statut", "updated_at"])
    return resultat
