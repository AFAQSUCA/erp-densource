# Chapitre 14 — La trésorerie : l'app finance

> 16 fichier(s) dans ce chapitre, 1932 lignes de code.

## Ce que vous allez construire

**`finance`** : la **trésorerie** et les **indicateurs financiers**. Cette app est une **couche au-dessus** de
`billing` : elle lit ce que les autres ont enregistré et en tire des chiffres.

**La trésorerie = ce qui a réellement bougé.** Trois sources :

| Source | Sens |
|---|---|
| **Règlements** reçus (`billing`) | entrées |
| **Dépenses** payées (`billing`) | sorties |
| **Mouvements manuels** (`finance`) : solde d'ouverture, apport, frais bancaires, retrait | entrées ou sorties |

Le **compte** (Banque, Caisse, Mobile Money) se **déduit du mode de paiement** : virement et chèque → banque,
espèces → caisse, Wave / Orange Money / MTN → mobile money.

**Les indicateurs du mois** :

- **CA facturé** = total **HT** des factures émises ; **encaissé** = règlements du mois ;
- **charges** = dépenses saisies **+** carburant (litres × prix des pleins) **+** coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles séparément ;
- **marge nette** = CA HT − charges ; **créances** = reste à recouvrer (dont échu) ; **trésorerie** = solde.

> Les **charges** (vue économique) et la **trésorerie** (vue réelle) ne sont volontairement **pas les mêmes
> chiffres**. Le rapprochement bancaire et les écritures comptables ne sont pas gérés (décision du client).

## Prérequis

- Chapitres 1 à 13 terminés.

## Notions Django de ce chapitre

- **Une app « de lecture »** : `finance` réutilise les services de `billing`, `fuel` et `inventory`
  **sans les dupliquer** : la règle du carburant reste dans `fuel`, le PUMP dans `inventory`.
- **Agrégation SQL** avec `Sum` et `values_list(...).annotate(...)` : le total est calculé par la base, pas
  par une boucle Python.
- **`order_by()` vide** pour neutraliser un tri par défaut qui fausserait un regroupement (`GROUP BY`).
- **Annulation logique d'un mouvement** (avec motif) : on n'efface pas un mouvement de trésorerie.
- **Dictionnaires de résultats** : les services renvoient des dictionnaires prêts à afficher (soldes,
  indicateurs).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/finance/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\finance apps\finance\management apps\finance\management\commands apps\finance\tests
touch apps/finance/__init__.py
touch apps/finance/management/__init__.py
touch apps/finance/management/commands/__init__.py
touch apps/finance/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle et services

#### `apps/finance/models.py`

*200 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.billing.models import CategorieDepense, ModePaiement
from apps.core.models import BaseModel


class SensMouvement(models.TextChoices):
    ENTREE = "ENTREE", _("Entrée")
    SORTIE = "SORTIE", _("Sortie")


class MouvementManuel(BaseModel):
    """Entrée ou sortie de trésorerie qui n'est ni un règlement ni une dépense.

    Exemples : solde d'ouverture, apport, frais bancaires, retrait. Les règlements de factures
    et les dépenses alimentent la trésorerie tout seuls (cahier-des-charges.md:196-198).
    """

    sens = models.CharField(_("sens"), max_length=6, choices=SensMouvement.choices)
    date_mouvement = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=200)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(_("référence"), max_length=100, blank=True)
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    motif_annulation = models.TextField(_("motif d'annulation"), blank=True)

    class Meta:
        verbose_name = _("mouvement de trésorerie")
        verbose_name_plural = _("mouvements de trésorerie")
        ordering = ["-date_mouvement", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="mouvement_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_sens_display()} {self.montant} : {self.libelle}"


# --- dépenses du parc auto pré-approuvées (R2) : enveloppes, demandes, ordres de décaissement ---


class EnveloppeDepense(BaseModel):
    """Plafond mensuel approuvé par la DIRECTION pour une catégorie de dépense automatique du parc
    auto (carburant, pièces, main-d'œuvre) — avenant-separation-des-taches.md (R2).

    Tant que les dépenses automatiques du mois restent dans ce plafond, elles se comptabilisent
    toutes seules comme aujourd'hui (``finance.receivers``, inchangé). Le dépasser bloque la
    dépense automatique suivante de cette catégorie et ouvre une ``DemandeDepense`` a posteriori
    que la DIRECTION doit valider avant que le mécanisme automatique ne reprenne. ``vehicule`` vide
    = enveloppe globale pour la catégorie ; sinon propre à ce camion (prioritaire sur la globale).
    """

    categorie = models.CharField(_("catégorie"), max_length=14, choices=CategorieDepense.choices)
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="enveloppes_depense",
        help_text=_("Vide : enveloppe globale pour cette catégorie, tous camions confondus."),
    )
    annee = models.PositiveSmallIntegerField(_("année"))
    mois = models.PositiveSmallIntegerField(_("mois"))
    montant_plafond = models.DecimalField(_("plafond (FCFA)"), max_digits=14, decimal_places=2)
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("approuvée par"), null=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name = _("enveloppe de dépense")
        verbose_name_plural = _("enveloppes de dépense")
        ordering = ["-annee", "-mois", "categorie"]
        constraints = [
            models.UniqueConstraint(
                fields=["categorie", "vehicule", "annee", "mois"], name="enveloppe_unique_par_scope_et_mois"
            ),
            models.CheckConstraint(condition=Q(montant_plafond__gt=0), name="enveloppe_plafond_positif"),
            models.CheckConstraint(condition=Q(mois__gte=1) & Q(mois__lte=12), name="enveloppe_mois_valide"),
        ]

    def __str__(self):
        cible = self.vehicule.immatriculation if self.vehicule_id else "tous camions"
        return f"{self.get_categorie_display()} {self.mois:02d}/{self.annee} ({cible})"


class OrigineDemande(models.TextChoices):
    MANUELLE = "MANUELLE", _("Demande du Parc Auto")
    DEPASSEMENT_ENVELOPPE = "DEPASSEMENT_ENVELOPPE", _("Dépassement d'enveloppe")


class StatutDemandeDepense(models.TextChoices):
    SOUMISE = "SOUMISE", _("Soumise")
    VALIDEE = "VALIDEE", _("Validée")
    REFUSEE = "REFUSEE", _("Refusée")


