"""Sortie du personnel : démission, licenciement, fin de contrat… (cahier-des-charges.md:50 « RH : … embauche,
licenciement, contrats » ; règles décidées le 12/10/2026 : avenant-sortie-personnel.md).

La RH (ou la DIRECTION, l'ADMIN) enregistre la sortie, éventuellement à l'avance (préavis) : jusqu'à la date de
sortie l'employé travaille normalement. Le jour venu (tout de suite si la date est passée, sinon par la tâche
quotidienne), les effets s'appliquent en une seule transaction :

- refus si l'employé conduit ou accompagne une mission **en cours** (``missions``, signal ``sortie_a_verifier``) ;
  la tâche quotidienne réessaie alors chaque jour ;
- demandes de congé en attente refusées, congés approuvés pas encore commencés annulés ;
- subordonnés rattachés au supérieur du partant ;
- compte utilisateur désactivé (un superutilisateur se gère en ligne de commande) ;
- fiches chauffeur et copilote « Inactif » (``drivers``), missions affectées pas encore parties libérées et
  Parc Auto prévenu (``missions``), par le signal ``sortie_appliquee``.

Une sortie s'annule (erreur, réintégration) avec un motif ; le compte et les fiches se réactivent alors à la main.
"""

from __future__ import annotations

import logging
from datetime import date

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet, Subquery
from django.utils import timezone

from . import permissions, signals
from .exceptions import SortieImpossible
from .models import Conge, MotifSortie, Personnel, SortiePersonnel, StatutConge

logger = logging.getLogger(__name__)

STATUTS_EN_ATTENTE = (StatutConge.DEMANDE, StatutConge.VALIDATION_N1)


def _sorties_appliquees():
    return SortiePersonnel.objects.filter(
        employe=OuterRef("pk"), annulee_le__isnull=True, appliquee_le__isnull=False
    )


def presents(personnel: QuerySet[Personnel]) -> QuerySet[Personnel]:
    """Le personnel encore dans l'entreprise (sortie non appliquée, ou annulée)."""
    return personnel.exclude(Exists(_sorties_appliquees()))


def sortis(personnel: QuerySet[Personnel]) -> QuerySet[Personnel]:
    return personnel.filter(Exists(_sorties_appliquees()))


PRESENCE_PRESENTS, PRESENCE_SORTIS, PRESENCE_TOUS = "presents", "sortis", "tous"
PRESENCES = (
    (PRESENCE_PRESENTS, "Présents"),
    (PRESENCE_SORTIS, "Sortis"),
    (PRESENCE_TOUS, "Tous"),
)


def filtrer_presence(personnel: QuerySet[Personnel], presence: str) -> QuerySet[Personnel]:
    """Filtre de la liste du personnel : présents par défaut (une valeur inconnue vaut « présents »)."""
    if presence == PRESENCE_TOUS:
        return personnel
    if presence == PRESENCE_SORTIS:
        return sortis(personnel)
    return presents(personnel)


def annoter_sortie(personnel: QuerySet[Personnel]) -> QuerySet[Personnel]:
    """Ajoute ``date_sortie`` (sortie non annulée, appliquée ou à venir) et ``sortie_appliquee`` à chaque fiche,
    pour les badges de la liste, sans une requête par ligne."""
    actives = SortiePersonnel.objects.filter(employe=OuterRef("pk"), annulee_le__isnull=True)
    return personnel.annotate(
        date_sortie=Subquery(actives.values("date_sortie")[:1]),
        sortie_appliquee=Exists(actives.filter(appliquee_le__isnull=False)),
    )


