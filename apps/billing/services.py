"""Logique métier de la facturation : factures, TVA, règlements, dépenses.

Réf. cahier-des-charges.md:181-193, architecture.md:213, 224-229, 432.

Cycle : BROUILLON (préparé par FINANCES) → A_VALIDER → EMISE (validée par la DIRECTION, numéro
attribué) → PARTIELLEMENT_PAYEE → PAYEE. La DIRECTION peut renvoyer une facture en brouillon avec
un motif. Une facture émise ne se modifie plus. Les montants sont arrondis au franc (ROUND_HALF_UP).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.search import filtrer_par_texte
from apps.core.services import prochain_numero, total_par_mois
from apps.customers.models import Client
from apps.missions.models import Mission, StatutMission

from . import permissions, signals
from .exceptions import (
    ActionFactureNonAutorisee,
    FactureNonFacturable,
    MontantInvalide,
    ReglementInvalide,
    TransitionFactureInterdite,
)
from .models import (
    STATUTS_A_RECOUVRER,
    STATUTS_EMIS,
    CategorieDepense,
    Depense,
    Facture,
    LigneFacture,
    Reglement,
    StatutFacture,
)

ZERO = Decimal("0")
STATUTS_MISSION_FACTURABLES = (StatutMission.LIVREE, StatutMission.CLOTUREE)  # après la livraison


def arrondir_franc(valeur) -> Decimal:
    """Arrondit au franc entier (le FCFA n'a pas de centimes)."""
    return Decimal(valeur).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _verrouiller(objet):
    type(objet)._base_manager.select_for_update().filter(pk=objet.pk).first()
    objet.refresh_from_db()
    return objet


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionFactureNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _exiger_statut(facture: Facture, attendus: tuple, action: str) -> None:
    if facture.statut not in attendus:
        raise TransitionFactureInterdite(
            f"Impossible de {action} : la facture est « {facture.get_statut_display()} »."
        )


# --- lecture ---


def _regle_annote(queryset):
    return queryset.annotate(
        montant_regle=Coalesce(
            Sum("reglements__montant", filter=Q(reglements__is_deleted=False)),
            Value(ZERO),
        )
    ).annotate(reste=F("montant_ttc") - F("montant_regle"))


def factures_queryset() -> QuerySet[Facture]:
    """Factures avec client, mission, montant réglé et reste à recouvrer."""
    # order_by explicite : l'agrégation (règlements) ignore l'ordre par défaut du modèle.
    return _regle_annote(
        Facture.objects.select_related("client", "mission").order_by("-created_at", "-pk")
    )


def est_echue(facture: Facture, aujourd_hui: date | None = None) -> bool:
    """Facture émise, pas soldée, dont la date d'échéance est dépassée."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    return (
        facture.statut in STATUTS_A_RECOUVRER
        and facture.date_echeance is not None
        and facture.date_echeance < aujourd_hui
    )


def montant_regle(facture: Facture) -> Decimal:
    return sum((r.montant for r in facture.reglements.all()), ZERO)


def reste_a_recouvrer(facture: Facture) -> Decimal:
    """Total TTC moins les règlements enregistrés (cahier-des-charges.md:191)."""
    return facture.montant_ttc - montant_regle(facture)


def factures_echues(aujourd_hui: date | None = None) -> QuerySet[Facture]:
    aujourd_hui = aujourd_hui or timezone.localdate()
    return factures_queryset().filter(
        statut__in=STATUTS_A_RECOUVRER, date_echeance__lt=aujourd_hui
    )


def rechercher_factures(
    *,
    recherche: str = "",
    statut: str = "",
    client: Client | None = None,
    echues: bool = False,
    aujourd_hui: date | None = None,
) -> QuerySet[Facture]:
    """Factures filtrées par texte (numéro, client, mission), statut, client, échéance."""
    resultat = factures_queryset()
    if statut in StatutFacture.values:
        resultat = resultat.filter(statut=statut)
    if client is not None:
        resultat = resultat.filter(client=client)
    if echues:
        aujourd_hui = aujourd_hui or timezone.localdate()
        resultat = resultat.filter(statut__in=STATUTS_A_RECOUVRER, date_echeance__lt=aujourd_hui)
    return filtrer_par_texte(
        resultat, recherche, "numero", "client__raison_sociale", "mission__numero"
    )


def creances(aujourd_hui: date | None = None) -> dict:
    """Créances clients : reste à recouvrer total, dont échu (tableau de bord)."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    total = echu = ZERO
    nombre = nombre_echues = 0
    for facture in factures_queryset().filter(statut__in=STATUTS_A_RECOUVRER):
        nombre += 1
        total += facture.reste
        if est_echue(facture, aujourd_hui):
            nombre_echues += 1
            echu += facture.reste
    return {"total": total, "nombre": nombre, "echu": echu, "nombre_echues": nombre_echues}


def missions_facturables() -> QuerySet[Mission]:
    """Missions livrées ou clôturées qui n'ont pas encore de facture (brouillon compris)."""
    return (
        Mission.objects.filter(statut__in=STATUTS_MISSION_FACTURABLES)
        .exclude(factures__is_deleted=False)
        .select_related("client")
        .order_by("-date_livraison", "-pk")
    )


def chiffre_affaires(debut: date, fin: date) -> Decimal:
    """Total HT des factures émises entre ces deux dates (bornes incluses)."""
    return Facture.objects.filter(
        statut__in=STATUTS_EMIS, date_emission__range=(debut, fin)
    ).aggregate(total=Sum("montant_ht"))["total"] or ZERO


def chiffre_affaires_par_mois(debut: date, fin: date) -> dict[tuple[int, int], Decimal]:
    """CA HT des factures émises, par mois (``(année, mois)``), sur la période, en une requête."""
    return total_par_mois(
        Facture.objects.filter(statut__in=STATUTS_EMIS, date_emission__range=(debut, fin)),
        "date_emission",
        "montant_ht",
    )


def encaissements_par_mois(debut: date, fin: date) -> dict[tuple[int, int], Decimal]:
    return total_par_mois(Reglement.objects.filter(date_reglement__range=(debut, fin)), "date_reglement")


def depenses_par_mois(debut: date, fin: date) -> dict[tuple[int, int], Decimal]:
    return total_par_mois(Depense.objects.filter(date_depense__range=(debut, fin)), "date_depense")


def creances_par_anciennete(aujourd_hui: date | None = None) -> list[dict]:
    """Reste à recouvrer réparti selon le retard de paiement : pas encore échu, puis 1-30 j, 31-60 j, plus de 60 j.

    Chaque tranche : ``libelle``, ``montant``, ``nombre``, ``echu`` (bool). Toutes les tranches sont
    présentes, même à 0.
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    tranches = [
        {"libelle": "Pas encore échu", "montant": ZERO, "nombre": 0, "echu": False},
        {"libelle": "En retard de 1 à 30 jours", "montant": ZERO, "nombre": 0, "echu": True},
        {"libelle": "En retard de 31 à 60 jours", "montant": ZERO, "nombre": 0, "echu": True},
        {"libelle": "En retard de plus de 60 jours", "montant": ZERO, "nombre": 0, "echu": True},
    ]
    for facture in factures_queryset().filter(statut__in=STATUTS_A_RECOUVRER):
        retard = (aujourd_hui - facture.date_echeance).days if facture.date_echeance else 0
        rang = 0 if retard <= 0 else 1 if retard <= 30 else 2 if retard <= 60 else 3
        tranches[rang]["montant"] += facture.reste
        tranches[rang]["nombre"] += 1
    return tranches


def encaissements(debut: date, fin: date) -> Decimal:
    """Total des règlements reçus entre ces deux dates (bornes incluses)."""
    return Reglement.objects.filter(date_reglement__range=(debut, fin)).aggregate(
        total=Sum("montant")
    )["total"] or ZERO


# --- préparation d'une facture (FINANCES) ---


def _recalculer(facture: Facture) -> Facture:
    """HT = somme des lignes ; TVA arrondie au franc ; TTC = HT + TVA."""
    ht = sum((ligne.montant_ht for ligne in facture.lignes.all()), ZERO)
    tva = arrondir_franc(ht * facture.taux_tva / 100)
    facture.montant_ht, facture.montant_tva, facture.montant_ttc = ht, tva, ht + tva
    facture.save(update_fields=["montant_ht", "montant_tva", "montant_ttc", "updated_at"])
    return facture


@transaction.atomic
def creer_facture(mission: Mission, acteur) -> Facture:
    """Brouillon de facture pour une mission livrée, avec la TVA et le délai du client.

    TVA à 3 niveaux (cahier-des-charges.md:184-186) : système 18 %, puis taux du client, puis
    ajustable sur la facture tant qu'elle est en brouillon. Une ligne reprend la prestation
    au prix convenu de la mission.
    """
    _exiger_role(acteur, permissions.SAISIE, "préparer une facture")
    mission = _verrouiller(mission)
    if mission.statut not in STATUTS_MISSION_FACTURABLES:
        raise FactureNonFacturable(
            f"La mission {mission.numero} n'est pas encore livrée : elle ne peut pas être facturée."
        )
    if Facture.objects.filter(mission=mission).exists():
        raise FactureNonFacturable(f"La mission {mission.numero} a déjà une facture.")
    client = mission.client
    try:
        with transaction.atomic():
            facture = Facture.objects.create(
                client=client,
                mission=mission,
                taux_tva=client.taux_tva,
                motif_exoneration=client.motif_exoneration,
                delai_paiement_jours=client.delai_paiement_jours,
                cree_par=acteur,
            )
    except IntegrityError as erreur:  # deux préparations simultanées
        raise FactureNonFacturable(f"La mission {mission.numero} a déjà une facture.") from erreur
    LigneFacture.objects.create(
        facture=facture,
        designation=(
            f"Transport {mission.numero} : {mission.lieu_chargement} → {mission.lieu_livraison} "
            f"({mission.nature_marchandise}, {mission.poids_t} t)"
        ),
        quantite=Decimal("1"),
        prix_unitaire_ht=mission.prix_convenu,
        montant_ht=arrondir_franc(mission.prix_convenu),
    )
    return _recalculer(facture)


@transaction.atomic
def ajouter_ligne(
    facture: Facture, acteur, *, designation: str, quantite: Decimal, prix_unitaire_ht: Decimal
) -> LigneFacture:
    """Ajoute une ligne (refacturation de péages, attente...) à un brouillon."""
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "ajouter une ligne")
    designation = designation.strip()
    if not designation:
        raise MontantInvalide("La désignation est obligatoire.")
    quantite, prix_unitaire_ht = Decimal(quantite), Decimal(prix_unitaire_ht)
    if quantite <= 0:
        raise MontantInvalide("La quantité doit être strictement positive.")
    if prix_unitaire_ht < 0:
        raise MontantInvalide("Le prix unitaire ne peut pas être négatif.")
    ligne = LigneFacture.objects.create(
        facture=facture,
        designation=designation,
        quantite=quantite,
        prix_unitaire_ht=prix_unitaire_ht,
        montant_ht=arrondir_franc(quantite * prix_unitaire_ht),
    )
    _recalculer(facture)
    return ligne


@transaction.atomic
def supprimer_ligne(ligne: LigneFacture, acteur) -> Facture:
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    facture = _verrouiller(ligne.facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "supprimer une ligne")
    ligne.delete()
    return _recalculer(facture)


@transaction.atomic
def modifier_conditions(
    facture: Facture,
    acteur,
    *,
    taux_tva: Decimal,
    motif_exoneration: str = "",
    delai_paiement_jours: int,
) -> Facture:
    """TVA et délai de paiement de la facture (3e niveau de TVA), tant qu'elle est en brouillon."""
    _exiger_role(acteur, permissions.SAISIE, "modifier une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "modifier les conditions")
    taux = Decimal(taux_tva)
    if not ZERO <= taux <= Decimal(100):
        raise MontantInvalide("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not motif_exoneration:
        raise MontantInvalide("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    if not 1 <= delai_paiement_jours <= 365:
        raise MontantInvalide("Le délai de paiement doit être compris entre 1 et 365 jours.")
    facture.taux_tva = taux
    facture.motif_exoneration = motif_exoneration if taux == 0 else ""
    facture.delai_paiement_jours = delai_paiement_jours
    facture.save(
        update_fields=["taux_tva", "motif_exoneration", "delai_paiement_jours", "updated_at"]
    )
    return _recalculer(facture)


@transaction.atomic
def abandonner_brouillon(facture: Facture, acteur) -> None:
    """Supprime (logiquement) un brouillon : la mission redevient facturable.

    Comme le numéro n'est attribué qu'à la validation, aucun trou dans la numérotation.
    """
    _exiger_role(acteur, permissions.SAISIE, "abandonner une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "abandonner la facture")
    facture.delete(deleted_by=acteur)


# --- validation (DIRECTION) ---


@transaction.atomic
def soumettre(facture: Facture, acteur) -> Facture:
    """Brouillon → À valider : envoie la facture à la DIRECTION."""
    _exiger_role(acteur, permissions.SAISIE, "soumettre une facture")
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.BROUILLON,), "soumettre la facture")
    if facture.montant_ht <= 0:
        raise MontantInvalide("Une facture à 0 FCFA ne peut pas être soumise.")
    facture.statut = StatutFacture.A_VALIDER
    facture.motif_refus = ""
    facture.save(update_fields=["statut", "motif_refus", "updated_at"])
    signals.emettre(signals.facture_a_valider, facture=facture)
    return facture


@transaction.atomic
def valider(facture: Facture, acteur, *, aujourd_hui: date | None = None) -> Facture:
    """À valider → Émise : numéro ``FACT-AAAA-XXXX``, date d'émission, échéance, créance.

    Réservé à la DIRECTION ; les montants ne bougent plus ensuite.
    """
    _exiger_role(acteur, permissions.VALIDATION, "valider une facture", strict=True)
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.A_VALIDER,), "valider la facture")
    aujourd_hui = aujourd_hui or timezone.localdate()
    facture.numero = prochain_numero("FACT", aujourd_hui.year)
    facture.statut = StatutFacture.EMISE
    facture.date_emission = aujourd_hui
    facture.date_echeance = aujourd_hui + timedelta(days=facture.delai_paiement_jours)
    facture.validee_par = acteur
    facture.date_validation = timezone.now()
    facture.save(
        update_fields=[
            "numero",
            "statut",
            "date_emission",
            "date_echeance",
            "validee_par",
            "date_validation",
            "updated_at",
        ]
    )
    signals.emettre(signals.facture_validee, facture=facture)
    return facture


@transaction.atomic
def refuser(facture: Facture, acteur, *, motif: str) -> Facture:
    """À valider → Brouillon avec un motif : FINANCES corrige puis soumet à nouveau."""
    _exiger_role(acteur, permissions.VALIDATION, "refuser une facture", strict=True)
    _verrouiller(facture)
    _exiger_statut(facture, (StatutFacture.A_VALIDER,), "refuser la facture")
    if not motif.strip():
        raise MontantInvalide("Le motif du refus est obligatoire.")
    facture.statut = StatutFacture.BROUILLON
    facture.motif_refus = motif.strip()
    facture.save(update_fields=["statut", "motif_refus", "updated_at"])
    signals.emettre(signals.facture_refusee, facture=facture, motif=facture.motif_refus)
    return facture


# --- règlements ---


def _statut_selon_reste(facture: Facture) -> str:
    if reste_a_recouvrer(facture) <= 0:
        return StatutFacture.PAYEE
    return (
        StatutFacture.PARTIELLEMENT_PAYEE if montant_regle(facture) > 0 else StatutFacture.EMISE
    )


@transaction.atomic
def enregistrer_reglement(
    facture: Facture,
    acteur,
    *,
    montant: Decimal,
    mode: str,
    date_reglement: date,
    reference: str = "",
) -> Reglement:
    """Acompte ou solde d'une facture émise ; le reste à recouvrer se recalcule.

    Refusé si la facture n'est pas émise, si le montant dépasse le reste à recouvrer ou si la
    date est future ou antérieure à l'émission.
    """
    _exiger_role(acteur, permissions.SAISIE, "enregistrer un règlement")
    _verrouiller(facture)
    if facture.statut not in STATUTS_A_RECOUVRER:
        raise ReglementInvalide(
            f"Impossible d'enregistrer un règlement : la facture est « {facture.get_statut_display()} »."
        )
    montant = Decimal(montant)
    if montant <= 0:
        raise ReglementInvalide("Le montant du règlement doit être strictement positif.")
    reste = reste_a_recouvrer(facture)
    if montant > reste:
        raise ReglementInvalide(
            f"Le montant dépasse le reste à recouvrer ({arrondir_franc(reste)} FCFA)."
        )
    if date_reglement > timezone.localdate():
        raise ReglementInvalide("La date du règlement ne peut pas être dans le futur.")
    if date_reglement < facture.date_emission:
        raise ReglementInvalide("Le règlement ne peut pas précéder la date d'émission de la facture.")
    reglement = Reglement.objects.create(
        facture=facture,
        date_reglement=date_reglement,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        saisi_par=acteur,
    )
    facture.statut = _statut_selon_reste(facture)
    facture.save(update_fields=["statut", "updated_at"])
    return reglement


@transaction.atomic
def annuler_reglement(reglement: Reglement, acteur, *, motif: str) -> Facture:
    """Annule (logiquement) un règlement saisi par erreur ; les jours de retard reprennent."""
    _exiger_role(acteur, permissions.SAISIE, "annuler un règlement")
    if not motif.strip():
        raise ReglementInvalide("Le motif de l'annulation est obligatoire.")
    facture = _verrouiller(reglement.facture)
    reglement.motif_annulation = motif.strip()
    reglement.save(update_fields=["motif_annulation", "updated_at"])
    reglement.delete(deleted_by=acteur)
    facture.statut = _statut_selon_reste(facture)
    facture.save(update_fields=["statut", "updated_at"])
    return facture


# --- dépenses ---


def depenses_queryset() -> QuerySet[Depense]:
    return Depense.objects.select_related("mission", "saisi_par")


def rechercher_depenses(
    *,
    recherche: str = "",
    categorie: str = "",
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> QuerySet[Depense]:
    resultat = depenses_queryset()
    if categorie in CategorieDepense.values:
        resultat = resultat.filter(categorie=categorie)
    if date_debut:
        resultat = resultat.filter(date_depense__gte=date_debut)
    if date_fin:
        resultat = resultat.filter(date_depense__lte=date_fin)
    return filtrer_par_texte(resultat, recherche, "libelle", "reference", "mission__numero")


def total_depenses(debut: date, fin: date) -> Decimal:
    return Depense.objects.filter(date_depense__range=(debut, fin)).aggregate(
        total=Sum("montant")
    )["total"] or ZERO


def depenses_par_categorie(debut: date, fin: date) -> list[dict]:
    """Total par catégorie sur la période (toutes les catégories, y compris à 0)."""
    totaux = dict(
        Depense.objects.filter(date_depense__range=(debut, fin))
        .values_list("categorie")
        .annotate(total=Sum("montant"))
        .order_by()
    )
    return [
        {"code": code, "libelle": libelle, "total": totaux.get(code, ZERO)}
        for code, libelle in CategorieDepense.choices
    ]


@transaction.atomic
def enregistrer_depense(
    acteur,
    *,
    categorie: str,
    date_depense: date,
    libelle: str,
    montant: Decimal,
    mode: str,
    reference: str = "",
    mission: Mission | None = None,
) -> Depense:
    """Saisie d'une dépense (cahier-des-charges.md:192) ; la date ne peut pas être future."""
    _exiger_role(acteur, permissions.SAISIE, "saisir une dépense")
    libelle = libelle.strip()
    if not libelle:
        raise MontantInvalide("Le libellé est obligatoire.")
    montant = Decimal(montant)
    if montant <= 0:
        raise MontantInvalide("Le montant de la dépense doit être strictement positif.")
    if date_depense > timezone.localdate():
        raise MontantInvalide("La date de la dépense ne peut pas être dans le futur.")
    return Depense.objects.create(
        categorie=categorie,
        date_depense=date_depense,
        libelle=libelle,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        mission=mission,
        saisi_par=acteur,
    )