class DemandeDepense(BaseModel):
    """Demande de dépense du parc auto, validée par la DIRECTION avant toute dépense — R2.

    Deux origines : ``MANUELLE`` (le Parc Auto demande par avance un achat ou une réparation non
    routinière) et ``DEPASSEMENT_ENVELOPPE`` (ouverte automatiquement quand une dépense qui vient
    de se comptabiliser toute seule fait franchir le plafond du mois — la dépense existe déjà,
    cette demande ne fait que débloquer la suivante une fois validée ou refusée).
    """

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    categorie = models.CharField(_("catégorie"), max_length=14, choices=CategorieDepense.choices)
    vehicule = models.ForeignKey(
        "fleet.Vehicule", verbose_name=_("camion"), null=True, blank=True,
        on_delete=models.PROTECT, related_name="demandes_depense",
    )
    origine = models.CharField(_("origine"), max_length=21, choices=OrigineDemande.choices)
    montant_estime = models.DecimalField(_("montant estimé (FCFA)"), max_digits=14, decimal_places=2)
    motif = models.TextField(_("motif"))
    fournisseur = models.CharField(_("fournisseur"), max_length=200, blank=True)
    piece_jointe = models.FileField(
        _("pièce jointe"), upload_to="demandes_depense/%Y/%m/", blank=True,
        help_text=_("Devis du fournisseur, par exemple."),
    )
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutDemandeDepense.choices, default=StatutDemandeDepense.SOUMISE
    )
    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("demandeur"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("décidée par"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    date_decision = models.DateTimeField(_("décidée le"), null=True, blank=True)
    motif_refus = models.TextField(_("motif du refus"), blank=True)

    class Meta:
        verbose_name = _("demande de dépense")
        verbose_name_plural = _("demandes de dépense")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["categorie", "vehicule", "statut"])]
        constraints = [
            models.CheckConstraint(condition=Q(montant_estime__gt=0), name="demande_depense_montant_positif"),
        ]

    def __str__(self):
        return self.numero


class StatutOrdreDecaissement(models.TextChoices):
    A_EXECUTER = "A_EXECUTER", _("À exécuter")
    EN_ATTENTE_REVALIDATION = "EN_ATTENTE_REVALIDATION", _("En attente de revalidation")
    EXECUTE = "EXECUTE", _("Exécuté")


class OrdreDecaissement(BaseModel):
    """Ordre d'exécution d'une demande validée par la DIRECTION (origine ``MANUELLE`` uniquement) :
    la Finance l'exécute (mode, montant réel, justificatif) — R2.

    Si le montant réel dépasse de plus de 10 % le montant validé, l'exécution est bloquée et
    l'ordre revient à la DIRECTION (:data:`StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION`).
    """

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    demande = models.OneToOneField(
        DemandeDepense, verbose_name=_("demande"), on_delete=models.PROTECT, related_name="ordre_decaissement"
    )
    montant_valide = models.DecimalField(_("montant validé (FCFA)"), max_digits=14, decimal_places=2)
    statut = models.CharField(
        _("statut"), max_length=23, choices=StatutOrdreDecaissement.choices,
        default=StatutOrdreDecaissement.A_EXECUTER,
    )
    mode_paiement = models.CharField(_("mode de paiement"), max_length=14, choices=ModePaiement.choices, blank=True)
    justificatif = models.FileField(_("justificatif"), upload_to="ordres_decaissement/%Y/%m/", blank=True)
    montant_reel = models.DecimalField(_("montant réel (FCFA)"), max_digits=14, decimal_places=2, null=True, blank=True)
    execute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("exécuté par"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    date_execution = models.DateTimeField(_("exécuté le"), null=True, blank=True)
    depense = models.ForeignKey(
        "billing.Depense", verbose_name=_("dépense"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name = _("ordre de décaissement")
        verbose_name_plural = _("ordres de décaissement")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant_valide__gt=0), name="ordre_decaissement_montant_positif"),
        ]

    def __str__(self):
        return self.numero
```

Un seul modèle : `MouvementManuel`. Tout le reste de la trésorerie vient des modèles de `billing`.

#### `apps/finance/services.py`

*386 lignes* — Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

```python
"""Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

Trésorerie = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties)
et mouvements manuels. Le compte (banque, caisse, mobile money) se déduit du mode de paiement.

Charges du mois (indicateur, distinct de la trésorerie) = dépenses saisies + carburant (pleins)
+ coût des OR clôturés (main-d'œuvre et pièces). Marge nette = CA HT - charges. Les trois
composantes restent visibles séparément. Le rapprochement bancaire n'est pas géré (décision
de l'utilisateur) ; les écritures comptables non plus.
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
```

À lire :

1. **`_compte`** : traduit un mode de paiement en compte grâce à `COMPTE_DU_MODE`.
2. **`enregistrer_mouvement`** / **`annuler_mouvement`** : contrôlent le rôle (`billing.permissions.SAISIE`), le
   montant (strictement positif) et le motif d'annulation.
3. **`soldes_par_compte`** : additionne règlements, soustrait dépenses, applique les mouvements manuels, et
   ajoute le **total**.
4. **`synthese_periode`** : entrées, sorties et variation sur une période.
5. **`charges`** et **`indicateurs`** : les chiffres du mois, en appelant `fuel.cout_carburant` et
   `inventory.cout_des_or_clotures`.

#### `apps/finance/permissions.py`

*26 lignes* — Qui peut consulter et alimenter la trésorerie.

```python
"""Qui peut consulter et alimenter la trésorerie.

