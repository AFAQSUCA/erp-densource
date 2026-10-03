"""Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

Trésorerie = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties)
et mouvements manuels. Le compte (banque, caisse, mobile money) se déduit du mode de paiement.

Charges du mois (indicateur, distinct de la trésorerie) = dépenses saisies + carburant (pleins)
+ coût des OR clôturés (main-d'œuvre et pièces). Marge nette = CA HT - charges. Les trois
composantes restent visibles séparément.

Rapprochement bancaire (avenant-comptabilite-autonomie.md § Lot G) : confronte les lignes du
relevé bancaire, saisies à la main, aux mouvements de trésorerie déjà enregistrés sur le compte
Banque (``mouvements(compte="BANQUE")``) — jamais la Caisse ni le Mobile Money, un relevé bancaire
ne concerne que la banque.
"""

from __future__ import annotations

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
    CategorieDepense,
    CompteTresorerie,
    Depense,
    ModePaiement,
    OrigineDepense,
    Reglement,
)
from apps.core.services import debuts_de_mois, fin_de_mois
from apps.fuel.models import Plein
from apps.garage.models import OrdreReparation, StatutOr
from apps.inventory.models import MouvementStock, TypeMouvement

from . import signals
from .models import LigneReleve, MouvementManuel, NatureMouvement, SensMouvement

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
    nature: str = NatureMouvement.AUTRE,
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
    if nature not in NatureMouvement.values:
        raise MontantInvalide("Nature de mouvement inconnue.")
    mouvement = MouvementManuel.objects.create(
        sens=sens,
        nature=nature,
        date_mouvement=date_mouvement,
        libelle=libelle,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        saisi_par=acteur,
    )
    signals.mouvement_a_comptabiliser.send(sender=MouvementManuel, mouvement=mouvement)
    return mouvement


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


# --- rapprochement bancaire (Lot G) ---


def _mouvements_deja_pointes() -> set[tuple[str, int]]:
    return set(
        LigneReleve.objects.filter(pointee=True).values_list("mouvement_origine", "mouvement_id")
    )


def saisir_ligne_releve(
    acteur, *, date_operation: date, libelle: str, montant: Decimal, sens: str, reference: str = ""
) -> LigneReleve:
    """Ajoute une ligne au relevé bancaire (pas encore pointée) — saisie manuelle, le relevé n'est
    importé depuis aucun format de fichier (décision confirmée avec l'entreprise)."""
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit de saisir une ligne de relevé.")
    libelle = libelle.strip()
    if not libelle:
        raise MontantInvalide("Le libellé est obligatoire.")
    montant = Decimal(montant)
    if montant <= 0:
        raise MontantInvalide("Le montant doit être strictement positif.")
    if sens not in SensMouvement.values:
        raise MontantInvalide("Sens inconnu.")
    if date_operation > timezone.localdate():
        raise MontantInvalide("La date ne peut pas être dans le futur.")
    return LigneReleve.objects.create(
        date_operation=date_operation,
        libelle=libelle,
        montant=montant,
        sens=sens,
        reference=reference.strip(),
        saisi_par=acteur,
    )


def suggestions_pointage(ligne: LigneReleve) -> list[dict]:
    """Mouvements de trésorerie Banque non encore pointés, de même sens et montant que la ligne de
    relevé, triés par date la plus proche — l'accountant confirme ou cherche ailleurs."""
    deja_pointes = _mouvements_deja_pointes()
    candidats = [
        m
        for m in mouvements(compte=CompteTresorerie.BANQUE)
        if m["sens"] == ligne.sens
        and m["montant"] == ligne.montant
        and (m["origine"], m["pk"]) not in deja_pointes
    ]
    candidats.sort(key=lambda m: abs((m["date"] - ligne.date_operation).days))
    return candidats


@transaction.atomic
def pointer_ligne_releve(ligne: LigneReleve, acteur, *, origine: str, mouvement_id: int) -> LigneReleve:
    """Associe la ligne de relevé à un mouvement de trésorerie précis (un règlement, une dépense
    ou un mouvement manuel), identifié par son origine et son identifiant."""
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit de pointer une ligne de relevé.")
    if origine not in {"REGLEMENT", "DEPENSE", "MANUEL"}:
        raise MontantInvalide("Origine de mouvement inconnue.")
    if (origine, mouvement_id) in _mouvements_deja_pointes():
        raise MontantInvalide("Ce mouvement est déjà pointé sur une autre ligne du relevé.")
    ligne.pointee = True
    ligne.mouvement_origine = origine
    ligne.mouvement_id = mouvement_id
    ligne.save(update_fields=["pointee", "mouvement_origine", "mouvement_id", "updated_at"])
    return ligne