def resume_bilan(sortie: SortiePersonnel, bilan: dict) -> str:
    """Phrase pour la RH : ce que la sortie vient de changer, ou sa date d'effet si elle est à venir."""
    nom = f"{sortie.employe.prenom} {sortie.employe.nom}"
    if sortie.appliquee_le is None:
        return (
            f"Sortie de {nom} enregistrée pour le {sortie.date_sortie:%d/%m/%Y} : jusque-là rien ne change, "
            "les effets s'appliqueront ce jour-là."
        )
    effets = []
    if bilan.get("compte_desactive"):
        effets.append(f"compte {bilan['compte_desactive']} désactivé")
    if bilan.get("compte_superutilisateur"):
        effets.append(f"compte superutilisateur {bilan['compte_superutilisateur']} à désactiver en ligne de commande")
    if bilan.get("conges_annules"):
        effets.append(f"{bilan['conges_annules']} congé(s) à venir annulé(s)")
    if bilan.get("subordonnes"):
        superieur = bilan.get("nouveau_superieur")
        cible = f"rattachée(s) à {superieur.prenom} {superieur.nom}" if superieur else "désormais sans supérieur"
        effets.append(f"{bilan['subordonnes']} personne(s) de son équipe {cible}")
    if bilan.get("fiche_chauffeur_inactive"):
        effets.append("fiche chauffeur inactive")
    if bilan.get("fiche_copilote_inactive"):
        effets.append("fiche copilote inactive")
    if bilan.get("missions_desaffectees"):
        effets.append(f"mission(s) {', '.join(bilan['missions_desaffectees'])} à réaffecter (Parc Auto prévenu)")
    if bilan.get("missions_sans_copilote"):
        effets.append(f"retiré(e) de la mission {', '.join(bilan['missions_sans_copilote'])}")
    detail = f" : {' ; '.join(effets)}" if effets else ""
    return f"Sortie de {nom} appliquée{detail}."


def sortie_active(employe: Personnel) -> SortiePersonnel | None:
    """La sortie enregistrée et non annulée de cet employé, appliquée ou encore à venir."""
    return employe.sorties.filter(annulee_le__isnull=True).select_related("enregistree_par").first()


def historique(employe: Personnel) -> QuerySet[SortiePersonnel]:
    return employe.sorties.select_related("enregistree_par", "annulee_par")


def peut_gerer(acteur, employe: Personnel) -> bool:
    """RH, DIRECTION, ADMIN ; jamais pour sa propre fiche."""
    return (
        getattr(acteur, "role_effectif", None) in permissions.PERSONNEL_MODIFICATION
        and not (employe.utilisateur_id and employe.utilisateur_id == acteur.pk)
    )


def _exiger_droit(acteur, employe: Personnel) -> None:
    if getattr(acteur, "role_effectif", None) not in permissions.PERSONNEL_MODIFICATION:
        raise SortieImpossible("Seules la RH, la direction et l'administration gèrent les sorties du personnel.")
    if employe.utilisateur_id and employe.utilisateur_id == acteur.pk:
        raise SortieImpossible("Vous ne pouvez pas gérer votre propre sortie.")


@transaction.atomic
def enregistrer_sortie(
    employe: Personnel,
    acteur,
    *,
    date_sortie: date,
    motif: str,
    commentaire: str = "",
    aujourd_hui: date | None = None,
) -> tuple[SortiePersonnel, dict]:
    """Enregistre la sortie ; l'applique aussitôt si ``date_sortie`` est aujourd'hui ou passée.

    Retourne ``(sortie, bilan)`` ; ``bilan`` est vide pour une sortie à venir."""
    _exiger_droit(acteur, employe)
    Personnel.objects.select_for_update().filter(pk=employe.pk).first()  # deux enregistrements simultanés
    existante = sortie_active(employe)
    if existante is not None:
        raise SortieImpossible(f"Une sortie est déjà enregistrée pour cet employé (le {existante.date_sortie:%d/%m/%Y}).")
    if motif not in MotifSortie.values:
        raise SortieImpossible("Motif de sortie inconnu.")
    commentaire = commentaire.strip()
    if motif == MotifSortie.AUTRE and not commentaire:
        raise SortieImpossible("Précisez le motif « Autre » dans le commentaire.")
    if date_sortie < employe.date_embauche:
        raise SortieImpossible(
            f"La date de sortie ne peut pas précéder l'embauche ({employe.date_embauche:%d/%m/%Y})."
        )
    sortie = SortiePersonnel.objects.create(
        employe=employe, date_sortie=date_sortie, motif=motif, commentaire=commentaire, enregistree_par=acteur
    )
    bilan = {}
    if date_sortie <= (aujourd_hui or timezone.localdate()):
        bilan = appliquer_sortie(sortie, acteur=acteur)
        sortie.refresh_from_db()
    return sortie, bilan