Mêmes droits que la facturation (cahier-des-charges.md:53) : FINANCES saisit et suit la
trésorerie, la DIRECTION consulte, l'ADMIN a tous les accès.
"""

from apps.accounts.models import Role
from apps.billing.permissions import CONSULTATION, SAISIE

__all__ = [
    "CONSULTATION", "SAISIE",
    "DEMANDE_CONSULTATION", "DEMANDE_SAISIE", "DEMANDE_VALIDATION", "ORDRE_EXECUTION", "ENVELOPPE_VALIDATION",
]

# Dépenses du parc auto pré-approuvées (R2) : celui qui demande (Parc Auto) ou exécute (Finance)
# n'est jamais celui qui valide (Direction) — jamais l'ADMIN à sa place (contrôle strict, comme
# pour la validation d'une facture). Retour réunion : la RH fait tout ce que fait la FINANCES, y
# compris exécuter l'ordre de décaissement ; la DIRECTION a la même largeur que l'ADMIN en saisie
# mais ne remplace jamais la FINANCES/RH sur l'exécution (contrôle strict conservé).
DEMANDE_CONSULTATION = frozenset(
    {Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.RH}
)
DEMANDE_SAISIE = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
DEMANDE_VALIDATION = frozenset({Role.DIRECTION})
ORDRE_EXECUTION = frozenset({Role.FINANCES, Role.RH})
ENVELOPPE_VALIDATION = frozenset({Role.DIRECTION})
```

Elle **réutilise** celles de `billing` : mêmes droits, écrits une seule fois.

#### `apps/finance/apps.py`

*30 lignes*

```python
from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    label = 'finance'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import DemandeDepense, EnveloppeDepense, MouvementManuel, OrdreDecaissement

        audit_model(MouvementManuel, module="FINANCES")
        audit_model(EnveloppeDepense, module="FINANCES")
        audit_model(DemandeDepense, module="FINANCES")
        audit_model(OrdreDecaissement, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Trésorerie", "finance:tresorerie", "fa-wallet", permissions.CONSULTATION, ordre=62
            )
        )
        enregistrer(
            EntreeMenu(
                "Demandes de dépense", "finance:demandes", "fa-file-invoice",
                permissions.DEMANDE_CONSULTATION, ordre=63,
            )
        )
```

#### `apps/finance/README.md`

*97 lignes* — finance

````markdown
# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.

**Dépenses du parc auto** (`receivers.py`) : chaque plein (`fuel.enregistrer_plein`), chaque achat de pièces
(`inventory.enregistrer_entree`) et la main-d'œuvre de chaque OR clôturé (`garage.cloturer_or`) crée une
`billing.Depense` automatique (catégorie Carburant / Pièces détachées / Main-d'œuvre des réparations, une seule par
source, contrainte `depense_une_par_origine`), donc une ligne de la page Dépenses **et** une sortie de trésorerie. Mode
de paiement par défaut : espèces (Caisse) ; la Finance le corrige sur la ligne (`billing.changer_mode_depense`), ce qui
change le compte débité. Les pièces sont comptées **à l'achat** : leur sortie vers un OR ne l'est pas (pas de double
compte), si bien qu'un OR n'ajoute que sa main-d'œuvre. Les apps d'origine émettent un signal (`plein_enregistre`,
`entree_stock_enregistree`, `or_cloture`) émis avec `send` : si la dépense ne peut pas être écrite, l'opération est
annulée. La saisie manuelle de ces trois catégories est refusée (double compte).

Reprise de l'historique (pleins, achats et OR déjà enregistrés avant la mise en service de ce mécanisme) :
`services.reprendre_depenses_parc_auto()` / commande `comptabiliser_historique_parc_auto` — **volontairement pas
une migration automatique**, pour ne jamais rétro-débiter la trésorerie sans décision explicite. Elle rejoue
`billing.comptabiliser_depense_automatique` pour chaque source manquante (idempotent, rejouable sans double
compte) et rapporte le nombre créé par catégorie. À exécuter une fois, après vérification :
```
python manage.py comptabiliser_historique_parc_auto --dry-run   # prévisualiser, rien n'est écrit
python manage.py comptabiliser_historique_parc_auto              # tout l'historique
python manage.py comptabiliser_historique_parc_auto --depuis 2026-09-01   # si un solde d'ouverture au
    # 31/08/2026 comprend déjà les mouvements antérieurs (sinon ils seraient comptés deux fois)
```

## Dépenses pré-approuvées du parc auto (`demandes.py`, R2 — avenant-separation-des-taches.md)

Séparation des tâches : le **Parc Auto** demande, la **DIRECTION** valide (jamais l'ADMIN à sa place,
contrôle strict comme pour une facture), la **FINANCES** exécute. Deux circuits sur le même modèle
`DemandeDepense` (numéro `DEM-AAAA-XXXX`) :

- **Manuelle** : le Parc Auto soumet une demande (catégorie, montant estimé, motif, fournisseur,
  pièce jointe) *avant* un achat ou une réparation non routinière. Validée, elle génère un
  `OrdreDecaissement` (`ODC-AAAA-XXXX`) que la Finance exécute (mode, montant réel, justificatif) :
  cela crée la `billing.Depense` (origine `ORDRE_DECAISSEMENT`). Refusée, elle s'arrête là (motif
  obligatoire).
- **Dépassement d'enveloppe** : la DIRECTION peut fixer une `EnveloppeDepense` — un plafond mensuel
  pour une catégorie automatique (carburant, pièces, main-d'œuvre), globalement ou pour un camion
  précis (prioritaire sur la globale). Tant que les dépenses du mois restent dans ce plafond, le
  mécanisme ci-dessus continue de fonctionner **sans rien changer** : c'est le comportement par
  défaut, sans enveloppe définie, illimité comme avant R2. Une dépense qui fait franchir le plafond
  reste comptabilisée (l'argent est déjà sorti) mais ouvre une `DemandeDepense` a posteriori ; toute
  dépense automatique *suivante* de cette catégorie est bloquée (l'opération d'origine — plein,
  achat, clôture d'OR — est annulée) tant que la DIRECTION n'a pas décidé (validée ou refusée,
  peu importe : les deux débloquent, seul le refus n'est qu'un constat de désaccord).

**Dépassement de plus de 10 %** à l'exécution d'un ordre (manuelle) : bloqué, l'ordre passe en
`EN_ATTENTE_REVALIDATION` (état qui **doit** survivre à l'erreur renvoyée à l'écran — `executer_ordre`
n'a donc pas de `@transaction.atomic` sur toute sa longueur, seulement sur le bloc qui écrit l'état,
sans quoi l'erreur annulerait la mise en attente elle-même). La DIRECTION revalide
(`revalider_ordre`, nouveau montant validé) avant que la Finance ne puisse retenter l'exécution.

Écrans : `/finances/demandes/` (liste + « Nouvelle demande » pour le Parc Auto), fiche par demande
(décision, exécution, revalidation selon le rôle et l'état), `/finances/enveloppes/` (DIRECTION).
Notifications (catégorie `DEMANDE_DEPENSE`) : soumission → DIRECTION ; décision → le demandeur (ou
le Parc Auto pour un dépassement) ; ordre à exécuter → FINANCES ; dépassement de 10 % → DIRECTION.

**Frais de mission** (`receivers.py`, R4 — avenant-separation-des-taches.md) : même mécanisme que ci-dessus, pour une
avance de route, une dépense prévue ou un imprévu (`missions.FraisMission`) une fois **confirmé**
(`missions.signals.frais_mission_confirme`, `send` non protégé : une dépense qui ne peut pas s'écrire annule la
confirmation) — catégorie « Frais de mission », dépense liée à la mission d'origine. Un encaissement
(`FraisMission` de type ``ENCAISSEMENT``) est le reflet automatique d'un règlement déjà enregistré
(`billing.signals.reglement_enregistre`, `send_robust` : un échec ici ne bloque jamais le règlement) : il ne crée ni
dépense ni règlement supplémentaire, seulement une ligne pour la vue « Frais de mission » de la mission facturée.
`missions` et `billing` s'ignorent l'un l'autre : c'est `finance` qui relie les deux (graphe de dépendance,
architecture.md:95-163).

**Versements à confirmer** : une facture émise mais pas soldée est un versement attendu
(`services.versements_attendus`). Quand la Direction valide une facture, la FINANCES reçoit une
notification avec le bouton « Confirmer le versement » ; il mène à `/finances/versements/<id>/confirmer/`
(`services.confirmer_versement`), où la Finance saisit le montant réellement reçu, la date et le mode. Cela
enregistre un règlement (`billing.enregistrer_reglement`, mêmes contrôles) et donc une **entrée** de
trésorerie sur le compte du mode. Tant que ce n'est pas confirmé, le solde réel ne bouge pas : la
page Trésorerie affiche les versements attendus à part, avec un solde prévisionnel. Un versement
partiel laisse le reste dans la liste. Seule la FINANCES (et l'ADMIN) confirme ; la DIRECTION voit la liste.

**Historique mensuel** (`services.historique_mensuel`) : CA HT, encaissé et charges des 6 derniers mois,
pour le graphique du tableau de bord ; le mois en cours reprend les indicateurs déjà calculés.

**Indicateurs du mois** (`services.indicateurs`, affichés au tableau de bord) :
- CA facturé = total **HT** des factures émises ; encaissé = règlements du mois ;
- charges = **toutes les dépenses** (`services.charges`), y compris celles du parc auto et des missions qui se
  créent toutes seules (voir ci-dessous) ; ventilées en carburant, pièces, main-d'œuvre, frais de mission et autres ;
- marge nette = CA HT - charges ; créances = reste à recouvrer (dont échu) ; trésorerie = solde.
  Les charges (économiques) et la trésorerie (réelle) ne sont volontairement pas les mêmes chiffres.

Pas encore fait : **rapprochement bancaire** (écarté sur décision de l'utilisateur : trésorerie
seulement), import de relevés, écritures comptables, grand livre.

Rapport imprimable de la trésorerie (`/finances/imprimer/`, bouton « Imprimer ») : soldes par compte, synthèse et journal de la période filtrée, mêmes filtres que l'écran, plafonné à 500 lignes (voir `apps/core/README.md`).
````

#### `apps/finance/signals.py`

*28 lignes* — Événements des dépenses pré-approuvées du parc auto (R2), souscrits par ``notifications``.

```python
"""Événements des dépenses pré-approuvées du parc auto (R2), souscrits par ``notifications``.

