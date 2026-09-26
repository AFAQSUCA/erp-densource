"""Dépenses du parc auto pré-approuvées (R2) : enveloppes mensuelles, demandes, ordres de décaissement.

Réf. avenant-separation-des-taches.md (R2). Séparation des tâches : le Parc Auto demande, la
DIRECTION valide (jamais l'ADMIN à sa place), la Finance exécute — jamais la même personne des
deux côtés.

Deux circuits sur le même modèle ``DemandeDepense`` :
- **Manuelle** : le Parc Auto soumet une demande avant un achat ou une réparation non routinière ;
  validée, elle génère un ``OrdreDecaissement`` que la Finance exécute (mode, montant réel,
  justificatif) — un dépassement de plus de 10 % du montant validé bloque l'exécution et renvoie
  l'ordre à la DIRECTION.
- **Dépassement d'enveloppe** : une dépense automatique (carburant, pièces, main-d'œuvre —
  ``finance.receivers``) qui vient de se comptabiliser toute seule fait franchir le plafond
  mensuel approuvé par la DIRECTION pour sa catégorie (et son camion, si une enveloppe lui est
  propre) : la dépense reste comptée (l'argent est déjà sorti), mais une demande s'ouvre
  automatiquement et bloque la dépense automatique *suivante* de cette catégorie tant qu'elle
  n'est pas décidée.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from apps.billing import services as billing_services
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide, TransitionFactureInterdite
from apps.billing.models import CategorieDepense, Depense, OrigineDepense
from apps.core.services import prochain_numero
from apps.fleet.models import Vehicule

from . import permissions, signals
from .models import (
    DemandeDepense,
    EnveloppeDepense,
    OrdreDecaissement,
    OrigineDemande,
    StatutDemandeDepense,
    StatutOrdreDecaissement,
)

ZERO = Decimal("0")
SEUIL_DEPASSEMENT = Decimal("1.10")  # au-delà de 10 % du montant validé, l'exécution est bloquée
PREFIXE_DEMANDE = "DEM"
PREFIXE_ORDRE = "ODC"

# Catégories couvertes par R2 (enveloppes et demandes). Volontairement plus restreint que
# ``billing.CATEGORIES_AUTOMATIQUES`` : les frais de mission (R4) ont déjà leur propre double
# validation (Parc Auto puis Finance) et ne passent pas en plus par une enveloppe ou une demande.
CATEGORIES_PARC_AUTO = (CategorieDepense.CARBURANT, CategorieDepense.PIECES, CategorieDepense.MAINTENANCE)


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionFactureNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_categorie_automatique(categorie: str) -> None:
    if categorie not in CATEGORIES_PARC_AUTO:
        raise MontantInvalide(
            "Seules les catégories du parc auto (carburant, pièces détachées, main-d'œuvre des "
            "réparations) passent par une demande ou une enveloppe."
        )


# --- enveloppes ---


def enveloppes_queryset() -> QuerySet[EnveloppeDepense]:
    return EnveloppeDepense.objects.select_related("vehicule", "valide_par")


@transaction.atomic
def definir_enveloppe(
    acteur, *, categorie: str, annee: int, mois: int, montant_plafond: Decimal, vehicule: Vehicule | None = None
) -> EnveloppeDepense:
    """La DIRECTION fixe (ou met à jour) le plafond mensuel d'une catégorie, globalement ou pour
    un camion précis."""
    _exiger_role(acteur, permissions.ENVELOPPE_VALIDATION, "définir une enveloppe", strict=True)
    _exiger_categorie_automatique(categorie)
    if not 1 <= mois <= 12:
        raise MontantInvalide("Mois invalide.")
    montant_plafond = Decimal(montant_plafond)
    if montant_plafond <= 0:
        raise MontantInvalide("Le plafond doit être strictement positif.")
    enveloppe, _cree = EnveloppeDepense.objects.update_or_create(
        categorie=categorie, vehicule=vehicule, annee=annee, mois=mois,
        defaults={"montant_plafond": montant_plafond, "valide_par": acteur},
    )
    return enveloppe


def _enveloppe_applicable(categorie: str, vehicule: Vehicule | None, annee: int, mois: int) -> EnveloppeDepense | None:
    """L'enveloppe propre au camion prime sur l'enveloppe globale de la catégorie."""
    if vehicule is not None:
        specifique = EnveloppeDepense.objects.filter(
            categorie=categorie, vehicule=vehicule, annee=annee, mois=mois
        ).first()
        if specifique is not None:
            return specifique
    return EnveloppeDepense.objects.filter(categorie=categorie, vehicule=None, annee=annee, mois=mois).first()


def _consomme(categorie: str, enveloppe: EnveloppeDepense, annee: int, mois: int) -> Decimal:
    """Total des dépenses déjà comptabilisées ce mois pour le périmètre de cette enveloppe."""
    filtres = {"categorie": categorie, "date_depense__year": annee, "date_depense__month": mois}
    if enveloppe.vehicule_id:
        filtres["vehicule"] = enveloppe.vehicule
    return Depense.objects.filter(**filtres).aggregate(total=Sum("montant"))["total"] or ZERO


def _demande_en_attente(categorie: str, vehicule: Vehicule | None) -> DemandeDepense | None:
    return DemandeDepense.objects.filter(
        categorie=categorie, vehicule=vehicule, origine=OrigineDemande.DEPASSEMENT_ENVELOPPE,
        statut=StatutDemandeDepense.SOUMISE,
    ).first()


# --- point d'entrée appelé par finance.receivers à la place de billing.comptabiliser_depense_automatique ---


@transaction.atomic
def comptabiliser_avec_controle_enveloppe(
    *,
    origine: str,
    origine_id: int,
    categorie: str,
    date_depense: date,
    libelle: str,
    montant: Decimal,
    vehicule: Vehicule | None = None,
    reference: str = "",
) -> Depense | None:
    """Comptabilise une dépense automatique du parc auto après avoir vérifié son enveloppe (R2).

    Bloque (lève une erreur, annule l'opération d'origine — plein, achat, clôture d'OR) si une
    demande de dépassement est déjà en attente pour cette catégorie/ce camion : la DIRECTION doit
    la décider avant toute nouvelle dépense de ce type. Sinon, comptabilise normalement puis, si
    cette dépense fait franchir le plafond du mois, ouvre une nouvelle demande a posteriori (la
    dépense elle-même n'est jamais refusée : l'argent est déjà sorti).
    """
    annee, mois = date_depense.year, date_depense.month
    enveloppe = _enveloppe_applicable(categorie, vehicule, annee, mois)
    if enveloppe is not None:
        en_attente = _demande_en_attente(categorie, enveloppe.vehicule)
        if en_attente is not None:
            raise TransitionFactureInterdite(
                f"Enveloppe « {enveloppe.get_categorie_display()} » de {mois:02d}/{annee} dépassée : "
                f"la direction doit d'abord décider de la demande {en_attente.numero}."
            )
    depense = billing_services.comptabiliser_depense_automatique(
        origine=origine, origine_id=origine_id, categorie=categorie, date_depense=date_depense,
        libelle=libelle, montant=montant, reference=reference, vehicule=vehicule,
    )
    if enveloppe is not None and depense is not None:
        consomme = _consomme(categorie, enveloppe, annee, mois)
        if consomme > enveloppe.montant_plafond:
            demande = DemandeDepense.objects.create(
                numero=prochain_numero(PREFIXE_DEMANDE, annee),
                categorie=categorie, vehicule=enveloppe.vehicule, origine=OrigineDemande.DEPASSEMENT_ENVELOPPE,
                montant_estime=consomme - enveloppe.montant_plafond,
                motif=f"Enveloppe « {enveloppe.get_categorie_display()} » de {mois:02d}/{annee} dépassée par « {libelle} ».",
            )
            signals.emettre(signals.demande_soumise, demande=demande)
    return depense


# --- demande manuelle (Parc Auto) ---


def demandes_queryset() -> QuerySet[DemandeDepense]:
    return DemandeDepense.objects.select_related("vehicule", "demandeur", "valide_par")


@transaction.atomic
def soumettre_demande(
    acteur, *, categorie: str, montant_estime: Decimal, motif: str,
    vehicule: Vehicule | None = None, fournisseur: str = "", piece_jointe=None,
) -> DemandeDepense:
    """Le Parc Auto demande par avance un achat ou une réparation non routinière."""
    _exiger_role(acteur, permissions.DEMANDE_SAISIE, "soumettre une demande de dépense")
    _exiger_categorie_automatique(categorie)
    montant_estime = Decimal(montant_estime)
    if montant_estime <= 0:
        raise MontantInvalide("Le montant estimé doit être strictement positif.")
    motif = motif.strip()
    if not motif:
        raise MontantInvalide("Le motif est obligatoire.")
    demande = DemandeDepense.objects.create(
        numero=prochain_numero(PREFIXE_DEMANDE, timezone.localdate().year),
        categorie=categorie, vehicule=vehicule, origine=OrigineDemande.MANUELLE,
        montant_estime=montant_estime, motif=motif, fournisseur=fournisseur.strip(),
        piece_jointe=piece_jointe, demandeur=acteur,
    )
    signals.emettre(signals.demande_soumise, demande=demande)
    return demande


@transaction.atomic
def valider_demande(demande: DemandeDepense, acteur, *, montant_valide: Decimal | None = None) -> DemandeDepense:
    """La DIRECTION valide une demande : génère un ordre à exécuter (manuelle), ou débloque
    simplement le mécanisme automatique (dépassement d'enveloppe, la dépense existe déjà)."""
    _exiger_role(acteur, permissions.DEMANDE_VALIDATION, "valider une demande de dépense", strict=True)
    _verrouiller(demande)
    if demande.statut != StatutDemandeDepense.SOUMISE:
        raise TransitionFactureInterdite(f"Cette demande est « {demande.get_statut_display()} », déjà traitée.")
    demande.statut = StatutDemandeDepense.VALIDEE
    demande.valide_par = acteur
    demande.date_decision = timezone.now()
    demande.save(update_fields=["statut", "valide_par", "date_decision", "updated_at"])
    if demande.origine == OrigineDemande.MANUELLE:
        ordre = OrdreDecaissement.objects.create(
            numero=prochain_numero(PREFIXE_ORDRE, timezone.localdate().year),
            demande=demande, montant_valide=Decimal(montant_valide) if montant_valide else demande.montant_estime,
        )
        signals.emettre(signals.ordre_a_executer, ordre=ordre)
    signals.emettre(signals.demande_decidee, demande=demande)
    return demande


@transaction.atomic
def refuser_demande(demande: DemandeDepense, acteur, *, motif: str) -> DemandeDepense:
    """La DIRECTION refuse une demande ; un dépassement d'enveloppe refusé débloque quand même le
    mécanisme automatique (le refus ne fait qu'acter le désaccord, sans figer la flotte)."""
    _exiger_role(acteur, permissions.DEMANDE_VALIDATION, "refuser une demande de dépense", strict=True)
    _verrouiller(demande)
    if demande.statut != StatutDemandeDepense.SOUMISE:
        raise TransitionFactureInterdite(f"Cette demande est « {demande.get_statut_display()} », déjà traitée.")
    motif = motif.strip()
    if not motif:
        raise MontantInvalide("Le motif du refus est obligatoire.")
    demande.statut = StatutDemandeDepense.REFUSEE
    demande.valide_par = acteur
    demande.date_decision = timezone.now()
    demande.motif_refus = motif
    demande.save(update_fields=["statut", "valide_par", "date_decision", "motif_refus", "updated_at"])
    signals.emettre(signals.demande_decidee, demande=demande)
    return demande


# --- exécution (Finance) ---


def ordres_queryset() -> QuerySet[OrdreDecaissement]:
    return OrdreDecaissement.objects.select_related("demande__vehicule", "execute_par")


def executer_ordre(
    ordre: OrdreDecaissement, acteur, *, mode_paiement: str, montant_reel: Decimal, justificatif=None, reference: str = ""
) -> OrdreDecaissement:
    """La Finance exécute un ordre validé par la DIRECTION.

    Si le montant réel dépasse de plus de 10 % le montant validé, l'exécution est refusée et
    l'ordre bascule en attente de revalidation (état persistant : voir ``revalider_ordre``) plutôt
    que d'être exécuté tel quel. Pas de ``@transaction.atomic`` sur cette fonction elle-même
    (seulement sur le bloc ``with`` interne) : la mise en attente doit survivre à l'erreur levée
    ensuite, qu'une transaction englobante annulerait avec elle.
    """
    _exiger_role(acteur, permissions.ORDRE_EXECUTION, "exécuter un ordre de décaissement", strict=True)
    montant_reel = Decimal(montant_reel)
    if montant_reel <= 0:
        raise MontantInvalide("Le montant réel doit être strictement positif.")
    depasse = False
    with transaction.atomic():
        _verrouiller(ordre)
        if ordre.statut != StatutOrdreDecaissement.A_EXECUTER:
            raise TransitionFactureInterdite(f"Cet ordre est « {ordre.get_statut_display()} », déjà traité.")
        if montant_reel > ordre.montant_valide * SEUIL_DEPASSEMENT:
            depasse = True
            ordre.statut = StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION
            ordre.montant_reel = montant_reel
            ordre.save(update_fields=["statut", "montant_reel", "updated_at"])
        else:
            ordre.mode_paiement = mode_paiement
            ordre.montant_reel = montant_reel
            ordre.justificatif = justificatif
            ordre.execute_par = acteur
            ordre.date_execution = timezone.now()
            ordre.statut = StatutOrdreDecaissement.EXECUTE
            ordre.save()
            depense = billing_services.comptabiliser_depense_automatique(
                origine=OrigineDepense.ORDRE_DECAISSEMENT, origine_id=ordre.pk, categorie=ordre.demande.categorie,
                date_depense=timezone.localdate(), libelle=f"{ordre.numero} · {ordre.demande.motif[:150]}",
                montant=montant_reel, reference=reference, mode=mode_paiement, vehicule=ordre.demande.vehicule,
            )
            ordre.depense = depense
            ordre.save(update_fields=["depense", "updated_at"])
    if depasse:
        signals.emettre(signals.ordre_depassement, ordre=ordre)
        raise MontantInvalide(
            f"Le montant réel dépasse de plus de 10 % le montant validé : renvoyé à la direction pour revalidation."
        )
    return ordre


@transaction.atomic
def revalider_ordre(ordre: OrdreDecaissement, acteur, *, montant_valide: Decimal) -> OrdreDecaissement:
    """La DIRECTION revoit un ordre bloqué par un dépassement et fixe le nouveau montant validé ;
    la Finance peut alors retenter l'exécution."""
    _exiger_role(acteur, permissions.DEMANDE_VALIDATION, "revalider un ordre de décaissement", strict=True)
    _verrouiller(ordre)
    if ordre.statut != StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION:
        raise TransitionFactureInterdite("Cet ordre n'attend pas de revalidation.")
    montant_valide = Decimal(montant_valide)
    if montant_valide <= 0:
        raise MontantInvalide("Le montant validé doit être strictement positif.")
    ordre.montant_valide = montant_valide
    ordre.statut = StatutOrdreDecaissement.A_EXECUTER
    ordre.save(update_fields=["montant_valide", "statut", "updated_at"])
    return ordre