def depointer_ligne_releve(ligne: LigneReleve, acteur) -> LigneReleve:
    """Annule le pointage d'une ligne, par exemple pour corriger une association faite par erreur."""
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit de dépointer une ligne de relevé.")
    ligne.pointee = False
    ligne.mouvement_origine = ""
    ligne.mouvement_id = None
    ligne.save(update_fields=["pointee", "mouvement_origine", "mouvement_id", "updated_at"])
    return ligne


def rapprochement_bancaire(*, debut: date, fin: date) -> dict:
    """État du rapprochement sur la période : solde du relevé, solde des mouvements Banque déjà
    enregistrés, écart entre les deux, et le détail de chaque côté non encore pointé (un écart
    persistant après pointage signale une opération jamais saisie — frais bancaires, par exemple —
    à corriger via une écriture manuelle existante, pas un nouveau mécanisme ici)."""
    lignes_releve = list(
        LigneReleve.objects.filter(date_operation__gte=debut, date_operation__lte=fin)
    )
    mouvements_banque = mouvements(date_debut=debut, date_fin=fin, compte=CompteTresorerie.BANQUE)
    deja_pointes = _mouvements_deja_pointes()
    solde_releve = sum(
        (l.montant if l.sens == SensMouvement.ENTREE else -l.montant for l in lignes_releve), ZERO
    )
    solde_comptable = sum(
        (m["montant"] if m["sens"] == SensMouvement.ENTREE else -m["montant"] for m in mouvements_banque),
        ZERO,
    )
    return {
        "debut": debut,
        "fin": fin,
        "lignes_releve": lignes_releve,
        "lignes_non_pointees": [l for l in lignes_releve if not l.pointee],
        "mouvements_banque": mouvements_banque,
        "mouvements_non_pointes": [
            m for m in mouvements_banque if (m["origine"], m["pk"]) not in deja_pointes
        ],
        "solde_releve": solde_releve,
        "solde_comptable": solde_comptable,
        "ecart": solde_releve - solde_comptable,
    }


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
    """Charges de la période = toutes les dépenses, y compris celles créées automatiquement.

    Un plein, un achat de pièces, la main-d'œuvre d'un OR clôturé et un frais de mission confirmé
    (avance, dépense prévue, imprévu — R4) sont des dépenses comme les autres (``finance.receivers``) :
    la page Dépenses, la trésorerie et ces charges donnent le même total. Ventilation : ``carburant``,
    ``pieces`` (achetées), ``main_oeuvre`` (des OR), ``maintenance`` (pièces + main-d'œuvre),
    ``frais_mission`` et ``depenses`` (le reste : péages, frais, saisies à la main).
    """
    par_categorie = {c["code"]: c["total"] for c in billing_services.depenses_par_categorie(debut, fin)}
    carburant = par_categorie[CategorieDepense.CARBURANT]
    pieces = par_categorie[CategorieDepense.PIECES]
    main_oeuvre = par_categorie[CategorieDepense.MAINTENANCE]
    frais_mission = par_categorie[CategorieDepense.FRAIS_MISSION]
    total = sum(par_categorie.values(), ZERO)
    return {
        "depenses": total - carburant - pieces - main_oeuvre - frais_mission,
        "carburant": carburant,
        "pieces": pieces,
        "main_oeuvre": main_oeuvre,
        "maintenance": pieces + main_oeuvre,
        "frais_mission": frais_mission,
        "total": total,
    }