Émis avec ``send_robust`` : un récepteur en erreur ne doit jamais empêcher une décision de la
direction ou de la finance.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Une demande vient d'être soumise (manuelle) ou ouverte automatiquement (dépassement d'enveloppe).
# Argument : ``demande``.
demande_soumise = Signal()
# La direction vient de valider ou refuser une demande. Argument : ``demande``.
demande_decidee = Signal()
# Une demande validée (manuelle) vient de générer un ordre à exécuter. Argument : ``ordre``.
ordre_a_executer = Signal()
# Le montant réel dépasse de plus de 10 % le montant validé : l'ordre revient à la direction.
# Argument : ``ordre``.
ordre_depassement = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
```

#### `apps/finance/receivers.py`

*104 lignes* — Comptabilisation automatique des dépenses du parc auto.

```python
"""Comptabilisation automatique des dépenses du parc auto.

Un plein de carburant, un achat de pièces (entrée de stock) et la main-d'œuvre d'un OR clôturé sont des
sorties d'argent : chacun crée sa dépense (``demandes.comptabiliser_avec_controle_enveloppe``, qui vérifie
d'abord l'enveloppe mensuelle de la DIRECTION avant de déléguer à ``billing.comptabiliser_depense_automatique``
— R2, avenant-separation-des-taches.md), donc une ligne de la page Dépenses et une sortie de trésorerie, sans
double saisie. Les apps d'origine ne connaissent pas ``finance`` : elles émettent un signal, souscrit ici.
Récepteurs appelés par ``send`` (pas ``send_robust``) : une erreur (dépense refusée, enveloppe dépassée en
attente de décision...) annule l'opération d'origine au lieu de laisser une dépense non comptée.

Les pièces sont comptées à l'**achat**, pas à leur sortie de stock vers un OR : le coût d'un OR clôturé n'entre
donc dans les charges que par sa main-d'œuvre (sinon la pièce serait comptée deux fois).
"""

from django.dispatch import receiver
from django.utils import timezone

from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, OrigineDepense
from apps.billing.signals import reglement_enregistre
from apps.fuel.signals import plein_enregistre
from apps.garage.signals import or_cloture
from apps.inventory.signals import entree_stock_enregistree
from apps.missions import terrain as missions_terrain
from apps.missions.models import TypeFraisMission
from apps.missions.signals import frais_mission_confirme

from . import demandes


@receiver(plein_enregistre)
def comptabiliser_un_plein(sender, plein, **kwargs):
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.PLEIN,
        origine_id=plein.pk,
        categorie=CategorieDepense.CARBURANT,
        date_depense=plein.date_plein,
        libelle=(
            f"Carburant · {plein.vehicule.immatriculation} · {plein.station} "
            f"({plein.quantite_litres.normalize():f} L)"
        ),
        montant=plein.quantite_litres * plein.prix_unitaire,
        reference=plein.numero_ticket,
        vehicule=plein.vehicule,
    )


@receiver(entree_stock_enregistree)
def comptabiliser_un_achat_de_pieces(sender, mouvement, **kwargs):
    article = mouvement.article
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.ACHAT_STOCK,
        origine_id=mouvement.pk,
        categorie=CategorieDepense.PIECES,
        date_depense=timezone.localdate(mouvement.date_mouvement),
        libelle=f"Achat de pièces · {article.designation} ({article.reference}) × {mouvement.variation}",
        montant=mouvement.variation * mouvement.prix_unitaire,
    )


@receiver(or_cloture)
def comptabiliser_la_main_d_oeuvre(sender, ordre, **kwargs):
    demandes.comptabiliser_avec_controle_enveloppe(
        origine=OrigineDepense.MAIN_OEUVRE_OR,
        origine_id=ordre.pk,
        categorie=CategorieDepense.MAINTENANCE,
        date_depense=timezone.localdate(ordre.date_cloture),
        libelle=f"Main-d'œuvre · {ordre.numero} · {ordre.vehicule.immatriculation}",
        montant=ordre.cout_main_oeuvre,
        reference=ordre.numero,
        vehicule=ordre.vehicule,
    )


