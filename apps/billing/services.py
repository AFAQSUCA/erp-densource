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

from apps.audit import services as audit_services
from apps.core.search import filtrer_par_texte
from apps.core.services import prochain_numero, total_par_mois
from apps.customers.models import Client
from apps.fleet.models import Vehicule
from apps.missions import services as missions_services
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
    DUREE_VALIDITE_PROFORMA_JOURS,
    STATUTS_A_RECOUVRER,
    STATUTS_EMIS,
    STATUTS_PROFORMA_MODIFIABLES,
    CATEGORIES_AUTOMATIQUES,
    CategorieDepense,
    Depense,
    Facture,
    LigneFacture,
    ModePaiement,
    Proforma,
    Reglement,
    StatutFacture,
    StatutProforma,
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
    signals.emettre(signals.reglement_enregistre, reglement=reglement)
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
def comptabiliser_depense_automatique(
    *,
    origine: str,
    origine_id: int,
    categorie: str,
    date_depense: date,
    libelle: str,
    montant: Decimal,
    reference: str = "",
    mode: str = ModePaiement.ESPECES,
    mission: Mission | None = None,
    vehicule: Vehicule | None = None,
) -> Depense | None:
    """Crée la dépense d'un plein, d'un achat de pièces, d'une main-d'œuvre d'OR, d'un frais de
    mission confirmé ou d'un ordre de décaissement exécuté (une seule fois par source).

    Appelée par les récepteurs de ``finance`` dans la transaction de l'opération d'origine : si la dépense
    ne peut pas être écrite, l'opération est annulée plutôt que de laisser une sortie d'argent non comptée.
    Mode de paiement par défaut : espèces (caisse), que la Finance corrige ensuite si besoin
    (:func:`changer_mode_depense`). Un montant nul ne crée rien. Idempotent : rejouer la même source
    renvoie la dépense existante. ``mission`` relie la dépense à la mission d'origine (frais de mission,
    R4) ; ``vehicule`` (plein, main-d'œuvre d'OR) sert au suivi par enveloppe (R2).
    """
    montant = Decimal(montant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if montant <= 0:
        return None
    depense, _ = Depense.objects.get_or_create(
        origine=origine,
        origine_id=origine_id,
        defaults={
            "categorie": categorie,
            "date_depense": date_depense,
            "libelle": libelle[:200],
            "montant": montant,
            "mode": mode,
            "reference": reference[:100],
            "mission": mission,
            "vehicule": vehicule,
        },
    )
    return depense


def changer_mode_depense(depense: Depense, acteur, *, mode: str) -> Depense:
    """La Finance corrige le mode de paiement d'une dépense automatique (elle en déduit le compte débité)."""
    _exiger_role(acteur, permissions.SAISIE, "modifier une dépense")
    if not depense.est_automatique:
        raise ActionFactureNonAutorisee("Seules les dépenses créées automatiquement se corrigent ici.")
    if mode not in ModePaiement.values:
        raise MontantInvalide("Mode de paiement inconnu.")
    depense.mode = mode
    depense.save(update_fields=["mode", "updated_at"])
    return depense


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
    if categorie in CATEGORIES_AUTOMATIQUES:
        raise MontantInvalide(
            "Le carburant, les pièces et la main-d'œuvre des réparations se comptabilisent tout seuls "
            "(plein, entrée de stock, clôture d'OR) : ne les saisissez pas ici."
        )
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


# --- devis (R5 : le chargé clientèle fixe le prix, la FINANCES et, au-delà d'un seuil,
# la DIRECTION le valident — R1 fusionnée) ---


def _recalculer_proforma(proforma: Proforma) -> Proforma:
    """HT = prix convenu ; TVA arrondie au franc ; TTC = HT + TVA."""
    ht = arrondir_franc(proforma.prix_convenu)
    tva = arrondir_franc(ht * proforma.taux_tva / 100)
    proforma.montant_ht, proforma.montant_tva, proforma.montant_ttc = ht, tva, ht + tva
    proforma.save(update_fields=["montant_ht", "montant_tva", "montant_ttc", "updated_at"])
    return proforma


def proformas_queryset() -> QuerySet[Proforma]:
    return Proforma.objects.select_related("client", "cree_par")


def rechercher_proformas(
    *, recherche: str = "", statut: str = "", client: Client | None = None
) -> QuerySet[Proforma]:
    resultat = proformas_queryset()
    if statut in StatutProforma.values:
        resultat = resultat.filter(statut=statut)
    if client is not None:
        resultat = resultat.filter(client=client)
    return filtrer_par_texte(
        resultat, recherche, "numero", "client__raison_sociale", "lieu_chargement", "lieu_livraison"
    )


def historique_proforma(proforma: Proforma) -> QuerySet:
    """Historique des modifications (préparation, contre-propositions, validations)."""
    return audit_services.historique("Proforma", proforma.pk)


@transaction.atomic
def creer_proforma(
    acteur,
    *,
    client: Client,
    lieu_chargement: str,
    lieu_livraison: str,
    nature_marchandise: str,
    poids_t: Decimal,
    prix_convenu: Decimal,
    date_depart_souhaitee: date | None = None,
) -> Proforma:
    """Brouillon de devis : trajet et prix fixés par le chargé clientèle, TVA reprise du client."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "préparer un devis")
    poids_t, prix_convenu = Decimal(poids_t), Decimal(prix_convenu)
    if poids_t <= 0:
        raise MontantInvalide("Le poids doit être strictement positif.")
    if prix_convenu < 0:
        raise MontantInvalide("Le prix convenu ne peut pas être négatif.")
    proforma = Proforma.objects.create(
        client=client,
        lieu_chargement=lieu_chargement,
        lieu_livraison=lieu_livraison,
        nature_marchandise=nature_marchandise,
        poids_t=poids_t,
        prix_convenu=prix_convenu,
        date_depart_souhaitee=date_depart_souhaitee,
        taux_tva=client.taux_tva,
        motif_exoneration=client.motif_exoneration,
        cree_par=acteur,
    )
    return _recalculer_proforma(proforma)


@transaction.atomic
def modifier_proforma(
    proforma: Proforma,
    acteur,
    *,
    lieu_chargement: str,
    lieu_livraison: str,
    nature_marchandise: str,
    poids_t: Decimal,
    prix_convenu: Decimal,
    taux_tva: Decimal,
    motif_exoneration: str = "",
    date_depart_souhaitee: date | None = None,
) -> Proforma:
    """Trajet, marchandise, prix et TVA, tant que le devis est modifiable (brouillon ou contre-proposé)."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "modifier un devis")
    _verrouiller(proforma)
    _exiger_statut(proforma, STATUTS_PROFORMA_MODIFIABLES, "modifier le devis")
    poids_t, prix_convenu, taux = Decimal(poids_t), Decimal(prix_convenu), Decimal(taux_tva)
    if poids_t <= 0:
        raise MontantInvalide("Le poids doit être strictement positif.")
    if prix_convenu < 0:
        raise MontantInvalide("Le prix convenu ne peut pas être négatif.")
    if not ZERO <= taux <= Decimal(100):
        raise MontantInvalide("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not motif_exoneration:
        raise MontantInvalide("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    proforma.lieu_chargement = lieu_chargement
    proforma.lieu_livraison = lieu_livraison
    proforma.nature_marchandise = nature_marchandise
    proforma.poids_t = poids_t
    proforma.prix_convenu = prix_convenu
    proforma.date_depart_souhaitee = date_depart_souhaitee
    proforma.taux_tva = taux
    proforma.motif_exoneration = motif_exoneration if taux == 0 else ""
    proforma.save(
        update_fields=[
            "lieu_chargement", "lieu_livraison", "nature_marchandise", "poids_t", "prix_convenu",
            "date_depart_souhaitee", "taux_tva", "motif_exoneration", "updated_at",
        ]
    )
    return _recalculer_proforma(proforma)


@transaction.atomic
def abandonner_proforma(proforma: Proforma, acteur) -> None:
    """Supprime (logiquement) un devis pas encore soumis à la validation."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "abandonner un devis")
    _verrouiller(proforma)
    _exiger_statut(proforma, STATUTS_PROFORMA_MODIFIABLES, "abandonner le devis")
    proforma.delete(deleted_by=acteur)


@transaction.atomic
def soumettre_proforma(proforma: Proforma, acteur) -> Proforma:
    """Brouillon ou contre-proposé → Soumis : envoie le devis à la FINANCES."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "soumettre un devis")
    _verrouiller(proforma)
    _exiger_statut(proforma, STATUTS_PROFORMA_MODIFIABLES, "soumettre le devis")
    if proforma.montant_ttc <= 0:
        raise MontantInvalide("Un devis à 0 FCFA ne peut pas être soumis.")
    proforma.statut = StatutProforma.SOUMISE
    proforma.motif_contre_proposition = ""
    proforma.save(update_fields=["statut", "motif_contre_proposition", "updated_at"])
    signals.emettre(signals.proforma_a_valider, sender=Proforma, proforma=proforma)
    return proforma


def _emettre_proforma(proforma: Proforma, aujourd_hui: date) -> Proforma:
    """Attribue le numéro et passe le devis en Validée (dernière étape des deux parcours)."""
    proforma.numero = prochain_numero("PRO", aujourd_hui.year)
    proforma.statut = StatutProforma.VALIDEE
    proforma.save(
        update_fields=[
            "numero", "statut", "valide_par_finances", "date_validation_finances",
            "valide_par_direction", "date_validation_direction", "updated_at",
        ]
    )
    signals.emettre(signals.proforma_validee, sender=Proforma, proforma=proforma)
    return proforma


@transaction.atomic
def valider_proforma(proforma: Proforma, acteur, *, aujourd_hui: date | None = None) -> Proforma:
    """La FINANCES valide le prix : émission directe sous le seuil, sinon transmission à la DIRECTION."""
    _exiger_role(acteur, permissions.PROFORMA_VALIDATION_FINANCES, "valider un devis", strict=True)
    _verrouiller(proforma)
    _exiger_statut(proforma, (StatutProforma.SOUMISE,), "valider le devis")
    proforma.valide_par_finances = acteur
    proforma.date_validation_finances = timezone.now()
    if proforma.requiert_direction:
        proforma.statut = StatutProforma.EN_ATTENTE_DIRECTION
        proforma.save(
            update_fields=["statut", "valide_par_finances", "date_validation_finances", "updated_at"]
        )
        signals.emettre(signals.proforma_en_attente_direction, sender=Proforma, proforma=proforma)
        return proforma
    return _emettre_proforma(proforma, aujourd_hui or timezone.localdate())


@transaction.atomic
def valider_proforma_direction(proforma: Proforma, acteur, *, aujourd_hui: date | None = None) -> Proforma:
    """La DIRECTION valide un devis dont le montant dépasse le seuil (R1 fusionnée)."""
    _exiger_role(acteur, permissions.PROFORMA_VALIDATION_DIRECTION, "valider un devis", strict=True)
    _verrouiller(proforma)
    _exiger_statut(proforma, (StatutProforma.EN_ATTENTE_DIRECTION,), "valider le devis")
    proforma.valide_par_direction = acteur
    proforma.date_validation_direction = timezone.now()
    return _emettre_proforma(proforma, aujourd_hui or timezone.localdate())


_ROLE_CONTRE_PROPOSITION = {
    StatutProforma.SOUMISE: permissions.PROFORMA_VALIDATION_FINANCES,
    StatutProforma.EN_ATTENTE_DIRECTION: permissions.PROFORMA_VALIDATION_DIRECTION,
}


@transaction.atomic
def contre_proposer_proforma(proforma: Proforma, acteur, *, motif: str) -> Proforma:
    """La FINANCES (devis soumis) ou la DIRECTION (devis en attente) conteste le prix.

    Renvoie le devis au chargé clientèle avec un motif plutôt que de le refuser
    définitivement : il ajuste le prix puis le soumet à nouveau.
    """
    _verrouiller(proforma)
    _exiger_statut(
        proforma,
        (StatutProforma.SOUMISE, StatutProforma.EN_ATTENTE_DIRECTION),
        "contre-proposer sur le devis",
    )
    _exiger_role(
        acteur, _ROLE_CONTRE_PROPOSITION[proforma.statut], "contre-proposer un devis", strict=True
    )
    if not motif.strip():
        raise MontantInvalide("Le motif de la contre-proposition est obligatoire.")
    proforma.statut = StatutProforma.CONTRE_PROPOSEE
    proforma.motif_contre_proposition = motif.strip()
    proforma.save(update_fields=["statut", "motif_contre_proposition", "updated_at"])
    signals.emettre(
        signals.proforma_contre_proposee,
        sender=Proforma,
        proforma=proforma,
        motif=proforma.motif_contre_proposition,
    )
    return proforma


@transaction.atomic
def envoyer_proforma_au_client(
    proforma: Proforma, acteur, *, aujourd_hui: date | None = None
) -> Proforma:
    """Devis validé → envoyé au client : la validité de 30 jours court à partir de l'envoi."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "envoyer un devis au client")
    _verrouiller(proforma)
    _exiger_statut(proforma, (StatutProforma.VALIDEE,), "envoyer le devis au client")
    aujourd_hui = aujourd_hui or timezone.localdate()
    proforma.statut = StatutProforma.ENVOYEE_CLIENT
    proforma.date_envoi = aujourd_hui
    proforma.date_validite = aujourd_hui + timedelta(days=DUREE_VALIDITE_PROFORMA_JOURS)
    proforma.save(update_fields=["statut", "date_envoi", "date_validite", "updated_at"])
    return proforma


@transaction.atomic
def enregistrer_decision_client(
    proforma: Proforma, acteur, *, acceptee: bool, motif: str = ""
) -> Proforma:
    """Le chargé clientèle enregistre la réponse du client à un devis envoyé."""
    _exiger_role(acteur, permissions.PROFORMA_SAISIE, "enregistrer la décision du client")
    _verrouiller(proforma)
    _exiger_statut(proforma, (StatutProforma.ENVOYEE_CLIENT,), "enregistrer la décision du client")
    if not acceptee and not motif.strip():
        raise MontantInvalide("Le motif du refus du client est obligatoire.")
    proforma.statut = StatutProforma.ACCEPTEE if acceptee else StatutProforma.REFUSEE
    proforma.motif_refus_client = motif.strip() if not acceptee else ""
    proforma.save(update_fields=["statut", "motif_refus_client", "updated_at"])
    return proforma


@transaction.atomic
def convertir_en_mission(proforma: Proforma) -> Mission:
    """Mission créée depuis un devis accepté (R6) : trajet, marchandise, poids et prix recopiés
    tels quels ; le devis devient une archive figée (« 1 devis = 1 mission »).

    Le prix repris est le HT du devis, comme celui d'une mission créée à la main : la facture
    calculera la TVA à son tour, avec le taux du client en vigueur au moment de la facturation.
    Le contrôle de rôle relève de la création de la mission (``missions.permissions.CREATION``),
    pas de ce module : cette fonction n'est appelée que depuis ce flux déjà autorisé. Orchestrée
    ici (et non dans ``missions``) car le graphe de dépendance des apps interdit à ``missions``
    de dépendre de ``billing`` (architecture.md:95-163) — l'inverse est permis.
    """
    _verrouiller(proforma)
    _exiger_statut(proforma, (StatutProforma.ACCEPTEE,), "convertir le devis en mission")
    mission = missions_services.creer_mission(
        client=proforma.client,
        lieu_chargement=proforma.lieu_chargement,
        lieu_livraison=proforma.lieu_livraison,
        nature_marchandise=proforma.nature_marchandise,
        poids_t=proforma.poids_t,
        prix_convenu=proforma.prix_convenu,
        date_depart_prevue=proforma.date_depart_souhaitee,
    )
    mission.proforma = proforma
    mission.save(update_fields=["proforma", "updated_at"])
    proforma.statut = StatutProforma.CONVERTIE
    proforma.save(update_fields=["statut", "updated_at"])
    return mission


def expirer_proformas(aujourd_hui: date | None = None) -> int:
    """Devis envoyés au client dont la validité de 30 jours est dépassée sans réponse."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    expirees = 0
    for proforma in Proforma.objects.filter(
        statut=StatutProforma.ENVOYEE_CLIENT, date_validite__lt=aujourd_hui
    ):
        proforma.statut = StatutProforma.EXPIREE
        proforma.save(update_fields=["statut", "updated_at"])
        signals.emettre(signals.proforma_expiree, sender=Proforma, proforma=proforma)
        expirees += 1
    return expirees