def historique_mensuel(jour: date | None = None, *, mois: int = 6, courant: dict | None = None) -> list[dict]:
    """CA HT facturé, encaissé et charges des ``mois`` derniers mois, du plus ancien au mois de ``jour``.

    Le mois de ``jour`` s'arrête à ``jour`` (comme les indicateurs du mois) ; ``courant`` (les valeurs
    ``chiffre_affaires``, ``encaisse`` et ``charges`` déjà calculées pour ce mois) évite de les relire.
    Chaque ligne : ``debut``, ``fin``, ``chiffre_affaires``, ``encaisse``, ``charges``. Trois requêtes en
    tout, quel que soit le nombre de mois.
    """
    jour = jour or timezone.localdate()
    debuts = debuts_de_mois(jour, mois)
    premier = debuts[0]
    ca = billing_services.chiffre_affaires_par_mois(premier, jour)
    encaisse = billing_services.encaissements_par_mois(premier, jour)
    depenses = billing_services.depenses_par_mois(premier, jour)
    lignes = []
    for debut in debuts:
        est_courant = debut == debuts[-1]
        fin = jour if est_courant else fin_de_mois(debut)
        cle = (debut.year, debut.month)
        valeurs = courant if est_courant and courant is not None else {
            "chiffre_affaires": ca.get(cle, ZERO),
            "encaisse": encaisse.get(cle, ZERO),
            "charges": depenses.get(cle, ZERO),
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


# --- reprise de l'historique du parc auto (commande comptabiliser_historique_parc_auto) ---


def reprendre_depenses_parc_auto(*, depuis: date | None = None) -> dict:
    """Comptabilise après coup les pleins, achats de pièces et main-d'œuvre d'OR déjà enregistrés,
    exactement comme ``finance.receivers`` le fait pour les nouveaux (dépense automatique en espèces,
    la Finance corrige ensuite le mode de paiement).

    ``depuis`` : ne reprend que les sources à partir de cette date (bornes incluses). À utiliser si un
    solde d'ouverture a déjà été saisi en trésorerie pour une date donnée : les mouvements antérieurs sont
    alors déjà compris dedans, les reprendre les compterait une seconde fois. Sans ``depuis``, tout
    l'historique est repris. Rejouable sans double compte (une dépense par source, comme le mécanisme
    normal) : relancer la commande après une reprise partielle ne recrée pas ce qui existe déjà.

    Retourne le nombre de dépenses créées par catégorie et le nombre de sources déjà comptabilisées.
    """
    compteurs = {"carburant": 0, "pieces": 0, "main_oeuvre": 0, "deja_comptabilisees": 0}

    def _traiter(*, origine, origine_id, cle, **kwargs):
        if Depense.objects.filter(origine=origine, origine_id=origine_id).exists():
            compteurs["deja_comptabilisees"] += 1
            return
        if billing_services.comptabiliser_depense_automatique(origine=origine, origine_id=origine_id, **kwargs):
            compteurs[cle] += 1

    pleins = Plein.objects.select_related("vehicule")
    if depuis:
        pleins = pleins.filter(date_plein__gte=depuis)
    for plein in pleins:
        _traiter(
            origine=OrigineDepense.PLEIN, origine_id=plein.pk, cle="carburant",
            categorie=CategorieDepense.CARBURANT, date_depense=plein.date_plein,
            libelle=(
                f"Carburant · {plein.vehicule.immatriculation} · {plein.station} "
                f"({plein.quantite_litres.normalize():f} L)"
            ),
            montant=plein.quantite_litres * plein.prix_unitaire, reference=plein.numero_ticket,
        )

    entrees = MouvementStock.objects.filter(type_mouvement=TypeMouvement.ENTREE).select_related("article")
    if depuis:
        entrees = entrees.filter(date_mouvement__date__gte=depuis)
    for mouvement in entrees:
        article = mouvement.article
        _traiter(
            origine=OrigineDepense.ACHAT_STOCK, origine_id=mouvement.pk, cle="pieces",
            categorie=CategorieDepense.PIECES, date_depense=timezone.localtime(mouvement.date_mouvement).date(),
            libelle=f"Achat de pièces · {article.designation} ({article.reference}) × {mouvement.variation}",
            montant=mouvement.variation * mouvement.prix_unitaire,
        )

    ordres = OrdreReparation.objects.filter(statut=StatutOr.CLOTURE).select_related("vehicule")
    if depuis:
        ordres = ordres.filter(date_cloture__date__gte=depuis)
    for ordre in ordres:
        _traiter(
            origine=OrigineDepense.MAIN_OEUVRE_OR, origine_id=ordre.pk, cle="main_oeuvre",
            categorie=CategorieDepense.MAINTENANCE, date_depense=timezone.localtime(ordre.date_cloture).date(),
            libelle=f"Main-d'œuvre · {ordre.numero} · {ordre.vehicule.immatriculation}",
            montant=ordre.cout_main_oeuvre, reference=ordre.numero,
        )

    return compteurs