@receiver(frais_mission_confirme)
def comptabiliser_un_frais_de_mission(sender, frais, **kwargs):
    """Avance de route, dépense prévue ou imprévu confirmé (R4) : une sortie d'argent comme une
    autre. Un encaissement (reflet d'un règlement) ne déclenche jamais ce signal."""
    if frais.type_frais == TypeFraisMission.ENCAISSEMENT:
        return
    billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.FRAIS_MISSION,
        origine_id=frais.pk,
        categorie=CategorieDepense.FRAIS_MISSION,
        date_depense=timezone.localdate(),
        libelle=(
            f"{frais.get_type_frais_display()} · {frais.mission.numero}"
            + (f" · {frais.description}" if frais.description else "")
        ),
        montant=frais.montant,
        mission=frais.mission,
    )


@receiver(reglement_enregistre)
def refleter_l_encaissement_sur_la_mission(sender, reglement, **kwargs):
    """Un règlement reçu se reflète dans la prévision de trésorerie de la mission facturée (R4),
    sans double saisie : aucune dépense ni règlement supplémentaire n'est créé ici."""
    missions_terrain.creer_encaissement(
        reglement.facture.mission,
        montant=reglement.montant,
        libelle=f"Règlement {reglement.facture.numero} ({reglement.get_mode_display()})",
        saisi_par=reglement.saisi_par,
    )
```

#### `apps/finance/demandes.py`

*320 lignes* — Dépenses du parc auto pré-approuvées (R2) : enveloppes mensuelles, demandes, ordres de décaissement.

```python
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
```

#### `apps/finance/management/commands/comptabiliser_historique_parc_auto.py`

*60 lignes* — Reprise, à la demande, des dépenses du parc auto déjà enregistrées avant la mise en service de leur

```python
"""Reprise, à la demande, des dépenses du parc auto déjà enregistrées avant la mise en service de leur
comptabilisation automatique (``finance.receivers``) : pleins, achats de pièces, main-d'œuvre d'OR clôturés.

Volontairement **pas une migration automatique** : sur une base qui a déjà un solde d'ouverture saisi en
trésorerie, reprendre l'historique complet compterait deux fois les mouvements antérieurs à ce solde (il
les comprend déjà). À exécuter une fois, après avoir vérifié la date du solde d'ouverture (s'il y en a un) :
- pas de solde d'ouverture (ou aucun mouvement antérieur à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une dépense par source, comme le mécanisme normal) : relancer la commande
après un ``--depuis`` mal choisi, corrigé, ne recrée pas ce qui a déjà été comptabilisé.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance import services


class Command(BaseCommand):
    help = (
        "Comptabilise en dépenses les pleins, achats de pièces et main-d'œuvre d'OR déjà enregistrés "
        "(voir --dry-run pour prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les sources à partir de cette date (bornes incluses).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait comptabilisé sans rien écrire.",
        )

    def handle(self, *args, depuis=None, dry_run=False, **options):
        date_depuis = None
        if depuis:
            try:
                date_depuis = date.fromisoformat(depuis)
            except ValueError:
                raise CommandError(f"Date invalide pour --depuis : {depuis!r} (attendu AAAA-MM-JJ).")

        if dry_run:
            from django.db import transaction

            with transaction.atomic():
                compteurs = services.reprendre_depenses_parc_auto(depuis=date_depuis)
                transaction.set_rollback(True)
        else:
            compteurs = services.reprendre_depenses_parc_auto(depuis=date_depuis)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            prefixe
            + f"Carburant : {compteurs['carburant']} · Pièces : {compteurs['pieces']} · "
            f"Main-d'œuvre : {compteurs['main_oeuvre']} comptabilisées "
            f"({compteurs['deja_comptabilisees']} déjà présentes, inchangées)."
        )
```

#### `apps/finance/tests/test_demandes.py`

*336 lignes* — Dépenses du parc auto pré-approuvées (R2) : enveloppes, demandes manuelles et dépassements,

```python
"""Dépenses du parc auto pré-approuvées (R2) : enveloppes, demandes manuelles et dépassements,
ordres de décaissement et blocage à plus de 10 % de dépassement."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide, TransitionFactureInterdite
from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import demandes as services
from apps.finance.models import (
    DemandeDepense,
    OrdreDecaissement,
    OrigineDemande,
    StatutDemandeDepense,
    StatutOrdreDecaissement,
)
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.fuel.models import Plein

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 10)


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


def _direction():
    return UserFactory(role=Role.DIRECTION)


def _finances():
    return UserFactory(role=Role.FINANCES)


def _plein(*, camion=None, litres="100", prix="655", jour=JOUR, ticket="T-1"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour,
        station="Total", quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix),
        km_compteur=1000, numero_ticket=ticket,
    )


# --- enveloppes ---


def test_la_direction_definit_une_enveloppe():
    enveloppe = services.definir_enveloppe(
        _direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000")
    )

    assert enveloppe.montant_plafond == Decimal("300000")
    assert enveloppe.vehicule is None


def test_redefinir_la_meme_enveloppe_met_a_jour_le_plafond():
    direction = _direction()
    services.definir_enveloppe(direction, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000"))

    services.definir_enveloppe(direction, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("500000"))

    assert services.enveloppes_queryset().count() == 1
    assert services.enveloppes_queryset().first().montant_plafond == Decimal("500000")


def test_seule_la_direction_definit_une_enveloppe():
    for acteur in (_parcauto(), _finances(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.definir_enveloppe(acteur, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("1"))


def test_enveloppe_refusee_hors_categorie_automatique():
    with pytest.raises(MontantInvalide):
        services.definir_enveloppe(_direction(), categorie=CategorieDepense.PEAGES, annee=2026, mois=9, montant_plafond=Decimal("1"))


# --- dépenses automatiques sans enveloppe : comportement inchangé ---


def test_sans_enveloppe_la_depense_automatique_reste_illimitee():
    plein = _plein(litres="500", prix="700")  # 350 000 FCFA, aucune enveloppe définie

    (depense,) = Depense.objects.filter(origine=OrigineDepense.PLEIN)
    assert depense.origine_id == plein.pk
    assert not DemandeDepense.objects.exists()


# --- dépassement d'enveloppe ---


def test_dans_l_enveloppe_aucune_demande_ne_s_ouvre():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000"))

    _plein(litres="100", prix="655", jour=JOUR)  # 65 500 FCFA, largement sous le plafond

    assert not DemandeDepense.objects.exists()


def test_le_depassement_ouvre_une_demande_mais_garde_la_depense():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))

    plein = _plein(litres="100", prix="655", jour=JOUR)  # 65 500 FCFA > 50 000

    assert Depense.objects.filter(origine_id=plein.pk).exists()  # l'argent est déjà sorti
    demande = DemandeDepense.objects.get()
    assert demande.origine == OrigineDemande.DEPASSEMENT_ENVELOPPE
    assert demande.statut == StatutDemandeDepense.SOUMISE
    assert demande.categorie == CategorieDepense.CARBURANT
    assert demande.montant_estime == Decimal("15500.00")


def test_une_demande_en_attente_bloque_le_plein_suivant():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")  # dépasse, ouvre une demande

    with pytest.raises(TransitionFactureInterdite, match="dépassée"):
        _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")

    # L'opération d'origine (le plein) est annulée avec la dépense refusée : rien n'est resté en base.
    assert not Plein.objects.filter(numero_ticket="T-2").exists()
    assert DemandeDepense.objects.count() == 1


def test_valider_la_demande_debloque_le_mecanisme():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")
    demande = DemandeDepense.objects.get()

    services.valider_demande(demande, _direction())
    _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")  # ne lève plus

    assert Depense.objects.filter(origine=OrigineDepense.PLEIN).count() == 2


def test_refuser_la_demande_debloque_aussi_le_mecanisme():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")
    demande = DemandeDepense.objects.get()

    services.refuser_demande(demande, _direction(), motif="Consommation anormale à vérifier")
    _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")

    assert Depense.objects.filter(origine=OrigineDepense.PLEIN).count() == 2


def test_une_demande_de_depassement_ne_genere_pas_d_ordre_de_decaissement():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR)
    demande = DemandeDepense.objects.get()

    services.valider_demande(demande, _direction())

    assert not OrdreDecaissement.objects.exists()