@transaction.atomic
def appliquer_sortie(sortie: SortiePersonnel, *, acteur=None) -> dict:
    """Applique les effets de la sortie (voir le module). Sans effet si elle est annulée ou déjà appliquée.
    Lève ``SortieImpossible`` (rien n'est modifié) si une autre app la refuse."""
    sortie = SortiePersonnel.objects.select_for_update().select_related("employe__utilisateur").get(pk=sortie.pk)
    if sortie.annulee_le is not None or sortie.appliquee_le is not None:
        return {}
    employe = sortie.employe
    signals.sortie_a_verifier.send(sender=SortiePersonnel, sortie=sortie)

    motif_conges = f"Sortie du personnel le {sortie.date_sortie:%d/%m/%Y}."
    annules = 0
    for conge in Conge.objects.select_for_update().filter(employe=employe, statut__in=STATUTS_EN_ATTENTE):
        conge.statut, conge.motif_decision = StatutConge.REFUSE, motif_conges
        conge.save(update_fields=["statut", "motif_decision", "updated_at"])
        signals.emettre(signals.conge_decide, conge=conge, decision=signals.DECISION_REFUSE, acteur=acteur)
        annules += 1
    for conge in Conge.objects.select_for_update().filter(
        employe=employe, statut=StatutConge.APPROUVE, date_debut__gt=sortie.date_sortie
    ):
        conge.statut, conge.motif_decision = StatutConge.REFUSE, motif_conges
        conge.save(update_fields=["statut", "motif_decision", "updated_at"])
        signals.emettre(signals.conge_decide, conge=conge, decision=signals.DECISION_ANNULE, acteur=acteur)
        annules += 1

    subordonnes = list(employe.subordonnes.all())
    for subordonne in subordonnes:
        subordonne.superieur = employe.superieur
        subordonne.save(update_fields=["superieur", "updated_at"])

    bilan = {"conges_annules": annules, "subordonnes": len(subordonnes), "nouveau_superieur": employe.superieur}
    compte = employe.utilisateur
    if compte is not None and compte.is_active:
        if compte.is_superuser:
            bilan["compte_superutilisateur"] = compte.username  # se désactive en ligne de commande
        else:
            compte.is_active = False
            compte.save(update_fields=["is_active"])
            bilan["compte_desactive"] = compte.username

    for _recepteur, resultat in signals.sortie_appliquee.send(sender=SortiePersonnel, sortie=sortie, acteur=acteur):
        if isinstance(resultat, dict):
            bilan.update(resultat)

    sortie.appliquee_le = timezone.now()
    sortie.save(update_fields=["appliquee_le", "updated_at"])
    return bilan


def appliquer_sorties_echues(*, aujourd_hui: date | None = None) -> dict:
    """Tâche quotidienne : applique les sorties dont la date est arrivée. Une sortie refusée (mission en cours)
    est réessayée le lendemain ; ``reportees`` liste ``(sortie, raison)`` pour prévenir la RH."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {"appliquees": 0, "reportees": []}
    echues = SortiePersonnel.objects.filter(
        annulee_le__isnull=True, appliquee_le__isnull=True, date_sortie__lte=aujourd_hui
    ).select_related("employe")
    for sortie in echues:
        try:
            appliquer_sortie(sortie)
        except SortieImpossible as erreur:
            logger.warning("Sortie de %s reportée : %s", sortie.employe, erreur)
            resultat["reportees"].append((sortie, str(erreur)))
        else:
            resultat["appliquees"] += 1
    return resultat


@transaction.atomic
def annuler_sortie(sortie: SortiePersonnel, acteur, *, motif: str) -> SortiePersonnel:
    """Annule une sortie (erreur, réintégration), motif obligatoire. Rien n'est réactivé automatiquement : le
    compte (écran Utilisateurs) et les fiches chauffeur ou copilote se réactivent à la main, les congés annulés
    se redemandent."""
    sortie = SortiePersonnel.objects.select_for_update().select_related("employe").get(pk=sortie.pk)
    _exiger_droit(acteur, sortie.employe)
    if sortie.annulee_le is not None:
        raise SortieImpossible("Cette sortie est déjà annulée.")
    motif = motif.strip()
    if not motif:
        raise SortieImpossible("Le motif de l'annulation est obligatoire.")
    sortie.annulee_le, sortie.annulee_par, sortie.motif_annulation = timezone.now(), acteur, motif
    sortie.save(update_fields=["annulee_le", "annulee_par", "motif_annulation", "updated_at"])
    return sortie
