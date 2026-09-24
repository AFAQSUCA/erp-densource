"""Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

Trésorerie = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties)
et mouvements manuels. Le compte (banque, caisse, mobile money) se déduit du mode de paiement.

Charges du mois (indicateur, distinct de la trésorerie) = dépenses saisies + carburant (pleins)
+ coût des OR clôturés (main-d'œuvre et pièces). Marge nette = CA HT - charges. Les trois
composantes restent visibles séparément. Le rapprochement bancaire n'est pas géré (décision
de l'utilisateur) ; les écritures comptables non plus.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing import permissions as billing_permissions
from apps.billing import services as billing_services
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import (
    COMPTE_DU_MODE,
    STATUTS_A_RECOUVRER,
    CompteTresorerie,
    Depense,
    ModePaiement,
    Reglement,
)
from apps.fuel import services as fuel_services
from apps.inventory import services as inventory_services

from .models import MouvementManuel, SensMouvement

ZERO = Decimal("0")


def _compte(mode: str) -> str:
    return COMPTE_DU_MODE[ModePaiement(mode)]


# --- mouvements manuels ---


@transaction.atomic
def enregistrer_mouvement(
    acteur,
    *,
    sens: str,
    date_mouvement: date,
    libelle: str,
    montant: Decimal,
    mode: str,
    reference: str = "",
) -> MouvementManuel:
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit de saisir un mouvement.")
    libelle = libelle.strip()
    if not libelle:
        raise MontantInvalide("Le libellé est obligatoire.")
    montant = Decimal(montant)
    if montant <= 0:
        raise MontantInvalide("Le montant doit être strictement positif.")
    if date_mouvement > timezone.localdate():
        raise MontantInvalide("La date du mouvement ne peut pas être dans le futur.")
    return MouvementManuel.objects.create(
        sens=sens,
        date_mouvement=date_mouvement,
        libelle=libelle,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        saisi_par=acteur,
    )


@transaction.atomic
def annuler_mouvement(mouvement: MouvementManuel, acteur, *, motif: str) -> None:
    """Annule (logiquement) un mouvement manuel saisi par erreur."""
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit d'annuler un mouvement.")
    if not motif.strip():
        raise MontantInvalide("Le motif de l'annulation est obligatoire.")
    mouvement.motif_annulation = motif.strip()
    mouvement.save(update_fields=["motif_annulation", "updated_at"])
    mouvement.delete(deleted_by=acteur)


# --- lecture ---


def mouvements(
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    sens: str = "",
    compte: str = "",
) -> list[dict]:
    """Journal de trésorerie, du plus récent au plus ancien.

    Chaque ligne : ``date``, ``libelle``, ``sens``, ``montant``, ``mode``, ``compte``,
    ``origine`` (REGLEMENT, DEPENSE ou MANUEL), ``reference``, ``objet`` (pour le lien).
    """
    lignes: list[dict] = []
    reglements = Reglement.objects.select_related("facture__client")
    depenses = Depense.objects.all()
    manuels = MouvementManuel.objects.all()
    if date_debut:
        reglements = reglements.filter(date_reglement__gte=date_debut)
        depenses = depenses.filter(date_depense__gte=date_debut)
        manuels = manuels.filter(date_mouvement__gte=date_debut)
    if date_fin:
        reglements = reglements.filter(date_reglement__lte=date_fin)
        depenses = depenses.filter(date_depense__lte=date_fin)
        manuels = manuels.filter(date_mouvement__lte=date_fin)
    if sens != SensMouvement.SORTIE:
        for r in reglements:
            lignes.append(
                {
                    "date": r.date_reglement,
                    "libelle": f"Règlement {r.facture.numero} · {r.facture.client.raison_sociale}",
                    "sens": SensMouvement.ENTREE,
                    "montant": r.montant,
                    "mode": r.mode,
                    "mode_libelle": r.get_mode_display(),
                    "reference": r.reference,
                    "origine": "REGLEMENT",
                    "objet": r,
                    "pk": r.pk,
                }
            )
    if sens != SensMouvement.ENTREE:
        for d in depenses:
            lignes.append(
                {
                    "date": d.date_depense,
                    "libelle": f"Dépense : {d.libelle}",
                    "sens": SensMouvement.SORTIE,
                    "montant": d.montant,
                    "mode": d.mode,
                    "mode_libelle": d.get_mode_display(),
                    "reference": d.reference,
                    "origine": "DEPENSE",
                    "objet": d,
                    "pk": d.pk,
                }
            )
    for m in manuels:
        if sens and m.sens != sens:
            continue
        lignes.append(
            {
                "date": m.date_mouvement,
                "libelle": m.libelle,
                "sens": m.sens,
                "montant": m.montant,
                "mode": m.mode,
                "mode_libelle": m.get_mode_display(),
                "reference": m.reference,
                "origine": "MANUEL",
                "objet": m,
                "pk": m.pk,
            }
        )
    for ligne in lignes:
        ligne["compte"] = _compte(ligne["mode"])
        ligne["compte_libelle"] = CompteTresorerie(ligne["compte"]).label
    if compte:
        lignes = [ligne for ligne in lignes if ligne["compte"] == compte]
    lignes.sort(key=lambda l: (l["date"], l["origine"], l["pk"]), reverse=True)
    return lignes


def _somme(queryset, champ: str = "montant") -> Decimal:
    return queryset.aggregate(total=Sum(champ))["total"] or ZERO


def soldes_par_compte() -> dict:
    """Solde en temps réel de chaque compte (entrées - sorties, depuis l'origine) et total."""
    soldes = {code: ZERO for code in CompteTresorerie.values}
    for reglement_mode, total in Reglement.objects.values_list("mode").annotate(t=Sum("montant")).order_by():
        soldes[_compte(reglement_mode)] += total
    for mode, total in Depense.objects.values_list("mode").annotate(t=Sum("montant")).order_by():
        soldes[_compte(mode)] -= total
    for mode, sens, total in (
        MouvementManuel.objects.values_list("mode", "sens").annotate(t=Sum("montant")).order_by()
    ):
        soldes[_compte(mode)] += total if sens == SensMouvement.ENTREE else -total
    soldes["total"] = sum(soldes.values(), ZERO)
    return soldes


def versements_attendus(aujourd_hui: date | None = None) -> dict:
    """Factures émises et pas soldées : les versements que la Finance doit confirmer à leur arrivée.

    Ce n'est **pas** de l'argent en caisse : le solde par compte reste celui des règlements réellement
    enregistrés. Tant que la Finance n'a pas confirmé le versement (``billing.enregistrer_reglement``,
    depuis l'écran de confirmation), la facture attend ici ; une fois confirmé, il devient une entrée du
    journal. Les plus en retard d'abord, puis par échéance.

    ``lignes`` : ``facture``, ``reste`` (à recouvrer), ``echue``, ``jours`` (de retard si échue, avant
    l'échéance sinon ; ``None`` sans échéance). ``total``, ``echu`` et ``a_venir`` en FCFA.
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    lignes = []
    total = echu = ZERO
    factures = billing_services.factures_queryset().filter(statut__in=STATUTS_A_RECOUVRER)
    for facture in sorted(factures, key=lambda f: (f.date_echeance is None, f.date_echeance or aujourd_hui, f.pk)):
        est_echue = billing_services.est_echue(facture, aujourd_hui)
        lignes.append({
            "facture": facture,
            "reste": facture.reste,
            "echue": est_echue,
            "jours": abs((aujourd_hui - facture.date_echeance).days) if facture.date_echeance else None,
        })
        total += facture.reste
        if est_echue:
            echu += facture.reste
    return {"lignes": lignes, "nombre": len(lignes), "total": total, "echu": echu, "a_venir": total - echu}


def confirmer_versement(facture, acteur, *, montant: Decimal, mode: str, date_reglement: date, reference: str = ""):
    """Confirme qu'un versement attendu a bien été reçu : l'enregistre comme règlement de la facture,
    donc comme **entrée** de trésorerie sur le compte du mode de paiement.

    Retourne ``(règlement, compte)``. Mêmes contrôles et mêmes droits que tout règlement
    (``billing.enregistrer_reglement`` : facture émise, montant ≤ reste à recouvrer, date valable).
    """
    reglement = billing_services.enregistrer_reglement(
        facture, acteur, montant=montant, mode=mode, date_reglement=date_reglement, reference=reference
    )
    return reglement, CompteTresorerie(_compte(mode))


def synthese_periode(debut: date, fin: date) -> dict:
    """Entrées, sorties et variation de la trésorerie sur la période (bornes incluses)."""
    entrees = billing_services.encaissements(debut, fin) + _somme(
        MouvementManuel.objects.filter(
            sens=SensMouvement.ENTREE, date_mouvement__range=(debut, fin)
        )
    )
    sorties = billing_services.total_depenses(debut, fin) + _somme(
        MouvementManuel.objects.filter(
            sens=SensMouvement.SORTIE, date_mouvement__range=(debut, fin)
        )
    )
    return {"entrees": entrees, "sorties": sorties, "variation": entrees - sorties}


def charges(debut: date, fin: date) -> dict:
    """Charges de la période : dépenses saisies, carburant, coût des OR clôturés."""
    depenses = billing_services.total_depenses(debut, fin)
    carburant = fuel_services.cout_carburant(debut, fin)
    maintenance = inventory_services.cout_des_or_clotures(debut, fin)
    return {
        "depenses": depenses,
        "carburant": carburant,
        "maintenance": maintenance,
        "total": depenses + carburant + maintenance,
    }


def historique_mensuel(jour: date | None = None, *, mois: int = 6, courant: dict | None = None) -> list[dict]:
    """CA HT facturé, encaissé et charges des ``mois`` derniers mois, du plus ancien au mois de ``jour``.

    Le mois de ``jour`` s'arrête à ``jour`` (comme les indicateurs du mois) ; ``courant`` (les valeurs
    ``chiffre_affaires``, ``encaisse`` et ``charges`` déjà calculées pour ce mois) évite de les relire.
    Chaque ligne : ``debut``, ``fin``, ``chiffre_affaires``, ``encaisse``, ``charges``.
    """
    jour = jour or timezone.localdate()
    lignes = []
    annee, numero = jour.year, jour.month
    for decalage in range(mois - 1, -1, -1):
        indice = annee * 12 + (numero - 1) - decalage
        an, mo = divmod(indice, 12)
        debut = date(an, mo + 1, 1)
        fin = jour if decalage == 0 else debut.replace(day=calendar.monthrange(an, mo + 1)[1])
        if decalage == 0 and courant is not None:
            valeurs = courant
        else:
            valeurs = {
                "chiffre_affaires": billing_services.chiffre_affaires(debut, fin),
                "encaisse": billing_services.encaissements(debut, fin),
                "charges": charges(debut, fin)["total"],
            }
        lignes.append({"debut": debut, "fin": fin, **valeurs})
    return lignes


def indicateurs(debut: date, fin: date, *, aujourd_hui: date | None = None) -> dict:
    """Indicateurs financiers de la période (cahier-des-charges.md:227-228, 199)."""
    ca = billing_services.chiffre_affaires(debut, fin)
    charges_periode = charges(debut, fin)
    return {
        "chiffre_affaires": ca,
        "encaisse": billing_services.encaissements(debut, fin),
        "charges": charges_periode,
        "marge_nette": ca - charges_periode["total"],
        "creances": billing_services.creances(aujourd_hui),
        "tresorerie": soldes_par_compte()["total"],
    }