def test_enveloppe_par_camion_prime_sur_l_enveloppe_globale():
    camion = VehiculeFactory()
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("1000000"))
    services.definir_enveloppe(
        _direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"), vehicule=camion
    )

    _plein(camion=camion, litres="100", prix="655", jour=JOUR)  # 65 500 > 50 000 (enveloppe du camion)

    demande = DemandeDepense.objects.get()
    assert demande.vehicule == camion


# --- demande manuelle (Parc Auto) ---


def test_soumettre_une_demande_manuelle():
    demande = services.soumettre_demande(
        _parcauto(), categorie=CategorieDepense.MAINTENANCE, montant_estime=Decimal("200000"),
        motif="Réparation boîte de vitesses chez un prestataire externe", fournisseur="Garage Koffi",
    )

    assert demande.origine == OrigineDemande.MANUELLE
    assert demande.statut == StatutDemandeDepense.SOUMISE
    assert demande.numero.startswith("DEM-2026-")


def test_seul_le_parc_auto_soumet_une_demande():
    # Retour réunion : la DIRECTION a désormais la même largeur que l'ADMIN en saisie ;
    # la FINANCES, elle, n'a jamais eu ce droit (elle exécute, elle ne demande pas).
    with pytest.raises(ActionFactureNonAutorisee):
        services.soumettre_demande(_finances(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1"), motif="x")


@pytest.mark.parametrize("montant", [Decimal("0"), Decimal("-1")])
def test_montant_estime_invalide(montant):
    with pytest.raises(MontantInvalide):
        services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=montant, motif="x")


def test_motif_obligatoire():
    with pytest.raises(MontantInvalide, match="motif"):
        services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="   ")


def test_valider_une_demande_manuelle_genere_un_ordre():
    demande = services.soumettre_demande(
        _parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="Pièce rare"
    )

    services.valider_demande(demande, _direction())

    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.VALIDEE
    ordre = OrdreDecaissement.objects.get(demande=demande)
    assert ordre.montant_valide == Decimal("200000")
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER
    assert ordre.numero.startswith("ODC-2026-")


def test_valider_peut_ajuster_le_montant():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="x")

    services.valider_demande(demande, _direction(), montant_valide=Decimal("150000"))

    assert OrdreDecaissement.objects.get(demande=demande).montant_valide == Decimal("150000")


def test_seule_la_direction_valide_ou_refuse():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")
    for acteur in (_parcauto(), _finances(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider_demande(demande, acteur)
        with pytest.raises(ActionFactureNonAutorisee):
            services.refuser_demande(demande, acteur, motif="x")


def test_refuser_exige_un_motif():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")

    with pytest.raises(MontantInvalide, match="motif"):
        services.refuser_demande(demande, _direction(), motif="  ")


def test_une_demande_deja_traitee_ne_se_redecide_pas():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")
    services.valider_demande(demande, _direction())

    with pytest.raises(TransitionFactureInterdite):
        services.valider_demande(demande, _direction())


# --- exécution et dépassement de 10 % ---


def _ordre_valide(montant_estime="200000", montant_valide=None):
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal(montant_estime), motif="x")
    services.valider_demande(demande, _direction(), montant_valide=montant_valide)
    return OrdreDecaissement.objects.get(demande=demande)


def test_executer_un_ordre_dans_la_tolerance_comptabilise_la_depense():
    ordre = _ordre_valide("200000")

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.VIREMENT, montant_reel=Decimal("205000"), reference="FAC-1")

    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE
    depense = Depense.objects.get(origine=OrigineDepense.ORDRE_DECAISSEMENT, origine_id=ordre.pk)
    assert depense.montant == Decimal("205000.00") and depense.mode == ModePaiement.VIREMENT
    assert ordre.depense_id == depense.pk


def test_seule_la_finance_execute():
    ordre = _ordre_valide()
    for acteur in (_parcauto(), _direction(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.executer_ordre(ordre, acteur, mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("1000"))


def test_un_depassement_de_plus_de_10_pourcent_bloque_l_execution():
    ordre = _ordre_valide("200000")

    with pytest.raises(MontantInvalide, match="dépasse"):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))

    ordre.refresh_from_db()
    # L'état bloqué est bien enregistré (pas annulé avec l'erreur) : la finance ne peut plus rejouer.
    assert ordre.statut == StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION
    assert ordre.montant_reel == Decimal("230000")
    assert not Depense.objects.filter(origine=OrigineDepense.ORDRE_DECAISSEMENT).exists()


def test_exactement_10_pourcent_de_plus_passe():
    ordre = _ordre_valide("200000")

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("220000"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_revalider_permet_de_reexecuter():
    ordre = _ordre_valide("200000")
    with pytest.raises(MontantInvalide):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()

    services.revalider_ordre(ordre, _direction(), montant_valide=Decimal("230000"))
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_seule_la_direction_revalide():
    ordre = _ordre_valide("200000")
    with pytest.raises(MontantInvalide):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()

    with pytest.raises(ActionFactureNonAutorisee):
        services.revalider_ordre(ordre, _finances(), montant_valide=Decimal("230000"))


def test_un_ordre_deja_execute_ne_se_reexecute_pas():
    ordre = _ordre_valide("200000")
    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("200000"))
    ordre.refresh_from_db()

    with pytest.raises(TransitionFactureInterdite):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("200000"))
```

#### `apps/finance/tests/test_frais_mission_receivers.py`

*74 lignes* — Prévision de trésorerie des missions (R4) côté finance : un frais confirmé devient une dépense,

```python
"""Prévision de trésorerie des missions (R4) côté finance : un frais confirmé devient une dépense,
un règlement reçu se reflète (sans double saisie) dans les frais de la mission facturée."""

from datetime import date
from decimal import Decimal

import pytest

from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import direction, finances, mission_livree
from apps.billing import services as billing_services
from apps.missions import terrain as missions_terrain
from apps.missions.models import FraisMission, StatutFraisMission, TypeFraisMission
from apps.missions.tests.test_frais_mission import _chauffeur, _mission_affectee, _parcauto

pytestmark = pytest.mark.django_db


def test_une_avance_confirmee_devient_une_depense_liee_a_la_mission():
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000"),
        description="Avance essence",
    )

    missions_terrain.valider_finances(frais, finances())

    depense = Depense.objects.get(origine=OrigineDepense.FRAIS_MISSION, origine_id=frais.pk)
    assert depense.categorie == CategorieDepense.FRAIS_MISSION
    assert depense.montant == Decimal("50000.00")
    assert depense.mission_id == mission.pk
    assert "Avance essence" in depense.libelle


def test_un_imprevu_confirme_devient_une_depense():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile

    preuve = SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("15000"), justificatif=preuve)
    missions_terrain.valider_parcauto(frais, _parcauto())

    missions_terrain.valider_finances(frais, finances())

    assert Depense.objects.filter(origine=OrigineDepense.FRAIS_MISSION, origine_id=frais.pk).exists()


def test_un_encaissement_ne_cree_aucune_depense():
    mission = _mission_affectee()

    missions_terrain.creer_encaissement(mission, montant=Decimal("300000"), libelle="Règlement")

    assert not Depense.objects.filter(origine=OrigineDepense.FRAIS_MISSION).exists()


def test_un_reglement_recu_se_reflete_dans_les_frais_de_la_mission():
    facture = billing_services.creer_facture(mission_livree(prix="1000000"), finances())
    billing_services.soumettre(facture, finances())
    billing_services.valider(facture, direction(), aujourd_hui=date(2026, 9, 1))

    billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 5),
    )

    ligne = FraisMission.objects.get(mission=facture.mission, type_frais=TypeFraisMission.ENCAISSEMENT)
    assert ligne.statut == StatutFraisMission.CONFIRME
    assert ligne.montant == Decimal("400000")
    assert facture.numero in ligne.description
    # Aucune double saisie : le règlement reste la seule dépense/entrée réelle en trésorerie.
    assert not Depense.objects.filter(mission=facture.mission).exists()
```

#### `apps/finance/tests/test_services.py`

*255 lignes* — Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers.

```python
"""Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import JOUR, direction, emise, finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

SEPT = (date(2026, 9, 1), date(2026, 9, 30))


def _manuel(sens=SensMouvement.ENTREE, montant="100000", *, mode=ModePaiement.VIREMENT, jour=JOUR,
            libelle="Apport", acteur=None):
    return services.enregistrer_mouvement(
        acteur or finances(), sens=sens, date_mouvement=jour, libelle=libelle,
        montant=Decimal(montant), mode=mode,
    )


def _reglement(facture, montant, mode=ModePaiement.VIREMENT, jour=JOUR):
    return billing.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def _depense(montant, mode=ModePaiement.ESPECES, jour=JOUR, categorie="PEAGES"):
    return billing.enregistrer_depense(
        finances(), categorie=categorie, date_depense=jour, libelle="Péage", montant=Decimal(montant), mode=mode
    )


# --- mouvements manuels ---


def test_un_mouvement_manuel_s_enregistre_et_s_annule_avec_un_motif():
    mouvement = _manuel()

    services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert MouvementManuel.all_objects.get(pk=mouvement.pk).motif_annulation == "Doublon"


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        ("  ", "10", JOUR, "libellé"),
        ("x", "0", JOUR, "strictement positif"),
        ("x", "10", date(2999, 1, 1), "futur"),
    ],
)
def test_mouvements_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        _manuel(libelle=libelle, montant=montant, jour=jour)


def test_les_mouvements_sont_reserves_a_la_saisie_facturation():
    # Retour réunion : la DIRECTION (même largeur que l'ADMIN) est désormais dans la SAISIE ;
    # le Parc Auto, lui, n'y a jamais eu accès.
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=UserFactory(role=Role.PARCAUTO))
    mouvement = _manuel()
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_mouvement(mouvement, UserFactory(role=Role.PARCAUTO), motif="x")
    with pytest.raises(MontantInvalide, match="motif"):
        services.annuler_mouvement(mouvement, finances(), motif=" ")


def test_la_direction_peut_desormais_saisir_un_mouvement():
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie."""
    assert _manuel(acteur=direction()).pk


# --- journal et soldes ---


def test_le_solde_reunit_reglements_depenses_et_mouvements_par_compte():
    facture = emise(prix="1000000")  # TTC 1 180 000
    _reglement(facture, "500000", ModePaiement.VIREMENT)
    _reglement(facture, "100000", ModePaiement.WAVE)
    _depense("20000", ModePaiement.ESPECES)
    _manuel(SensMouvement.ENTREE, "50000", mode=ModePaiement.ESPECES, libelle="Solde de caisse")
    _manuel(SensMouvement.SORTIE, "5000", mode=ModePaiement.VIREMENT, libelle="Frais bancaires")

    soldes = services.soldes_par_compte()

    assert soldes["BANQUE"] == Decimal("495000")  # 500 000 - 5 000
    assert soldes["CAISSE"] == Decimal("30000")  # 50 000 - 20 000
    assert soldes["MOBILE_MONEY"] == Decimal("100000")
    assert soldes["total"] == Decimal("625000")


def test_un_reglement_annule_ne_compte_plus():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "300000")
    billing.annuler_reglement(reglement, finances(), motif="Erreur")

    assert services.soldes_par_compte()["total"] == 0
    assert services.mouvements() == []


def test_le_journal_est_trie_et_decrit_chaque_origine():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", jour=date(2026, 9, 3))
    _depense("5000", jour=date(2026, 9, 5))
    _manuel(jour=date(2026, 9, 4), libelle="Apport")

    journal = services.mouvements()

    assert [(m["origine"], m["sens"]) for m in journal] == [
        ("DEPENSE", "SORTIE"), ("MANUEL", "ENTREE"), ("REGLEMENT", "ENTREE"),
    ]
    assert journal[2]["libelle"].startswith(f"Règlement {facture.numero} · ")
    assert journal[2]["compte"] == "BANQUE" and journal[0]["compte"] == "CAISSE"


def test_le_journal_se_filtre_par_periode_sens_et_compte():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.WAVE, date(2026, 9, 3))
    _depense("5000", ModePaiement.ESPECES, date(2026, 9, 10))
    _manuel(SensMouvement.SORTIE, "1000", mode=ModePaiement.VIREMENT, jour=date(2026, 9, 15), libelle="Frais")

    assert len(services.mouvements(date_debut=date(2026, 9, 5))) == 2
    assert len(services.mouvements(date_fin=date(2026, 9, 5))) == 1
    assert [m["origine"] for m in services.mouvements(sens="ENTREE")] == ["REGLEMENT"]
    assert sorted(m["origine"] for m in services.mouvements(sens="SORTIE")) == ["DEPENSE", "MANUEL"]
    assert [m["origine"] for m in services.mouvements(compte="MOBILE_MONEY")] == ["REGLEMENT"]
    assert services.mouvements(compte="CAISSE")[0]["origine"] == "DEPENSE"


def test_synthese_de_periode_entrees_sorties_variation():
    facture = emise(prix="1000000")
    _reglement(facture, "400000", jour=date(2026, 9, 3))
    _manuel(SensMouvement.ENTREE, "100000", jour=date(2026, 9, 4))
    _depense("30000", jour=date(2026, 9, 6))
    _manuel(SensMouvement.SORTIE, "20000", jour=date(2026, 9, 7), libelle="Frais")
    _depense("999", jour=date(2026, 8, 6))  # hors période

    assert services.synthese_periode(*SEPT) == {
        "entrees": Decimal("500000"), "sorties": Decimal("50000"), "variation": Decimal("450000"),
    }


def test_sans_mouvement_tout_est_a_zero():
    assert services.soldes_par_compte()["total"] == 0
    assert services.synthese_periode(*SEPT)["variation"] == 0


# --- charges et indicateurs ---


def _or_cloture(jour_cloture, main_oeuvre="30000", pieces=2):
    ordre = garage.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )
    article = ArticleFactory(reference=f"P-{ordre.pk}", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))
    stock.sortir_pour_or(article, quantite=pieces, ordre=ordre)
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal(main_oeuvre))
    type(ordre).objects.filter(pk=ordre.pk).update(
        date_cloture=timezone.now().replace(year=jour_cloture.year, month=jour_cloture.month, day=jour_cloture.day)
    )
    return ordre


def _plein(litres, prix, jour, camion=None, km=1000, ticket="T"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour, station="T",
        quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km, numero_ticket=ticket,
    )


def test_le_cout_du_carburant_est_litres_fois_prix_sur_la_periode():
    _plein("100", "655", date(2026, 9, 3), ticket="A")
    _plein("50", "660", date(2026, 9, 8), ticket="B")
    _plein("999", "700", date(2026, 8, 30), ticket="C")  # hors période

    assert fuel.cout_carburant(*SEPT) == Decimal("98500")  # 65 500 + 33 000


def test_le_cout_des_or_clotures_compte_main_d_oeuvre_et_pieces_de_la_periode():
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # 30 000 + 2 x 5 000
    _or_cloture(date(2026, 8, 10), main_oeuvre="99999", pieces=1)  # hors période

    assert stock.cout_des_or_clotures(*SEPT) == Decimal("40000")


def test_charges_regroupe_depenses_carburant_pieces_et_main_d_oeuvre():
    """Le carburant, les pièces achetées et la main-d'œuvre des OR sont des dépenses comme les autres."""
    from apps.billing.models import Depense, OrigineDepense

    _depense("20000", jour=date(2026, 9, 2))
    _plein("100", "655", date(2026, 9, 3))
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # achat de 10 pièces à 5 000 + main-d'œuvre
    Depense.objects.filter(origine__in=[OrigineDepense.ACHAT_STOCK, OrigineDepense.MAIN_OEUVRE_OR]).update(
        date_depense=date(2026, 9, 10)
    )

    charges = services.charges(*SEPT)

    assert charges == {
        "depenses": Decimal("20000"),
        "carburant": Decimal("65500"),
        "pieces": Decimal("50000"),  # comptées à l'achat, pas à la sortie vers l'OR
        "main_oeuvre": Decimal("30000"),
        "maintenance": Decimal("80000"),
        "frais_mission": Decimal("0"),
        "total": Decimal("165500"),
    }


def test_indicateurs_du_mois():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    emise(prix="500000", aujourd_hui=date(2026, 9, 12))  # créance non échue au 20/09
    _reglement(facture, "600000", jour=date(2026, 9, 15))
    _depense("100000", jour=date(2026, 9, 5))

    kpi = services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))

    assert kpi["chiffre_affaires"] == Decimal("1500000")  # HT
    assert kpi["encaisse"] == Decimal("600000")
    assert kpi["charges"]["total"] == Decimal("100000")
    assert kpi["marge_nette"] == Decimal("1400000")
    assert kpi["creances"]["total"] == Decimal("1180000") - Decimal("600000") + Decimal("590000")
    assert kpi["creances"]["nombre_echues"] == 0
    assert kpi["tresorerie"] == Decimal("500000")  # 600 000 encaissés - 100 000 dépensés


def test_la_marge_peut_etre_negative():
    _depense("300000", jour=date(2026, 9, 5))

    assert services.indicateurs(*SEPT)["marge_nette"] == Decimal("-300000")


def test_un_utilisateur_de_role_rh_saisit_desormais_comme_la_finance():
    """Retour réunion : la RH fait tout ce que fait la FINANCES, y compris la trésorerie."""
    assert _manuel(acteur=UserFactory(role=Role.RH)).pk
```

## Étape 3 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -64,4 +64,5 @@
     "apps.fuel",
     "apps.billing",
+    "apps.finance",
 ]
 
```

```bash
python manage.py makemigrations finance
python manage.py migrate
```

**Résultat attendu :** `Create model MouvementManuel`, puis `Applying finance.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/finance/tests/test_demandes.py apps/finance/tests/test_frais_mission_receivers.py apps/finance/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `17 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

Essai dans le shell (base sans règlement ni dépense) :

```bash
python manage.py shell -c "from apps.finance import services as s; t = s.soldes_par_compte(); print(sorted(t), t['total'])"
```

**Résultat attendu :** `['BANQUE', 'CAISSE', 'MOBILE_MONEY', 'total'] 0`.

## Ce qu'il faut retenir

- Une app qui **agrège** doit **appeler** les services des autres, pas recopier leurs règles.
- Ne pas confondre **économique** (charges, marge) et **réel** (trésorerie) : deux vérités, deux chiffres.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 14 : app finance (trésorerie par compte, indicateurs du mois)"
```

---

[← Chapitre 13](13-billing.md) · [Sommaire](README.md) · [Chapitre 15 →](15-notifications.md)
