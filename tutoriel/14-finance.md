# Chapitre 14 — La trésorerie : l'app finance

> 37 fichier(s) dans ce chapitre, 4886 lignes de code.

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
> chiffres**. Le **rapprochement bancaire** (compte Banque uniquement : saisie du relevé, suggestion de
> pointage même sens/montant, écart) vit dans ces mêmes `models.py`/`services.py` ; son écran arrive plus tard,
> au chapitre « Écrans : facturation, dépenses et trésorerie ».

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
mkdir -p apps\accounting apps\accounting\management apps\accounting\management\commands apps\accounting\tests apps\finance apps\finance\management apps\finance\management\commands apps\finance\tests
touch apps/accounting/__init__.py
touch apps/accounting/management/__init__.py
touch apps/finance/__init__.py
touch apps/finance/management/__init__.py
touch apps/accounting/management/commands/__init__.py
touch apps/finance/management/commands/__init__.py
touch apps/accounting/tests/__init__.py
touch apps/finance/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle et services

#### `apps/finance/models.py`

*252 lignes*

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


class NatureMouvement(models.TextChoices):
    """Nature du mouvement — détermine son compte de contrepartie comptable (accounting, P4 de
    avenant-comptabilite-syscohada.md) : un solde d'ouverture ou un apport créditent le capital, un
    retrait débite le compte de l'exploitant, des frais bancaires sont une charge."""

    SOLDE_OUVERTURE = "SOLDE_OUVERTURE", _("Solde d'ouverture")
    APPORT = "APPORT", _("Apport de l'exploitant")
    RETRAIT = "RETRAIT", _("Retrait de l'exploitant")
    FRAIS_BANCAIRE = "FRAIS_BANCAIRE", _("Frais bancaires")
    AUTRE = "AUTRE", _("Autre")


class MouvementManuel(BaseModel):
    """Entrée ou sortie de trésorerie qui n'est ni un règlement ni une dépense.

    Exemples : solde d'ouverture, apport, frais bancaires, retrait. Les règlements de factures
    et les dépenses alimentent la trésorerie tout seuls (cahier-des-charges.md:196-198).
    """

    sens = models.CharField(_("sens"), max_length=6, choices=SensMouvement.choices)
    nature = models.CharField(
        _("nature"), max_length=16, choices=NatureMouvement.choices, default=NatureMouvement.AUTRE
    )
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


class LigneReleve(BaseModel):
    """Une ligne du relevé bancaire, saisie à la main pour la confronter à la trésorerie déjà
    enregistrée (rapprochement bancaire — cahier-des-charges.md:199,
    avenant-comptabilite-autonomie.md § Lot G).

    Une fois pointée, elle porte l'origine et l'identifiant du mouvement de trésorerie
    (``finance.services.mouvements``, un règlement/une dépense/un mouvement manuel) auquel elle
    correspond ; ``mouvement_origine``/``mouvement_id`` restent vides tant qu'elle ne l'est pas.
    """

    date_operation = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=200)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    sens = models.CharField(_("sens"), max_length=6, choices=SensMouvement.choices)
    reference = models.CharField(_("référence"), max_length=100, blank=True)
    pointee = models.BooleanField(_("pointée"), default=False)
    mouvement_origine = models.CharField(
        _("origine du mouvement rapproché"), max_length=10, blank=True,
        help_text=_("REGLEMENT, DEPENSE ou MANUEL — renseignée une fois la ligne pointée."),
    )
    mouvement_id = models.PositiveBigIntegerField(_("identifiant du mouvement rapproché"), null=True, blank=True)
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("ligne de relevé bancaire")
        verbose_name_plural = _("lignes de relevé bancaire")
        ordering = ["-date_operation", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="ligne_releve_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_sens_display()} {self.montant} : {self.libelle}"


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

*508 lignes* — Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

```python
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

*37 lignes*

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
        from .models import DemandeDepense, EnveloppeDepense, LigneReleve, MouvementManuel, OrdreDecaissement

        audit_model(MouvementManuel, module="FINANCES")
        audit_model(EnveloppeDepense, module="FINANCES")
        audit_model(DemandeDepense, module="FINANCES")
        audit_model(OrdreDecaissement, module="FINANCES")
        audit_model(LigneReleve, module="FINANCES")
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
        enregistrer(
            EntreeMenu(
                "Rapprochement bancaire", "finance:rapprochement", "fa-money-check-alt",
                permissions.CONSULTATION, ordre=64,
            )
        )
```

#### `apps/accounting/README.md`

*96 lignes* — accounting

```markdown
# accounting

Rôle : comptabilité en partie double (SYSCOHADA révisé) — cahier-des-charges.md:340. Dépend de
`billing` et `finance` (architecture.md). Nouveau chantier (avenant-comptabilite-syscohada.md),
livré par lot indépendant comme R1-R8 (`avenant-separation-des-taches.md`).

**Phase 1** : fondations — plan comptable, moteur d'écritures toujours équilibrées, écriture
générée automatiquement à la validation d'une facture (« une facture émise génère la créance
client et l'écriture comptable équilibrée », cahier-des-charges.md:340).

**Phase 2** : encaissements — écriture générée automatiquement à l'enregistrement d'un règlement
(débit trésorerie selon le mode de paiement, crédit client).

**Phase 3** : dépenses automatiques du parc auto/missions — écriture générée automatiquement pour
un plein, un achat de pièces, une main-d'œuvre d'OR, un frais de mission confirmé ou un ordre de
décaissement exécuté ; reclassement de trésorerie quand la Finance corrige après coup le mode
d'une dépense provisoire.

**Phase 4** : saisie manuelle — écriture générée automatiquement pour un mouvement manuel de
trésorerie (`finance.MouvementManuel`, champ `nature` pour déduire le compte de contrepartie) ;
écran de saisie manuelle d'opérations diverses (brouillon → ajout/retrait de lignes → validation
par la DIRECTION, cycle calqué sur `Facture`).

**Phase 5** : exercice comptable et clôture — un exercice (année civile) s'ouvre tout
seul à la première écriture qui le concerne ; la DIRECTION peut le clôturer (contrôle strict),
ce qui verrouille définitivement toute nouvelle écriture datée dans sa période. Refusé s'il reste
des brouillons non résolus dans la période.

**Phase 6 (ce lot, dernière de la feuille de route)** : rapports en lecture seule — grand livre
d'un compte avec solde cumulé, balance générale de tous les comptes mouvementés, bilan (cumulé
depuis l'origine) et compte de résultat (strictement borné à l'exercice choisi). Aucun nouveau
modèle ni signal : uniquement des agrégations sur les écritures déjà posées par les Phases 1-5.

Entités : `Compte` (plan comptable, table de référence), `EcritureComptable` (en-tête, numérotée
par journal via `core.services.prochain_numero` — vide tant qu'elle est en `BROUILLON`),
`LigneEcriture` (ligne débit/crédit, append-only une fois l'écriture validée, modifiable tant
qu'elle est en brouillon), `ExerciceComptable` (année, période, statut `OUVERT`/`CLOTURE`).
Une écriture validée ne se modifie ni ne se supprime : seule une contre-passation (non livrée) la
corrige. Un exercice clôturé ne se rouvre jamais.

Service central : `services.passer_ecriture(...)` — garantit lui-même l'équilibre (débit ==
crédit), l'idempotence par `(origine, origine_id)` et que l'exercice de la date n'est pas
clôturé, jamais l'appelant ; toujours `VALIDEE` directement (usage automatique). Chaque événement
automatique a sa fonction dédiée qui construit les lignes puis appelle `passer_ecriture` :
`comptabiliser_facture_validee`, `comptabiliser_un_reglement`,
`comptabiliser_une_depense_automatique` (dépenses automatiques *et* manuelles, les 8 catégories
de `billing.CategorieDepense` — `avenant-comptabilite-autonomie.md` § Lot C), `reclasser_mode_depense`
(sans `origine`/`origine_id`, voir « Limite connue » P3), `comptabiliser_un_mouvement_manuel`.

La saisie manuelle passe par un cycle brouillon/validation distinct :
`creer_ecriture_manuelle` → `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant
que `BROUILLON`) → `valider_ecriture_manuelle` (DIRECTION, contrôle **strict**, vérifie
l'équilibre et attribue le numéro) ou `abandonner_ecriture_manuelle` (soft delete du brouillon).

`services.exercice_pour(date)` renvoie (et crée si besoin, `OUVERT`) l'exercice d'une date —
même principe que `core.services.prochain_numero`. `services.cloturer_exercice(exercice, acteur)`
verrouille la période (DIRECTION, strict), refusé s'il reste des brouillons dans la période.

Rapports (Phase 6, lecture seule) : `services.grand_livre_avec_solde(compte, debut=, fin=)`
(lignes d'un compte + solde cumulé), `services.balance(debut=, fin=)` (tous les comptes
mouvementés, total débit/crédit et solde par compte), `services.compte_de_resultat(exercice)`
(produits/charges strictement dans l'exercice), `services.bilan(exercice)` (actif/passif cumulés
depuis l'origine jusqu'à la fin de l'exercice, résultat net ajouté au passif pour l'affichage —
**aucune écriture de clôture ne l'impute réellement au compte 120000**, voir « Limite connue »
dans `avenant-comptabilite-syscohada.md` § P6).

Déclenchement (automatique) : signaux `billing.signals.facture_a_comptabiliser`,
`reglement_a_comptabiliser`, `depense_a_comptabiliser`, `depense_mode_a_reclasser`, et
`finance.signals.mouvement_a_comptabiliser` — tous émis en `send()` **brut** (pas
`emettre()`/`send_robust`) : une écriture qui échoue à s'équilibrer (ou tombe dans un exercice
clôturé) annule l'opération d'origine plutôt que de laisser un grand livre incomplet.

Reprise de l'historique (événements déjà enregistrés avant la mise en service de chaque lot) :
`python manage.py comptabiliser_historique_factures`, `comptabiliser_historique_reglements`,
`comptabiliser_historique_depenses` (chacune avec `[--depuis AAAA-MM-JJ] [--dry-run]`).

Accès : `permissions.CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH, lecture) ; `SAISIE_OD` (mêmes
rôles, opérations diverses) ; `VALIDATION_OD` (DIRECTION seule, strict) ; `CLOTURE_EXERCICE`
(DIRECTION seule, strict) ; `GESTION_PLAN_COMPTABLE` (mêmes rôles que `SAISIE_OD` — créer/modifier
un compte, `avenant-comptabilite-autonomie.md` § Lot F). Écrans :
`/comptabilite/plan-comptable/` (liste, création, modification — numéro et nature fixés à la
création, un compte ne se supprime jamais, seulement désactivé),
`/comptabilite/operations-diverses/` (liste, création, fiche avec ajout/retrait de ligne,
validation, abandon), `/comptabilite/exercices/` (liste, clôture),
`/comptabilite/grand-livre/` (formulaire compte + période), `/comptabilite/balance/` (formulaire
période), `/comptabilite/bilan/` et `/comptabilite/compte-de-resultat/` (sélecteur d'exercice,
le plus récent par défaut), `/comptabilite/declaration-tva/` (TVA collectée 443300 − TVA
déductible 445200 sur une période, le mois en cours par défaut —
`services.declaration_tva`, `avenant-comptabilite-autonomie.md` § Lot E) — ces 5 derniers
accessibles depuis le menu « Rapports comptables », chacun avec une version imprimable
(`.../imprimer/`, même mécanisme que `finance.tresorerie` — voir
`avenant-comptabilite-autonomie.md` § Lot B).

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail, à
valider par un expert-comptable avant mise en production — aucun plan comptable existant côté
cabinet externe n'a été fourni à ce stade.
```

#### `apps/finance/README.md`

*109 lignes* — finance

````markdown
# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.
`MouvementManuel.nature` (`NatureMouvement` : solde d'ouverture, apport, retrait, frais bancaires,
autre) détermine le compte de contrepartie comptable — voir `apps/accounting/README.md` (P4).

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

**Rapprochement bancaire** (`/finances/rapprochement/`, Lot G — avenant-comptabilite-autonomie.md) :
confronte les lignes du relevé bancaire, saisies à la main (pas d'import de fichier — décision
confirmée), aux mouvements déjà enregistrés sur le compte Banque (`services.mouvements(compte="BANQUE")`
: règlements, dépenses, mouvements manuels — jamais la Caisse ni le Mobile Money). Chaque ligne non
pointée se voit proposer des suggestions (`services.suggestions_pointage`, même sens et montant,
triées par date la plus proche) ; la Finance confirme (`pointer_ligne_releve`) ou dépointe
(`depointer_ligne_releve`) en cas d'erreur. L'écran affiche le solde du relevé, celui des mouvements
enregistrés et l'écart entre les deux sur la période choisie (`services.rapprochement_bancaire`) ;
un écart qui persiste après pointage signale une opération jamais saisie (frais bancaires, par
exemple) — à corriger par l'opération diverse existante (`apps/accounting/README.md`), pas un nouveau
mécanisme. Les écritures comptables (partie double, SYSCOHADA) sont générées automatiquement depuis
chaque événement de trésorerie — voir `apps/accounting/README.md` et `avenant-comptabilite-syscohada.md`.

Rapport imprimable de la trésorerie (`/finances/imprimer/`, bouton « Imprimer ») : soldes par compte, synthèse et journal de la période filtrée, mêmes filtres que l'écran, plafonné à 500 lignes (voir `apps/core/README.md`).
````

#### `apps/accounting/constants.py`

*58 lignes* — Numéros de comptes utilisés par le code (ancrages internes, pas de saisie utilisateur).

```python
"""Numéros de comptes utilisés par le code (ancrages internes, pas de saisie utilisateur).

Le plan comptable complet (``migrations/0002_plan_comptable_seed.py``) est une liste de travail
à valider par un expert-comptable avant mise en production (aucun cabinet externe consulté à ce
stade) ; seuls les comptes ci-dessous sont mobilisés par la Phase 1.
"""

from apps.billing.models import CategorieDepense, CompteTresorerie
from apps.finance.models import NatureMouvement

from .models import Journal

COMPTE_CLIENTS = "411000"
COMPTE_VENTES_TRANSPORT = "706100"
COMPTE_TVA_COLLECTEE = "443300"
COMPTE_TVA_DEDUCTIBLE = "445200"

# billing.models.CategorieDepense -> Compte.numero — les 4 catégories automatiques
# (billing.models.CATEGORIES_AUTOMATIQUES) et les 4 catégories de saisie manuelle sont toutes
# mobilisées (avenant-comptabilite-autonomie.md § Lot C). Péages rattachés aux frais de mission
# (comptes de déplacement) ; Entretien au même compte que la main-d'œuvre des OR (prestataires
# extérieurs) ; Frais administratifs et Autre au compte générique de charges diverses — mapping
# de départ, à valider par un expert-comptable comme le reste du plan comptable.
CATEGORIE_DEPENSE_VERS_COMPTE = {
    CategorieDepense.CARBURANT: "605100",
    CategorieDepense.PIECES: "605800",
    CategorieDepense.MAINTENANCE: "624100",
    CategorieDepense.FRAIS_MISSION: "628100",
    CategorieDepense.PEAGES: "628100",
    CategorieDepense.ENTRETIEN: "624100",
    CategorieDepense.FRAIS_ADMIN: "658000",
    CategorieDepense.AUTRE: "658000",
}

# finance.models.NatureMouvement -> Compte.numero (contrepartie du mouvement manuel de trésorerie).
NATURE_MOUVEMENT_VERS_COMPTE = {
    NatureMouvement.SOLDE_OUVERTURE: "101000",
    NatureMouvement.APPORT: "101000",
    NatureMouvement.RETRAIT: "108000",
    NatureMouvement.FRAIS_BANCAIRE: "631000",
    NatureMouvement.AUTRE: "658000",
}

# apps.billing.models.CompteTresorerie -> Compte.numero (Mobile Money reste fusionné pour les
# 3 opérateurs, cf. avenant-comptabilite-syscohada.md).
COMPTE_TRESORERIE_VERS_COMPTE = {
    CompteTresorerie.BANQUE: "521000",
    CompteTresorerie.CAISSE: "571000",
    CompteTresorerie.MOBILE_MONEY: "521900",
}

# apps.billing.models.CompteTresorerie -> Journal : le Mobile Money, dématérialisé, n'a pas de
# journal auxiliaire dédié dans les 5 journaux SYSCOHADA standards — rattaché à la Banque.
COMPTE_TRESORERIE_VERS_JOURNAL = {
    CompteTresorerie.BANQUE: Journal.BANQUE,
    CompteTresorerie.CAISSE: Journal.CAISSE,
    CompteTresorerie.MOBILE_MONEY: Journal.BANQUE,
}
```

#### `apps/accounting/models.py`

*222 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

from .exceptions import EcritureVerrouillee


class NatureCompte(models.TextChoices):
    """Sens naturel d'un compte du plan comptable — détermine son solde normal."""

    ACTIF = "ACTIF", _("Actif")
    PASSIF = "PASSIF", _("Passif")
    CHARGE = "CHARGE", _("Charge")
    PRODUIT = "PRODUIT", _("Produit")


class Compte(models.Model):
    """Un compte du plan comptable SYSCOHADA révisé.

    Table de référence technique (comme ``core.CompteurNumero``) : jamais soft-supprimée,
    seulement désactivée (``actif=False``) si elle ne doit plus servir à de nouvelles écritures.
    """

    numero = models.CharField(_("numéro"), max_length=10, unique=True)
    libelle = models.CharField(_("libellé"), max_length=150)
    nature = models.CharField(_("nature"), max_length=10, choices=NatureCompte.choices)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("compte")
        verbose_name_plural = _("plan comptable")
        ordering = ["numero"]

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class Journal(models.TextChoices):
    """5 journaux auxiliaires SYSCOHADA — chaque écriture appartient à l'un d'eux."""

    ACHATS = "ACH", _("Achats")
    VENTES = "VTE", _("Ventes")
    BANQUE = "BQ", _("Banque")
    CAISSE = "CAI", _("Caisse")
    OPERATIONS_DIVERSES = "OD", _("Opérations diverses")


class SensEcriture(models.TextChoices):
    DEBIT = "DEBIT", _("Débit")
    CREDIT = "CREDIT", _("Crédit")


class StatutEcriture(models.TextChoices):
    """Une écriture automatique naît toujours ``VALIDEE`` (elle découle d'un événement déjà
    validé ailleurs, cahier-des-charges.md:340). ``BROUILLON`` sert à la saisie manuelle
    (opérations diverses), pas encore livrée à ce stade."""

    BROUILLON = "BROUILLON", _("Brouillon")
    VALIDEE = "VALIDEE", _("Validée")


class EcritureComptable(BaseModel):
    """En-tête d'une écriture comptable — cahier-des-charges.md:340 (« écriture comptable
    équilibrée »). Une fois ``VALIDEE``, elle ne se modifie ni ne se supprime : seule une
    contre-passation (nouvelle écriture inverse) corrige une erreur.
    """

    numero = models.CharField(_("numéro"), max_length=20, blank=True)
    journal = models.CharField(_("journal"), max_length=3, choices=Journal.choices)
    date_ecriture = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=255)
    piece_reference = models.CharField(_("pièce justificative"), max_length=30, blank=True)
    origine = models.CharField(_("origine"), max_length=30, blank=True)
    origine_id = models.PositiveIntegerField(_("ID origine"), null=True, blank=True)
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutEcriture.choices, default=StatutEcriture.VALIDEE
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation = models.DateTimeField(_("validée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("écriture comptable")
        verbose_name_plural = _("écritures comptables")
        ordering = ["-date_ecriture", "-pk"]
        indexes = [models.Index(fields=["journal", "date_ecriture"])]
        constraints = [
            models.UniqueConstraint(
                fields=["numero"], condition=~Q(numero=""), name="ecriture_numero_unique"
            ),
            models.UniqueConstraint(
                fields=["origine", "origine_id"],
                condition=~Q(origine=""),
                name="ecriture_une_par_origine",
            ),
        ]

    def __str__(self):
        return self.numero or f"{self.journal} — {self.libelle}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            statut_en_base = (
                type(self).all_objects.filter(pk=self.pk).values_list("statut", flat=True).first()
            )
            if statut_en_base == StatutEcriture.VALIDEE:
                raise EcritureVerrouillee(
                    "Une écriture validée ne se modifie pas : contre-passez-la."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Une écriture encore en brouillon peut être abandonnée (soft delete, ``BaseModel``) ;
        une écriture validée ne se supprime jamais, seule une contre-passation la corrige."""
        if self.statut == StatutEcriture.VALIDEE:
            raise EcritureVerrouillee("Une écriture validée ne se supprime jamais : contre-passez-la.")
        super().delete(*args, **kwargs)


class LigneEcriture(models.Model):
    """Ligne débit ou crédit d'une écriture — append-only, comme ``inventory.MouvementStock``."""

    ecriture = models.ForeignKey(
        EcritureComptable, verbose_name=_("écriture"), on_delete=models.CASCADE, related_name="lignes"
    )
    compte = models.ForeignKey(
        Compte, verbose_name=_("compte"), on_delete=models.PROTECT, related_name="lignes"
    )
    sens = models.CharField(_("sens"), max_length=6, choices=SensEcriture.choices)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    libelle = models.CharField(_("libellé"), max_length=255, blank=True)
    # Rattachement générique optionnel (ex. tiers_type="CLIENT", tiers_id=client.pk) : sert au
    # suivi par tiers (compte 411 par client) sans dépendre de ``customers`` au niveau du modèle.
    tiers_type = models.CharField(_("type de tiers"), max_length=20, blank=True)
    tiers_id = models.PositiveIntegerField(_("ID tiers"), null=True, blank=True)

    class Meta:
        verbose_name = _("ligne d'écriture")
        verbose_name_plural = _("lignes d'écriture")
        ordering = ["ecriture", "pk"]
        indexes = [models.Index(fields=["compte"]), models.Index(fields=["tiers_type", "tiers_id"])]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="ligne_ecriture_montant_positif"),
        ]

    def __str__(self):
        return f"{self.compte.numero} {self.get_sens_display()} {self.montant}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("LigneEcriture est append-only : contre-passez plutôt que modifier.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Une ligne d'une écriture encore en brouillon (saisie manuelle) peut être retirée ; une
        fois l'écriture validée, plus aucune ligne ne se supprime."""
        if self.ecriture.statut == StatutEcriture.VALIDEE:
            raise EcritureVerrouillee(
                "Une ligne d'une écriture validée ne se supprime pas : contre-passez plutôt."
            )
        super().delete(*args, **kwargs)


class StatutExercice(models.TextChoices):
    OUVERT = "OUVERT", _("Ouvert")
    CLOTURE = "CLOTURE", _("Clôturé")


class ExerciceComptable(BaseModel):
    """Exercice comptable — année civile (hypothèse par défaut alignée sur
    ``core.CompteurNumero`` ; le cahier des charges ne précise pas de date de clôture fiscale
    propre à l'entreprise, à confirmer avec l'expert-comptable avant mise en production).

    Auto-créé ``OUVERT`` au passage de la première écriture de son année (même principe que
    ``core.services.prochain_numero``) : aucun geste explicite n'est requis pour « ouvrir »
    une nouvelle année. Une fois ``CLOTURE``, aucune écriture ne peut plus être datée dans sa
    période — jamais rouvert (une correction après clôture attend une phase de contre-passation).
    """

    annee = models.PositiveSmallIntegerField(_("année"), unique=True)
    date_debut = models.DateField(_("début"))
    date_fin = models.DateField(_("fin"))
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutExercice.choices, default=StatutExercice.OUVERT
    )
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("clôturé par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_cloture = models.DateTimeField(_("clôturé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("exercice comptable")
        verbose_name_plural = _("exercices comptables")
        ordering = ["-annee"]

    def __str__(self):
        return f"Exercice {self.annee}"

    def delete(self, *args, **kwargs):
        raise ValueError("ExerciceComptable ne se supprime jamais.")
```

#### `apps/accounting/exceptions.py`

*31 lignes*

```python
class AccountingError(Exception):
    """Erreur métier de la comptabilité."""


class EcritureNonEquilibree(AccountingError):
    """Le total des débits ne correspond pas au total des crédits."""


class CompteInconnu(AccountingError):
    """Le compte demandé n'existe pas dans le plan comptable, ou n'est plus actif."""


class CompteDejaExistant(AccountingError):
    """Un compte porte déjà ce numéro dans le plan comptable."""


class EcritureVerrouillee(AccountingError):
    """Une écriture déjà validée ne se modifie ni ne se supprime."""


class ActionComptableNonAutorisee(AccountingError):
    """L'utilisateur n'a pas le droit d'effectuer cette action."""


class ExerciceCloture(AccountingError):
    """L'exercice comptable concerné est déjà clôturé : aucune écriture ne peut plus y être
    datée, ni y être clôturé une seconde fois."""


class ClotureImpossible(AccountingError):
    """Des brouillons non résolus (saisie manuelle) empêchent de clôturer l'exercice."""
```

#### `apps/accounting/services.py`

*635 lignes* — Moteur d'écritures comptables — conventions.md §2.

```python
"""Moteur d'écritures comptables — conventions.md §2.

``passer_ecriture`` est le seul point d'entrée qui écrit une ``EcritureComptable`` : il garantit
lui-même l'équilibre (jamais l'appelant), à l'image de ``_exiger_role``/``_exiger_statut`` dans
``apps.billing.services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from django.db import transaction
from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import COMPTE_DU_MODE
from apps.core.services import prochain_numero

from .constants import (
    CATEGORIE_DEPENSE_VERS_COMPTE,
    COMPTE_CLIENTS,
    COMPTE_TRESORERIE_VERS_COMPTE,
    COMPTE_TRESORERIE_VERS_JOURNAL,
    COMPTE_TVA_COLLECTEE,
    COMPTE_TVA_DEDUCTIBLE,
    COMPTE_VENTES_TRANSPORT,
    NATURE_MOUVEMENT_VERS_COMPTE,
)
from . import permissions
from .exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteDejaExistant,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from .models import (
    Compte,
    EcritureComptable,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    NatureCompte,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)

ZERO = Decimal("0")


@dataclass(frozen=True)
class LigneSaisie:
    """Une ligne débit ou crédit à passer, avant résolution du ``Compte``."""

    compte: str
    sens: str
    montant: Decimal
    libelle: str = ""
    tiers_type: str = ""
    tiers_id: int | None = None


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionComptableNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _exiger_brouillon(ecriture: EcritureComptable, action: str) -> None:
    if ecriture.statut != StatutEcriture.BROUILLON:
        raise EcritureVerrouillee(f"Impossible de {action} : l'écriture est « {ecriture.get_statut_display()} ».")


def creer_compte(acteur, *, numero: str, libelle: str, nature: str) -> Compte:
    """Ajoute un compte au plan comptable (avenant-comptabilite-autonomie.md § Lot F). Le numéro
    et la nature ne se modifient plus ensuite (:func:`modifier_compte`) : seuls le libellé et
    l'activation le peuvent, pour ne jamais reclasser silencieusement des écritures déjà
    posées."""
    _exiger_role(acteur, permissions.GESTION_PLAN_COMPTABLE, "créer un compte")
    numero = numero.strip()
    if not numero:
        raise CompteInconnu("Le numéro de compte est obligatoire.")
    if Compte.objects.filter(numero=numero).exists():
        raise CompteDejaExistant(f"Le compte {numero} existe déjà.")
    libelle = libelle.strip()
    if not libelle:
        raise CompteInconnu("Le libellé est obligatoire.")
    if nature not in NatureCompte.values:
        raise CompteInconnu("Nature de compte inconnue.")
    return Compte.objects.create(numero=numero, libelle=libelle, nature=nature)


def modifier_compte(compte: Compte, acteur, *, libelle: str, actif: bool) -> Compte:
    """Corrige le libellé d'un compte et/ou le désactive (jamais supprimé, voir
    ``Compte.__doc__``) : un compte désactivé ne peut plus être utilisé dans une nouvelle
    écriture, mais son historique reste lisible dans le grand livre."""
    _exiger_role(acteur, permissions.GESTION_PLAN_COMPTABLE, "modifier un compte")
    libelle = libelle.strip()
    if not libelle:
        raise CompteInconnu("Le libellé est obligatoire.")
    compte.libelle, compte.actif = libelle, actif
    compte.save(update_fields=["libelle", "actif"])
    return compte


def exercice_pour(date_ecriture: date) -> ExerciceComptable:
    """Renvoie l'exercice comptable (année civile) de cette date, le crée ``OUVERT`` s'il
    n'existe pas encore — même principe que ``core.services.prochain_numero`` : aucun geste
    explicite n'est requis pour « ouvrir » une nouvelle année."""
    exercice, _ = ExerciceComptable.objects.get_or_create(
        annee=date_ecriture.year,
        defaults={
            "date_debut": date(date_ecriture.year, 1, 1),
            "date_fin": date(date_ecriture.year, 12, 31),
        },
    )
    return exercice


def _exiger_exercice_ouvert(date_ecriture: date) -> None:
    exercice = exercice_pour(date_ecriture)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(
            f"L'exercice {exercice.annee} est clôturé : aucune écriture ne peut plus y être datée."
        )


@transaction.atomic
def cloturer_exercice(exercice: ExerciceComptable, acteur) -> ExerciceComptable:
    """Clôture un exercice : verrouille toute nouvelle écriture datée dans sa période. Refusé s'il
    reste des brouillons (saisie manuelle non validée) dans la période — à valider ou abandonner
    avant de clôturer, pour ne jamais clôturer une année à l'insu d'une saisie en attente.
    Contrôle **strict** (``acteur.role``) : réservé à la DIRECTION, comme ``Facture.valider`` —
    jamais l'ADMIN ni un superutilisateur à sa place. Jamais rouvert ensuite."""
    _exiger_role(acteur, permissions.CLOTURE_EXERCICE, "clôturer un exercice", strict=True)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(f"L'exercice {exercice.annee} est déjà clôturé.")
    brouillons = EcritureComptable.objects.filter(
        statut=StatutEcriture.BROUILLON,
        date_ecriture__gte=exercice.date_debut,
        date_ecriture__lte=exercice.date_fin,
    ).count()
    if brouillons:
        raise ClotureImpossible(
            f"{brouillons} écriture(s) en brouillon reste(nt) dans cette période : "
            "validez-les ou abandonnez-les avant de clôturer."
        )
    exercice.statut = StatutExercice.CLOTURE
    exercice.cloture_par = acteur
    exercice.date_cloture = timezone.now()
    exercice.save(update_fields=["statut", "cloture_par", "date_cloture", "updated_at"])
    return exercice


def _comptes_actifs(numeros: set[str]) -> dict[str, Compte]:
    comptes = {c.numero: c for c in Compte.objects.filter(numero__in=numeros, actif=True)}
    manquants = numeros - comptes.keys()
    if manquants:
        raise CompteInconnu(
            f"Compte(s) inconnu(s) ou inactif(s) dans le plan comptable : {', '.join(sorted(manquants))}."
        )
    return comptes


@transaction.atomic
def passer_ecriture(
    *,
    journal: str,
    date_ecriture: date,
    libelle: str,
    lignes: Sequence[LigneSaisie],
    origine: str = "",
    origine_id: int | None = None,
    piece_reference: str = "",
) -> EcritureComptable:
    """Crée une écriture équilibrée (débit == crédit) et ses lignes.

    Idempotente par ``(origine, origine_id)`` : rejouer le même événement source renvoie
    l'écriture déjà comptabilisée, sans en recréer une seconde. Tout est vérifié avant la
    moindre écriture en base : au moins 2 lignes, montants strictement positifs, comptes
    existants et actifs, total débit égal au total crédit.
    """
    if origine:
        existante = EcritureComptable.objects.filter(origine=origine, origine_id=origine_id).first()
        if existante is not None:
            return existante

    _exiger_exercice_ouvert(date_ecriture)

    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    for ligne in lignes:
        if ligne.montant <= 0:
            raise EcritureNonEquilibree("Chaque montant doit être strictement positif.")

    comptes = _comptes_actifs({ligne.compte for ligne in lignes})

    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )

    ecriture = EcritureComptable.objects.create(
        numero=prochain_numero(journal, date_ecriture.year),
        journal=journal,
        date_ecriture=date_ecriture,
        libelle=libelle,
        piece_reference=piece_reference,
        origine=origine,
        origine_id=origine_id,
        statut=StatutEcriture.VALIDEE,
    )
    LigneEcriture.objects.bulk_create(
        LigneEcriture(
            ecriture=ecriture,
            compte=comptes[ligne.compte],
            sens=ligne.sens,
            montant=ligne.montant,
            libelle=ligne.libelle,
            tiers_type=ligne.tiers_type,
            tiers_id=ligne.tiers_id,
        )
        for ligne in lignes
    )
    return ecriture


def comptabiliser_facture_validee(facture) -> EcritureComptable:
    """Écriture d'une facture validée : débite le client (TTC), crédite les ventes (HT) et la
    TVA collectée (si le taux n'est pas nul) — cahier-des-charges.md:340. Idempotent (voir
    :func:`passer_ecriture`) : reprendre une facture déjà comptabilisée ne recrée rien."""
    lignes = [
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.DEBIT,
            montant=facture.montant_ttc,
            tiers_type="CLIENT",
            tiers_id=facture.client_id,
        ),
        LigneSaisie(
            compte=COMPTE_VENTES_TRANSPORT, sens=SensEcriture.CREDIT, montant=facture.montant_ht
        ),
    ]
    if facture.montant_tva > 0:
        lignes.append(
            LigneSaisie(
                compte=COMPTE_TVA_COLLECTEE, sens=SensEcriture.CREDIT, montant=facture.montant_tva
            )
        )
    return passer_ecriture(
        journal=Journal.VENTES,
        date_ecriture=facture.date_emission,
        libelle=f"Facture {facture.numero} — {facture.client}",
        lignes=lignes,
        origine="FACTURE",
        origine_id=facture.pk,
        piece_reference=facture.numero,
    )


def comptabiliser_un_reglement(reglement) -> EcritureComptable:
    """Écriture d'un règlement encaissé : débite la trésorerie (banque/caisse/mobile money selon
    le mode de paiement), crédite le client (411) — solde la créance. Idempotent (voir
    :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[reglement.mode]
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=reglement.montant,
        ),
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.CREDIT,
            montant=reglement.montant,
            tiers_type="CLIENT",
            tiers_id=reglement.facture.client_id,
        ),
    ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=reglement.date_reglement,
        libelle=f"Règlement {reglement.facture.numero} — {reglement.facture.client}",
        lignes=lignes,
        origine="REGLEMENT",
        origine_id=reglement.pk,
        piece_reference=reglement.facture.numero,
    )


def comptabiliser_une_depense_automatique(depense) -> EcritureComptable:
    """Écriture d'une dépense, automatique (plein, achat de pièces, main-d'œuvre d'OR, frais de
    mission, ordre de décaissement) ou manuelle (péages, entretien, frais administratifs, autre —
    avenant-comptabilite-autonomie.md § Lot C) : débite la charge (montant HT) selon la catégorie,
    débite la TVA déductible si ``depense.montant_tva`` est renseignée (§ Lot D), crédite la
    trésorerie au montant TTC selon le mode de paiement. Pour une dépense automatique, le mode est
    provisoire (Caisse par défaut) sauf pour un ordre de décaissement, dont le mode réel est connu
    dès l'exécution — voir :func:`reclasser_mode_depense` pour la correction ultérieure ; une
    dépense saisie à la main connaît déjà son mode réel. Idempotent (voir :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    lignes = [
        LigneSaisie(
            compte=CATEGORIE_DEPENSE_VERS_COMPTE[depense.categorie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant_ht,
        ),
    ]
    if depense.montant_tva > 0:
        lignes.append(
            LigneSaisie(compte=COMPTE_TVA_DEDUCTIBLE, sens=SensEcriture.DEBIT, montant=depense.montant_tva)
        )
    lignes.append(
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        )
    )
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=depense.date_depense,
        libelle=depense.libelle,
        lignes=lignes,
        origine="DEPENSE",
        origine_id=depense.pk,
        piece_reference=depense.reference,
    )


def reclasser_mode_depense(depense, ancien_mode: str) -> EcritureComptable | None:
    """Corrige le compte de trésorerie d'une dépense automatique après coup (Finance corrige le
    mode réel via ``billing.services.changer_mode_depense``) : contre-passe l'ancien compte,
    impute le nouveau, plutôt que de modifier l'écriture d'origine (append-only). Ne crée rien si
    l'ancien et le nouveau mode partagent le même compte de trésorerie (ex. virement → chèque,
    tous deux Banque).

    Non idempotente (pas d'``origine``/``origine_id``) : une correction manuelle rejouée deux fois
    créerait deux reclassements — cas rare, accepté pour cette phase (voir « Limite connue »,
    avenant-comptabilite-syscohada.md)."""
    ancien_compte_tresorerie = COMPTE_DU_MODE[ancien_mode]
    nouveau_compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    if ancien_compte_tresorerie == nouveau_compte_tresorerie:
        return None
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[nouveau_compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant,
        ),
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[ancien_compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        ),
    ]
    return passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=timezone.localdate(),
        libelle=f"Reclassement du mode de paiement — {depense.libelle}",
        lignes=lignes,
    )


def comptabiliser_un_mouvement_manuel(mouvement) -> EcritureComptable:
    """Écriture d'un mouvement manuel de trésorerie (solde d'ouverture, apport, retrait, frais
    bancaires…) : la contrepartie se déduit de sa nature (``finance.models.NatureMouvement``).
    Une entrée débite la trésorerie et crédite la contrepartie ; une sortie fait l'inverse.
    Idempotent (voir :func:`passer_ecriture`)."""
    from apps.finance.models import SensMouvement

    compte_tresorerie = COMPTE_DU_MODE[mouvement.mode]
    compte_contrepartie = NATURE_MOUVEMENT_VERS_COMPTE[mouvement.nature]
    if mouvement.sens == SensMouvement.ENTREE:
        lignes = [
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    else:
        lignes = [
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=mouvement.date_mouvement,
        libelle=mouvement.libelle,
        lignes=lignes,
        origine="MOUVEMENT",
        origine_id=mouvement.pk,
        piece_reference=mouvement.reference,
    )


# --- saisie manuelle (opérations diverses) ---


@transaction.atomic
def creer_ecriture_manuelle(acteur, *, date_ecriture: date, libelle: str) -> EcritureComptable:
    """Ouvre un brouillon d'écriture manuelle (journal Opérations diverses) : pas de numéro tant
    qu'elle n'est pas validée (comme ``Facture``, pour ne pas laisser de trou de numérotation si
    elle est abandonnée), pas de ligne encore."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    if not libelle.strip():
        raise EcritureNonEquilibree("Le libellé est obligatoire.")
    _exiger_exercice_ouvert(date_ecriture)
    return EcritureComptable.objects.create(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=date_ecriture,
        libelle=libelle.strip(),
        statut=StatutEcriture.BROUILLON,
        cree_par=acteur,
    )


@transaction.atomic
def ajouter_ligne_manuelle(
    ecriture: EcritureComptable, acteur, *, compte: str, sens: str, montant: Decimal, libelle: str = ""
) -> LigneEcriture:
    """Ajoute une ligne à un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    _exiger_brouillon(ecriture, "ajouter une ligne")
    montant = Decimal(montant)
    if montant <= 0:
        raise EcritureNonEquilibree("Le montant doit être strictement positif.")
    comptes = _comptes_actifs({compte})
    return LigneEcriture.objects.create(
        ecriture=ecriture, compte=comptes[compte], sens=sens, montant=montant, libelle=libelle.strip()
    )


def supprimer_ligne_manuelle(ligne: LigneEcriture, acteur) -> None:
    """Retire une ligne d'un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "modifier une écriture")
    _exiger_brouillon(ligne.ecriture, "retirer une ligne")
    ligne.delete()


@transaction.atomic
def abandonner_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> None:
    """Abandonne un brouillon d'écriture manuelle (soft delete) : aucun numéro n'a encore été
    attribué, rien à contre-passer."""
    _exiger_role(acteur, permissions.SAISIE_OD, "abandonner une écriture")
    _exiger_brouillon(ecriture, "abandonner l'écriture")
    ecriture.delete(deleted_by=acteur)


@transaction.atomic
def valider_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> EcritureComptable:
    """Verrouille un brouillon d'écriture manuelle : vérifie l'équilibre (au moins 2 lignes,
    débit == crédit), attribue son numéro, la statut passe à ``VALIDEE`` — définitif, réservé à la
    DIRECTION (contrôle strict, comme ``Facture.valider`` : jamais l'ADMIN ni un superutilisateur
    à sa place)."""
    _exiger_role(acteur, permissions.VALIDATION_OD, "valider une écriture", strict=True)
    _exiger_brouillon(ecriture, "valider l'écriture")
    _exiger_exercice_ouvert(ecriture.date_ecriture)
    lignes = list(ecriture.lignes.all())
    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )
    ecriture.numero = prochain_numero(ecriture.journal, ecriture.date_ecriture.year)
    ecriture.statut = StatutEcriture.VALIDEE
    ecriture.valide_par = acteur
    ecriture.date_validation = timezone.now()
    ecriture.save(update_fields=["numero", "statut", "valide_par", "date_validation", "updated_at"])
    return ecriture


def grand_livre(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> QuerySet[LigneEcriture]:
    """Lignes d'un compte, triées par date d'écriture. Un brouillon d'opération diverse n'est pas
    encore approuvé par la DIRECTION (services.valider_ecriture_manuelle) : il ne doit jamais
    apparaître dans un rapport officiel, donc seules les écritures VALIDEE sont incluses."""
    lignes = LigneEcriture.objects.filter(
        compte=compte, ecriture__statut=StatutEcriture.VALIDEE
    ).select_related("ecriture", "compte")
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    return lignes.order_by("ecriture__date_ecriture", "pk")


def grand_livre_avec_solde(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> list[dict]:
    """Lignes du compte avec leur solde cumulé (débit augmente le solde, crédit le diminue —
    convention SYSCOHADA, valable pour un compte d'actif/charge ; un compte de passif/produit se
    lit alors en négatif, ce qui reste correct pour vérifier l'équilibre ligne à ligne)."""
    solde = ZERO
    resultat = []
    for ligne in grand_livre(compte, debut=debut, fin=fin):
        solde += ligne.montant if ligne.sens == SensEcriture.DEBIT else -ligne.montant
        resultat.append({"ligne": ligne, "solde_cumule": solde})
    return resultat


def _agreger_par_compte(lignes: QuerySet[LigneEcriture]) -> list[dict]:
    """Total débit/crédit par compte mouvementé dans ``lignes``."""
    return list(
        lignes.values("compte__id", "compte__numero", "compte__libelle", "compte__nature")
        .annotate(
            total_debit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.DEBIT)), Value(ZERO)),
            total_credit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.CREDIT)), Value(ZERO)),
        )
        .order_by("compte__numero")
    )


def balance(*, debut: date | None = None, fin: date | None = None) -> list[dict]:
    """Balance générale : total débit/crédit et solde de chaque compte mouvementé sur la période
    (tous comptes confondus, toutes dates si ``debut``/``fin`` omis). Seules les écritures
    VALIDEE comptent — un brouillon d'opération diverse ne doit jamais fausser la balance
    officielle avant l'approbation de la DIRECTION."""
    lignes = LigneEcriture.objects.filter(ecriture__statut=StatutEcriture.VALIDEE)
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    resultat = []
    for ligne in _agreger_par_compte(lignes):
        solde = ligne["total_debit"] - ligne["total_credit"]
        resultat.append(
            {
                **ligne,
                "solde_debiteur": solde if solde > 0 else ZERO,
                "solde_crediteur": -solde if solde < 0 else ZERO,
            }
        )
    return resultat


def declaration_tva(*, debut: date, fin: date) -> dict:
    """TVA collectée (443300, sur les ventes) moins TVA déductible (445200, sur les dépenses) sur
    la période = TVA nette à payer (positive) ou crédit de TVA reportable (négative), comme une
    déclaration périodique réelle (avenant-comptabilite-autonomie.md § Lot E). Seules les
    écritures VALIDEE comptent."""
    lignes = LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__gte=debut,
        ecriture__date_ecriture__lte=fin,
        compte__numero__in=[COMPTE_TVA_COLLECTEE, COMPTE_TVA_DEDUCTIBLE],
    )
    agrege = {ligne["compte__numero"]: ligne for ligne in _agreger_par_compte(lignes)}
    collectee = agrege.get(COMPTE_TVA_COLLECTEE)
    deductible = agrege.get(COMPTE_TVA_DEDUCTIBLE)
    tva_collectee = (collectee["total_credit"] - collectee["total_debit"]) if collectee else ZERO
    tva_deductible = (deductible["total_debit"] - deductible["total_credit"]) if deductible else ZERO
    return {
        "debut": debut,
        "fin": fin,
        "tva_collectee": tva_collectee,
        "tva_deductible": tva_deductible,
        "tva_nette": tva_collectee - tva_deductible,
    }


def compte_de_resultat(exercice: ExerciceComptable) -> dict:
    """Produits moins charges de l'exercice = résultat net (bénéfice ou perte). Calculé à la
    demande à partir des lignes de la période (rapport de situation) : aucune écriture de
    clôture n'existe encore pour transférer ce résultat dans le bilan de l'exercice suivant —
    voir « Limite connue », avenant-comptabilite-syscohada.md § P6. Seules les écritures VALIDEE
    comptent, jamais un brouillon d'opération diverse non encore approuvé par la DIRECTION."""
    lignes = LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__gte=exercice.date_debut,
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.CHARGE, NatureCompte.PRODUIT],
    )
    charges, produits = [], []
    total_charges = total_produits = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.CHARGE:
            montant = ligne["total_debit"] - ligne["total_credit"]
            charges.append({**ligne, "montant": montant})
            total_charges += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            produits.append({**ligne, "montant": montant})
            total_produits += montant
    return {
        "charges": charges,
        "produits": produits,
        "total_charges": total_charges,
        "total_produits": total_produits,
        "resultat_net": total_produits - total_charges,
    }


def bilan(exercice: ExerciceComptable) -> dict:
    """Actif et passif cumulés depuis l'origine jusqu'à la fin de l'exercice (un bilan est une
    photo à une date, pas une période — contrairement au compte de résultat). Le résultat net de
    l'exercice (voir :func:`compte_de_resultat`) est ajouté au passif pour équilibrer le bilan,
    puisqu'il n'existe pas encore d'écriture de clôture qui l'impute au compte 120000. Seules les
    écritures VALIDEE comptent, jamais un brouillon d'opération diverse non encore approuvé par
    la DIRECTION."""
    lignes = LigneEcriture.objects.filter(
        ecriture__statut=StatutEcriture.VALIDEE,
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.ACTIF, NatureCompte.PASSIF],
    )
    actif, passif = [], []
    total_actif = total_passif = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.ACTIF:
            montant = ligne["total_debit"] - ligne["total_credit"]
            actif.append({**ligne, "montant": montant})
            total_actif += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            passif.append({**ligne, "montant": montant})
            total_passif += montant
    resultat_net = compte_de_resultat(exercice)["resultat_net"]
    return {
        "actif": actif,
        "passif": passif,
        "total_actif": total_actif,
        "total_passif": total_passif,
        "resultat_net": resultat_net,
        "total_passif_avec_resultat": total_passif + resultat_net,
    }
```

#### `apps/finance/signals.py`

*34 lignes* — Événements des dépenses pré-approuvées du parc auto (R2), souscrits par ``notifications``.

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

# Un mouvement manuel de trésorerie vient d'être enregistré : à comptabiliser (même principe que
# ``billing.signals.facture_a_comptabiliser`` — ``send()`` **brut**, pas ``send_robust`` : une
# écriture qui échoue à s'équilibrer annule l'enregistrement plutôt que de laisser un mouvement de
# trésorerie non tracé). Argument : ``mouvement``.
mouvement_a_comptabiliser = Signal()


def emettre(signal: Signal, **arguments) -> None:
    for recepteur, resultat in signal.send_robust(sender=None, **arguments):
        if isinstance(resultat, Exception):
            logger.error("Récepteur %r en erreur", recepteur, exc_info=resultat)
```

#### `apps/accounting/permissions.py`

*24 lignes* — Qui peut consulter, saisir, valider et clôturer la comptabilité.

```python
"""Qui peut consulter, saisir, valider et clôturer la comptabilité.

Cohérent avec ``billing.permissions`` : la RH fait tout ce que fait la FINANCES, la DIRECTION a
la même largeur que l'ADMIN — sauf sur la validation d'une écriture manuelle et la clôture d'un
exercice, strictement réservées à la DIRECTION (comme la validation d'une facture, jamais
l'ADMIN/un superutilisateur à sa place : ce sont les deux seuls contrôles comptables a posteriori
sur une saisie humaine).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})

# Saisie d'une écriture manuelle (opérations diverses, P4) : créer le brouillon, y ajouter/retirer
# des lignes, l'abandonner.
SAISIE_OD = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
# Validation d'une écriture manuelle : DIRECTION seule, contrôle strict.
VALIDATION_OD = frozenset({Role.DIRECTION})
# Clôture d'un exercice comptable (P5) : DIRECTION seule, contrôle strict.
CLOTURE_EXERCICE = frozenset({Role.DIRECTION})
# Gestion du plan comptable (créer/modifier un compte, Lot F autonomie comptable) : même largeur
# que la saisie d'une écriture manuelle, pas de contrôle Direction a posteriori (ce n'est pas une
# transaction financière, seulement le paramétrage du référentiel).
GESTION_PLAN_COMPTABLE = frozenset({Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH})
```

#### `apps/accounting/receivers.py`

*47 lignes* — Génération automatique des écritures comptables depuis les événements de facturation et de

```python
"""Génération automatique des écritures comptables depuis les événements de facturation et de
trésorerie.

Souscrit aux signaux **bloquants** de ``billing`` et ``finance`` (``facture_a_comptabiliser``,
``reglement_a_comptabiliser``, ``depense_a_comptabiliser``, ``depense_mode_a_reclasser``,
``mouvement_a_comptabiliser``, envoyés en ``send()`` brut, pas ``emettre()``/``send_robust``) :
si l'écriture ne peut pas s'équilibrer, l'opération d'origine (validation de la facture,
enregistrement du règlement ou du mouvement, dépense automatique, correction du mode) est
annulée plutôt que de laisser un grand livre incomplet — cahier-des-charges.md:340.
"""

from django.dispatch import receiver

from apps.billing.signals import (
    depense_a_comptabiliser,
    depense_mode_a_reclasser,
    facture_a_comptabiliser,
    reglement_a_comptabiliser,
)
from apps.finance.signals import mouvement_a_comptabiliser

from . import services


@receiver(facture_a_comptabiliser)
def comptabiliser_une_facture_validee(sender, facture, **kwargs) -> None:
    services.comptabiliser_facture_validee(facture)


@receiver(reglement_a_comptabiliser)
def comptabiliser_un_reglement_recu(sender, reglement, **kwargs) -> None:
    services.comptabiliser_un_reglement(reglement)


@receiver(depense_a_comptabiliser)
def comptabiliser_une_depense(sender, depense, **kwargs) -> None:
    services.comptabiliser_une_depense_automatique(depense)


@receiver(depense_mode_a_reclasser)
def reclasser_le_mode_d_une_depense(sender, depense, ancien_mode, **kwargs) -> None:
    services.reclasser_mode_depense(depense, ancien_mode)


@receiver(mouvement_a_comptabiliser)
def comptabiliser_un_mouvement(sender, mouvement, **kwargs) -> None:
    services.comptabiliser_un_mouvement_manuel(mouvement)
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

#### `apps/accounting/admin.py`

*45 lignes*

```python
from django.contrib import admin

from .models import Compte, EcritureComptable, ExerciceComptable, LigneEcriture


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ("numero", "libelle", "nature", "actif")
    list_filter = ("nature", "actif")
    search_fields = ("numero", "libelle")


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 0
    fields = ("compte", "sens", "montant", "libelle", "tiers_type", "tiers_id")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EcritureComptable)
class EcritureComptableAdmin(admin.ModelAdmin):
    list_display = ("numero", "journal", "date_ecriture", "libelle", "statut", "piece_reference")
    list_filter = ("journal", "statut")
    search_fields = ("numero", "libelle", "piece_reference")
    inlines = [LigneEcritureInline]

    def get_queryset(self, request):
        return EcritureComptable.objects.select_related("cree_par", "valide_par")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(admin.ModelAdmin):
    list_display = ("annee", "date_debut", "date_fin", "statut", "cloture_par")
    list_filter = ("statut",)

    def has_delete_permission(self, request, obj=None):
        return False
```

#### `apps/accounting/apps.py`

*44 lignes*

```python
from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounting"
    label = "accounting"
    verbose_name = "Comptabilité"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, receivers  # noqa: F401  (connecte les récepteurs)
        from .models import Compte, EcritureComptable, ExerciceComptable, LigneEcriture

        audit_model(Compte, module="COMPTABILITE")
        audit_model(EcritureComptable, module="COMPTABILITE")
        audit_model(LigneEcriture, module="COMPTABILITE")
        audit_model(ExerciceComptable, module="COMPTABILITE")
        enregistrer(
            EntreeMenu(
                "Plan comptable", "accounting:plan_comptable", "fa-list-check",
                permissions.CONSULTATION, ordre=63,
            )
        )
        enregistrer(
            EntreeMenu(
                "Opérations diverses", "accounting:ecritures_manuelles", "fa-scale-balanced",
                permissions.CONSULTATION, ordre=64,
            )
        )
        enregistrer(
            EntreeMenu(
                "Exercices comptables", "accounting:exercices", "fa-calendar-days",
                permissions.CONSULTATION, ordre=65,
            )
        )
        enregistrer(
            EntreeMenu(
                "Rapports comptables", "accounting:balance", "fa-chart-column",
                permissions.CONSULTATION, ordre=66,
            )
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

#### `apps/accounting/management/commands/comptabiliser_historique_depenses.py`

*73 lignes* — Reprise, à la demande, des dépenses déjà enregistrées avant la mise en service de la

```python
"""Reprise, à la demande, des dépenses déjà enregistrées avant la mise en service de la
comptabilisation automatique (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures``/``comptabiliser_historique_reglements``. Reprend toutes les
dépenses, automatiques (catégories CARBURANT, PIECES, MAINTENANCE, FRAIS_MISSION) et de saisie
manuelle (péages, entretien, frais administratifs, autre — comptabilisées depuis
avenant-comptabilite-autonomie.md § Lot C).

- pas de solde d'ouverture (ou aucune dépense antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par dépense, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Depense


class Command(BaseCommand):
    help = (
        "Comptabilise les dépenses déjà enregistrées avant ce lot (voir --dry-run pour "
        "prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les dépenses enregistrées à partir de cette date (bornes incluses).",
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

        depenses = Depense.objects.all()
        if date_depuis is not None:
            depenses = depenses.filter(date_depense__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="DEPENSE", origine_id__in=depenses.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for depense in depenses:
                services.comptabiliser_une_depense_automatique(depense)
                if depense.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} dépense(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
```

#### `apps/accounting/management/commands/comptabiliser_historique_factures.py`

*76 lignes* — Reprise, à la demande, des factures déjà validées avant la mise en service de la

```python
"""Reprise, à la demande, des factures déjà validées avant la mise en service de la
comptabilisation automatique (``accounting.receivers``) : sans cette commande, ces factures
n'auraient jamais leur écriture, alors qu'elles ont bien généré une créance client réelle.

Volontairement **pas une migration automatique**, sur le même principe que
``finance.comptabiliser_historique_parc_auto`` : sur une base qui a déjà un solde d'ouverture
saisi en comptabilité, reprendre l'historique complet compterait deux fois les créances
antérieures à ce solde. À exécuter une fois, après avoir vérifié la date du solde d'ouverture
(s'il y en a un) :
- pas de solde d'ouverture (ou aucune facture antérieure à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par facture, comme le mécanisme normal) : relancer la
commande après un ``--depuis`` mal choisi, corrigé, ne recrée pas ce qui a déjà été comptabilisé.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import STATUTS_EMIS, Facture


class Command(BaseCommand):
    help = (
        "Comptabilise les factures déjà validées avant ce lot (voir --dry-run pour prévisualiser, "
        "--depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les factures émises à partir de cette date (bornes incluses).",
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

        factures = Facture.objects.filter(statut__in=STATUTS_EMIS)
        if date_depuis is not None:
            factures = factures.filter(date_emission__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="FACTURE", origine_id__in=factures.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilisees = 0
        deja_presentes = 0
        with transaction.atomic():
            for facture in factures:
                services.comptabiliser_facture_validee(facture)
                if facture.pk in deja:
                    deja_presentes += 1
                else:
                    comptabilisees += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilisees} facture(s) comptabilisée(s) "
            f"({deja_presentes} déjà présentes, inchangées)."
        )
```

#### `apps/accounting/management/commands/comptabiliser_historique_reglements.py`

*72 lignes* — Reprise, à la demande, des règlements déjà enregistrés avant la mise en service de la

```python
"""Reprise, à la demande, des règlements déjà enregistrés avant la mise en service de la
comptabilisation automatique des encaissements (``accounting.receivers``) — même principe que
``comptabiliser_historique_factures`` et ``finance.comptabiliser_historique_parc_auto`` : sur une
base qui a déjà un solde d'ouverture saisi en comptabilité, reprendre l'historique complet
compterait deux fois les encaissements antérieurs à ce solde.

- pas de solde d'ouverture (ou aucun règlement antérieur à sa date) → lancer sans ``--depuis`` ;
- un solde d'ouverture à une date donnée → lancer avec ``--depuis`` fixé au lendemain de cette date.

Rejouable sans double compte (une écriture par règlement, comme le mécanisme normal).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounting import services
from apps.accounting.models import EcritureComptable
from apps.billing.models import Reglement


class Command(BaseCommand):
    help = (
        "Comptabilise les règlements déjà enregistrés avant ce lot (voir --dry-run pour "
        "prévisualiser, --depuis pour ignorer ce qui précède un solde d'ouverture)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--depuis", metavar="AAAA-MM-JJ",
            help="Ne reprend que les règlements enregistrés à partir de cette date (bornes incluses).",
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

        reglements = Reglement.objects.select_related("facture", "facture__client")
        if date_depuis is not None:
            reglements = reglements.filter(date_reglement__gte=date_depuis)

        deja = set(
            EcritureComptable.objects.filter(
                origine="REGLEMENT", origine_id__in=reglements.values_list("pk", flat=True)
            ).values_list("origine_id", flat=True)
        )
        comptabilises = 0
        deja_presents = 0
        with transaction.atomic():
            for reglement in reglements:
                services.comptabiliser_un_reglement(reglement)
                if reglement.pk in deja:
                    deja_presents += 1
                else:
                    comptabilises += 1
            if dry_run:
                transaction.set_rollback(True)

        prefixe = "[Simulation, rien n'a été écrit] " if dry_run else ""
        self.stdout.write(
            f"{prefixe}{comptabilises} règlement(s) comptabilisé(s) "
            f"({deja_presents} déjà présents, inchangés)."
        )
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

#### `apps/accounting/tests/factories.py`

*14 lignes*

```python
import factory

from apps.accounting.models import Compte, NatureCompte


class CompteFactory(factory.django.DjangoModelFactory):
    """Compte de test, indépendant du plan comptable seedé (migration 0002)."""

    class Meta:
        model = Compte

    numero = factory.Sequence(lambda n: f"9{n:05d}")
    libelle = factory.Sequence(lambda n: f"Compte de test {n}")
    nature = NatureCompte.CHARGE
```

#### `apps/accounting/tests/test_models.py`

*60 lignes* — Immuabilité : une écriture validée (et ses lignes) ne se modifie ni ne se supprime.

```python
"""Immuabilité : une écriture validée (et ses lignes) ne se modifie ni ne se supprime."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import EcritureVerrouillee
from apps.accounting.models import Journal, SensEcriture
from apps.accounting.services import LigneSaisie

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _ecriture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )


def test_une_ecriture_validee_ne_se_modifie_pas():
    ecriture = _ecriture()

    ecriture.libelle = "Modifié"
    with pytest.raises(EcritureVerrouillee):
        ecriture.save()


def test_une_ecriture_validee_ne_se_supprime_pas():
    ecriture = _ecriture()

    with pytest.raises(EcritureVerrouillee):
        ecriture.delete()


def test_une_ligne_d_ecriture_ne_se_modifie_pas():
    ligne = _ecriture().lignes.first()

    ligne.montant = Decimal("1")
    with pytest.raises(ValueError):
        ligne.save()


def test_une_ligne_d_une_ecriture_validee_ne_se_supprime_pas():
    ligne = _ecriture().lignes.first()

    with pytest.raises(EcritureVerrouillee):
        ligne.delete()
```

#### `apps/accounting/tests/test_receivers.py`

*281 lignes* — Intégration : la validation d'une facture et l'enregistrement d'un règlement (billing)

```python
"""Intégration : la validation d'une facture et l'enregistrement d'un règlement (billing)
génèrent toujours leur écriture comptable — cahier-des-charges.md:340."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.constants import COMPTE_CLIENTS, COMPTE_TVA_COLLECTEE, COMPTE_VENTES_TRANSPORT
from apps.accounting.models import EcritureComptable, Journal, SensEcriture
from apps.billing import services as billing_services
from apps.billing.models import CategorieDepense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import a_valider, direction, emise, finances
from apps.customers.tests.factories import ClientFactory
from apps.finance import services as finance_services
from apps.finance.models import NatureMouvement, SensMouvement

pytestmark = pytest.mark.django_db


def test_facture_validee_genere_une_ecriture_equilibree():
    facture = emise(prix="1000000")

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)

    assert ecriture.journal == Journal.VENTES
    assert ecriture.numero.startswith("VTE-2026-")
    assert ecriture.piece_reference == facture.numero
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.DEBIT, facture.montant_ttc)
    assert lignes[COMPTE_VENTES_TRANSPORT] == (SensEcriture.CREDIT, facture.montant_ht)
    assert lignes[COMPTE_TVA_COLLECTEE] == (SensEcriture.CREDIT, facture.montant_tva)
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    total_credit = sum(m for sens, m in lignes.values() if sens == SensEcriture.CREDIT)
    assert total_debit == total_credit == facture.montant_ttc


def test_ligne_clients_est_rattachee_au_client_de_la_facture():
    facture = emise()

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)

    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_une_facture_exoneree_ne_cree_pas_de_ligne_tva():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = emise(client=client)

    assert facture.montant_tva == 0
    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    assert ecriture.lignes.count() == 2
    assert not ecriture.lignes.filter(compte__numero=COMPTE_TVA_COLLECTEE).exists()


def test_valider_une_facture_deja_validee_ne_duplique_pas_l_ecriture():
    facture = emise()
    nb_avant = EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count()

    from apps.billing.exceptions import TransitionFactureInterdite

    with pytest.raises(TransitionFactureInterdite):
        billing_services.valider(facture, direction())

    assert EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count() == nb_avant == 1


# --- règlements (Phase 2) ---


@pytest.mark.parametrize(
    ("mode", "compte_attendu", "journal_attendu"),
    [
        (ModePaiement.VIREMENT, "521000", Journal.BANQUE),
        (ModePaiement.CHEQUE, "521000", Journal.BANQUE),
        (ModePaiement.ESPECES, "571000", Journal.CAISSE),
        (ModePaiement.WAVE, "521900", Journal.BANQUE),
        (ModePaiement.ORANGE_MONEY, "521900", Journal.BANQUE),
        (ModePaiement.MTN_MONEY, "521900", Journal.BANQUE),
    ],
)
def test_reglement_enregistre_genere_une_ecriture_selon_le_mode(mode, compte_attendu, journal_attendu):
    facture = emise(prix="1000000")

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("100000"), mode=mode, date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    assert ecriture.journal == journal_attendu
    assert ecriture.date_ecriture == date(2026, 9, 5)
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_attendu] == (SensEcriture.DEBIT, Decimal("100000"))
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.CREDIT, Decimal("100000"))


def test_ligne_clients_du_reglement_est_rattachee_au_client():
    facture = emise()

    reglement = billing_services.enregistrer_reglement(
        facture, finances(), montant=facture.montant_ttc, mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 5),
    )

    ecriture = EcritureComptable.objects.get(origine="REGLEMENT", origine_id=reglement.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)
    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_deux_reglements_sur_la_meme_facture_generent_deux_ecritures_distinctes():
    facture = emise(prix="1000000")

    premier = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.ESPECES,
        date_reglement=date(2026, 9, 5),
    )
    second = billing_services.enregistrer_reglement(
        facture, finances(), montant=Decimal("600000"), mode=ModePaiement.VIREMENT,
        date_reglement=date(2026, 9, 10),
    )

    ecritures = EcritureComptable.objects.filter(origine="REGLEMENT", origine_id__in=[premier.pk, second.pk])
    assert ecritures.count() == 2


# --- dépenses automatiques (Phase 3) ---


def _depense_automatique(origine_id, *, categorie=CategorieDepense.CARBURANT, mode=ModePaiement.ESPECES):
    return billing_services.comptabiliser_depense_automatique(
        origine=OrigineDepense.PLEIN, origine_id=origine_id, categorie=categorie,
        date_depense=date(2026, 9, 5), libelle="Plein — AB-1234-CI", montant=Decimal("50000"),
        mode=mode,
    )


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.CARBURANT, "605100"),
        (CategorieDepense.PIECES, "605800"),
        (CategorieDepense.MAINTENANCE, "624100"),
        (CategorieDepense.FRAIS_MISSION, "628100"),
    ],
)
def test_depense_automatique_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = _depense_automatique(1001, categorie=categorie)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE  # ESPECES par défaut
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


@pytest.mark.parametrize(
    ("categorie", "compte_charge"),
    [
        (CategorieDepense.PEAGES, "628100"),
        (CategorieDepense.ENTRETIEN, "624100"),
        (CategorieDepense.FRAIS_ADMIN, "658000"),
        (CategorieDepense.AUTRE, "658000"),
    ],
)
def test_depense_manuelle_genere_une_ecriture_selon_la_categorie(categorie, compte_charge):
    depense = billing_services.enregistrer_depense(
        finances(), categorie=categorie, date_depense=date(2026, 9, 5), libelle="Test",
        montant=Decimal("12000"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[compte_charge] == (SensEcriture.DEBIT, Decimal("12000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("12000"))


def test_depense_avec_tva_deductible_genere_une_ecriture_a_3_lignes():
    depense = billing_services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=date(2026, 9, 5), libelle="Péage facturé",
        montant=Decimal("11800"), montant_tva=Decimal("1800"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["628100"] == (SensEcriture.DEBIT, Decimal("10000"))  # charge au HT
    assert lignes["445200"] == (SensEcriture.DEBIT, Decimal("1800"))  # TVA déductible
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("11800"))  # trésorerie au TTC
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    assert total_debit == Decimal("11800")  # écriture équilibrée


def test_depense_sans_tva_ne_genere_aucune_ligne_445200():
    depense = billing_services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=date(2026, 9, 5), libelle="Péage sans facture",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert not ecriture.lignes.filter(compte__numero="445200").exists()
    assert ecriture.lignes.count() == 2


def test_rejouer_la_meme_source_ne_duplique_pas_l_ecriture():
    premiere = _depense_automatique(1002)
    seconde = _depense_automatique(1002)  # même origine_id : Depense.get_or_create retombe dessus

    assert premiere.pk == seconde.pk
    assert EcritureComptable.objects.filter(origine="DEPENSE", origine_id=premiere.pk).count() == 1


def test_un_ordre_de_decaissement_avec_mode_reel_ne_passe_pas_par_la_caisse_provisoire():
    depense = _depense_automatique(1003, categorie=CategorieDepense.PIECES, mode=ModePaiement.VIREMENT)

    ecriture = EcritureComptable.objects.get(origine="DEPENSE", origine_id=depense.pk)
    assert ecriture.journal == Journal.BANQUE
    assert ecriture.lignes.filter(compte__numero="521000", sens=SensEcriture.CREDIT).exists()


def test_changer_le_mode_reclasse_la_tresorerie():
    depense = _depense_automatique(1004)  # ESPECES -> 571000 par défaut

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    reclassements = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES)
    ecriture = reclassements.latest("pk")
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("50000"))
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))


def test_changer_le_mode_vers_le_meme_compte_de_tresorerie_ne_reclasse_rien():
    depense = _depense_automatique(1005, mode=ModePaiement.VIREMENT)  # Banque
    nb_avant = EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count()

    billing_services.changer_mode_depense(depense, finances(), mode=ModePaiement.CHEQUE)  # Banque aussi

    assert EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES).count() == nb_avant


# --- mouvements manuels de trésorerie (Phase 4) ---


@pytest.mark.parametrize(
    ("nature", "compte_contrepartie"),
    [
        (NatureMouvement.SOLDE_OUVERTURE, "101000"),
        (NatureMouvement.APPORT, "101000"),
        (NatureMouvement.RETRAIT, "108000"),
        (NatureMouvement.FRAIS_BANCAIRE, "631000"),
        (NatureMouvement.AUTRE, "658000"),
    ],
)
def test_une_entree_de_mouvement_manuel_debite_la_tresorerie(nature, compte_contrepartie):
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.ENTREE, date_mouvement=date(2026, 9, 5), libelle="Test",
        montant=Decimal("200000"), mode=ModePaiement.VIREMENT, nature=nature,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.BANQUE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["521000"] == (SensEcriture.DEBIT, Decimal("200000"))
    assert lignes[compte_contrepartie] == (SensEcriture.CREDIT, Decimal("200000"))


def test_une_sortie_de_mouvement_manuel_credite_la_tresorerie():
    mouvement = finance_services.enregistrer_mouvement(
        finances(), sens=SensMouvement.SORTIE, date_mouvement=date(2026, 9, 5), libelle="Retrait",
        montant=Decimal("50000"), mode=ModePaiement.ESPECES, nature=NatureMouvement.RETRAIT,
    )

    ecriture = EcritureComptable.objects.get(origine="MOUVEMENT", origine_id=mouvement.pk)
    assert ecriture.journal == Journal.CAISSE
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes["571000"] == (SensEcriture.CREDIT, Decimal("50000"))
    assert lignes["108000"] == (SensEcriture.DEBIT, Decimal("50000"))
```

#### `apps/accounting/tests/test_services.py`

*759 lignes* — Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle

```python
"""Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle
d'opérations diverses (Phase 4) ; exercice comptable et clôture (Phase 5) ; rapports (Phase 6)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteDejaExistant,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from apps.accounting.models import (
    Compte,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _lignes_equilibrees(charge, tresorerie, montant="1000"):
    montant = Decimal(montant)
    return [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=montant),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=montant),
    ]


def test_passer_ecriture_equilibree_cree_lignes():
    charge, tresorerie = CompteFactory(), CompteFactory()

    ecriture = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ecriture.numero.startswith("OD-2026-")
    assert ecriture.lignes.count() == 2
    assert {l.compte_id for l in ecriture.lignes.all()} == {charge.pk, tresorerie.pk}


def test_passer_ecriture_desequilibree_leve_erreur_et_ne_cree_rien():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("900")),
    ]

    with pytest.raises(EcritureNonEquilibree, match="1000.*900|900.*1000"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )

    assert LigneEcriture.objects.count() == 0


def test_passer_ecriture_refuse_un_montant_negatif_ou_nul():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("0")),
    ]

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )


def test_passer_ecriture_refuse_moins_de_deux_lignes():
    charge = CompteFactory()

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000"))],
        )


def test_passer_ecriture_refuse_un_compte_inconnu():
    tresorerie = CompteFactory()

    with pytest.raises(CompteInconnu, match="999999"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[
                LigneSaisie(compte="999999", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
                LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            ],
        )


def test_passer_ecriture_refuse_un_compte_inactif():
    charge, tresorerie = CompteFactory(actif=False), CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_passer_ecriture_idempotente_par_origine():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = _lignes_equilibrees(charge, tresorerie)

    premiere = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=lignes, origine="TEST", origine_id=42,
    )
    seconde = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Autre libellé",
        lignes=lignes, origine="TEST", origine_id=42,
    )

    assert premiere.pk == seconde.pk
    assert LigneEcriture.objects.count() == 2  # pas de doublon


def test_grand_livre_filtre_par_compte_et_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes_annee = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 12, 31))
    lignes_premier_semestre = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 3, 31))

    assert lignes_annee.count() == 2
    assert lignes_premier_semestre.count() == 1


def test_grand_livre_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    assert services.grand_livre(charge).count() == 0


# --- plan comptable (Lot F, autonomie comptable) ---


def test_creer_un_compte():
    compte = services.creer_compte(
        finances(), numero="999999", libelle="Compte de test", nature="CHARGE"
    )

    assert (compte.numero, compte.libelle, compte.nature, compte.actif) == ("999999", "Compte de test", "CHARGE", True)


def test_creer_un_compte_refuse_un_numero_vide():
    with pytest.raises(CompteInconnu, match="numéro"):
        services.creer_compte(finances(), numero="  ", libelle="x", nature="CHARGE")


def test_creer_un_compte_refuse_une_nature_inconnue():
    with pytest.raises(CompteInconnu, match="Nature"):
        services.creer_compte(finances(), numero="999999", libelle="x", nature="INCONNUE")


def test_creer_un_compte_refuse_un_numero_deja_pris():
    services.creer_compte(finances(), numero="999999", libelle="Premier", nature="CHARGE")

    with pytest.raises(CompteDejaExistant):
        services.creer_compte(finances(), numero="999999", libelle="Second", nature="PRODUIT")


def test_creer_un_compte_refuse_un_libelle_vide():
    with pytest.raises(CompteInconnu, match="libellé"):
        services.creer_compte(finances(), numero="999999", libelle="  ", nature="CHARGE")


def test_creer_un_compte_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_compte(
            UserFactory(role=Role.CHAUFFEUR), numero="999999", libelle="x", nature="CHARGE"
        )


def test_modifier_un_compte_corrige_le_libelle_et_le_statut():
    compte = CompteFactory(libelle="Ancien libellé", actif=True)

    services.modifier_compte(compte, finances(), libelle="Nouveau libellé", actif=False)

    compte.refresh_from_db()
    assert (compte.libelle, compte.actif) == ("Nouveau libellé", False)


def test_modifier_un_compte_refuse_un_libelle_vide():
    compte = CompteFactory()

    with pytest.raises(CompteInconnu, match="libellé"):
        services.modifier_compte(compte, finances(), libelle=" ", actif=True)


def test_modifier_un_compte_refuse_un_role_non_autorise():
    compte = CompteFactory()

    with pytest.raises(ActionComptableNonAutorisee):
        services.modifier_compte(compte, UserFactory(role=Role.CHAUFFEUR), libelle="x", actif=True)


def test_un_compte_desactive_est_refuse_dans_une_nouvelle_ecriture():
    compte = CompteFactory()
    services.modifier_compte(compte, finances(), libelle=compte.libelle, actif=False)
    autre = CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
            lignes=_lignes_equilibrees(compte, autre),
        )


# --- saisie manuelle d'opérations diverses (Phase 4) ---


def test_creer_une_ecriture_manuelle_ouvre_un_brouillon_sans_numero():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.numero == ""
    assert ecriture.lignes.count() == 0


def test_creer_une_ecriture_manuelle_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_ecriture_manuelle(
            UserFactory(role=Role.CHARGE_CLIENTELE), date_ecriture=JOUR, libelle="Test"
        )


def test_ajouter_puis_supprimer_une_ligne_sur_un_brouillon():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    assert ecriture.lignes.count() == 1

    services.supprimer_ligne_manuelle(ligne, finances())
    assert ecriture.lignes.count() == 0


def test_valider_une_ecriture_manuelle_equilibree_attribue_un_numero():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    validee = services.valider_ecriture_manuelle(ecriture, direction())

    assert validee.statut == StatutEcriture.VALIDEE
    assert validee.numero.startswith("OD-2026-")
    assert validee.valide_par is not None


def test_valider_une_ecriture_desequilibree_est_refuse():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    with pytest.raises(EcritureNonEquilibree):
        services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.BROUILLON


def test_seule_la_direction_valide_une_ecriture_manuelle_strict():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_une_fois_validee_on_ne_peut_plus_ajouter_ni_supprimer_de_ligne():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1")
        )
    with pytest.raises(EcritureVerrouillee):
        services.supprimer_ligne_manuelle(ligne, finances())


def test_abandonner_un_brouillon():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    services.abandonner_ecriture_manuelle(ecriture, finances())

    from apps.accounting.models import EcritureComptable

    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()
    assert EcritureComptable.all_objects.get(pk=ecriture.pk).is_deleted


def test_on_ne_peut_pas_abandonner_une_ecriture_deja_validee():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.abandonner_ecriture_manuelle(ecriture, finances())


def test_creer_une_ecriture_manuelle_refuse_un_libelle_vide():
    with pytest.raises(EcritureNonEquilibree):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="   ")


def test_ajouter_une_ligne_refuse_un_montant_negatif_ou_nul():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    with pytest.raises(EcritureNonEquilibree):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")
        )


def test_valider_une_ecriture_avec_deux_lignes_desequilibrees_est_refuse():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("4000")
    )

    with pytest.raises(EcritureNonEquilibree, match="5000.*4000|4000.*5000"):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- exercice comptable et clôture (Phase 5) ---


def test_exercice_pour_cree_l_exercice_de_l_annee_s_il_n_existe_pas():
    exercice = services.exercice_pour(date(2026, 3, 15))

    assert exercice.annee == 2026
    assert exercice.date_debut == date(2026, 1, 1)
    assert exercice.date_fin == date(2026, 12, 31)
    assert exercice.statut == StatutExercice.OUVERT


def test_exercice_pour_est_idempotent():
    premier = services.exercice_pour(date(2026, 3, 15))
    second = services.exercice_pour(date(2026, 11, 1))

    assert premier.pk == second.pk
    assert ExerciceComptable.objects.count() == 1


def test_passer_une_ecriture_cree_son_exercice_au_passage():
    charge, tresorerie = CompteFactory(), CompteFactory()

    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2027, 5, 1), libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ExerciceComptable.objects.filter(annee=2027, statut=StatutExercice.OUVERT).exists()


def test_cloturer_un_exercice_verrouille_les_nouvelles_ecritures():
    charge, tresorerie = CompteFactory(), CompteFactory()
    exercice = services.exercice_pour(JOUR)

    services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE
    assert exercice.cloture_par is not None
    with pytest.raises(ExerciceCloture, match="2026"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Trop tard",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_cloturer_est_reserve_a_la_direction_strict():
    exercice = services.exercice_pour(JOUR)

    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_cloturer_un_exercice_deja_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.cloturer_exercice(exercice, direction())


def test_cloturer_refuse_s_il_reste_des_brouillons_dans_la_periode():
    exercice = services.exercice_pour(JOUR)
    services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Encore en brouillon")

    with pytest.raises(ClotureImpossible, match="1"):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT


def test_creer_une_ecriture_manuelle_dans_un_exercice_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Trop tard")


def test_valider_une_ecriture_manuelle_est_refuse_si_l_exercice_est_devenu_cloture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    # Simule une clôture concurrente (impossible via l'écran, qui bloque tant qu'un brouillon
    # reste dans la période — ce test vérifie la seconde ligne de défense au moment de valider).
    ExerciceComptable.objects.filter(annee=JOUR.year).update(statut=StatutExercice.CLOTURE)

    with pytest.raises(ExerciceCloture):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- rapports : grand livre, balance, bilan, compte de résultat (Phase 6) ---


def _compte(numero):
    return Compte.objects.get(numero=numero)


def test_grand_livre_avec_solde_calcule_le_solde_cumule():
    caisse = _compte("571000")
    autre = CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 10), libelle="Un",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=autre.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 20), libelle="Deux",
        lignes=[
            LigneSaisie(compte=autre.numero, sens=SensEcriture.DEBIT, montant=Decimal("400")),
            LigneSaisie(compte="571000", sens=SensEcriture.CREDIT, montant=Decimal("400")),
        ],
    )

    lignes = services.grand_livre_avec_solde(caisse)

    assert [l["solde_cumule"] for l in lignes] == [Decimal("1000"), Decimal("600")]


def test_balance_agrege_debit_credit_et_solde_par_compte():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie, montant="7000"),
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert lignes[charge.numero]["total_debit"] == Decimal("7000")
    assert lignes[charge.numero]["solde_debiteur"] == Decimal("7000")
    assert lignes[charge.numero]["solde_crediteur"] == Decimal("0")
    assert lignes[tresorerie.numero]["total_credit"] == Decimal("7000")
    assert lignes[tresorerie.numero]["solde_crediteur"] == Decimal("7000")


def test_balance_filtre_par_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes = {l["compte__numero"]: l for l in services.balance(debut=date(2026, 1, 1), fin=date(2026, 3, 31))}

    assert lignes[charge.numero]["total_debit"] == Decimal("1000")


def test_balance_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert charge.numero not in lignes


def test_declaration_tva_calcule_la_tva_nette():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Péage facturé",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("100")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("18")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("118")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("180")
    assert rapport["tva_deductible"] == Decimal("18")
    assert rapport["tva_nette"] == Decimal("162")


def test_declaration_tva_negative_est_un_credit_reportable():
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Grosse dépense facturée",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("180")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("1180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("0")
    assert rapport["tva_deductible"] == Decimal("180")
    assert rapport["tva_nette"] == Decimal("-180")


def test_declaration_tva_filtre_par_periode():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2026, 1, 15), libelle="Vente janvier",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 6, 1), fin=date(2026, 6, 30))

    assert rapport["tva_collectee"] == Decimal("0")


def test_declaration_tva_exclut_les_brouillons_non_valides():
    tva_deductible = _compte("445200")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_deductible"] == Decimal("0")


def test_compte_de_resultat_calcule_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes, tva = _compte("411000"), _compte("706100"), _compte("443300")
    caisse, carburant = _compte("571000"), _compte("605100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Plein",
        lignes=[
            LigneSaisie(compte=carburant.numero, sens=SensEcriture.DEBIT, montant=Decimal("300")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("300")),
        ],
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_produits"] == Decimal("1000")  # la TVA collectée n'est pas un produit
    assert rapport["total_charges"] == Decimal("300")
    assert rapport["resultat_net"] == Decimal("700")


def test_compte_de_resultat_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_charges"] == Decimal("0")
    assert rapport["charges"] == []


def test_bilan_equilibre_avec_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes = _compte("411000"), _compte("706100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("1000")
    assert rapport["total_passif"] == Decimal("0")
    assert rapport["resultat_net"] == Decimal("1000")
    assert rapport["total_passif_avec_resultat"] == rapport["total_actif"] == Decimal("1000")


def test_bilan_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    caisse = _compte("571000")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("0")
    assert rapport["actif"] == []


def test_bilan_est_cumulatif_mais_compte_de_resultat_reste_par_exercice():
    clients, ventes = _compte("411000"), _compte("706100")
    exercice_2025 = services.exercice_pour(date(2025, 6, 1))
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2025, 6, 1), libelle="Vente 2025",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("500")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("500")),
        ],
    )
    exercice_2026 = services.exercice_pour(JOUR)

    bilan_2026 = services.bilan(exercice_2026)
    resultat_2026 = services.compte_de_resultat(exercice_2026)

    assert bilan_2026["total_actif"] == Decimal("500")  # cumulatif : reprend 2025
    assert resultat_2026["total_produits"] == Decimal("0")  # la vente 2025 n'est pas dans 2026
    assert services.compte_de_resultat(exercice_2025)["total_produits"] == Decimal("500")


def test_bilan_classe_aussi_les_comptes_de_passif():
    exercice = services.exercice_pour(JOUR)
    caisse, capital = _compte("571000"), _compte("101000")
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Apport",
        lignes=[
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("2000")),
            LigneSaisie(compte=capital.numero, sens=SensEcriture.CREDIT, montant=Decimal("2000")),
        ],
    )

    rapport = services.bilan(exercice)

    lignes_passif = {l["compte__numero"]: l for l in rapport["passif"]}
    assert lignes_passif[capital.numero]["montant"] == Decimal("2000")
    assert rapport["total_passif"] == Decimal("2000")
    assert rapport["total_actif"] == Decimal("2000")
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

*400 lignes* — Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers.

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


# --- rapprochement bancaire (Lot G) ---


def _ligne_releve(sens=SensMouvement.ENTREE, montant="100000", jour=JOUR, libelle="Virement client",
                   acteur=None, reference=""):
    return services.saisir_ligne_releve(
        acteur or finances(), date_operation=jour, libelle=libelle, montant=Decimal(montant), sens=sens,
        reference=reference,
    )


def test_une_ligne_de_releve_se_saisit_a_la_main():
    ligne = _ligne_releve(reference="REF1")

    assert ligne.pk
    assert ligne.pointee is False
    assert ligne.reference == "REF1"


@pytest.mark.parametrize(
    ("libelle", "montant", "sens", "jour", "message"),
    [
        ("  ", "10", SensMouvement.ENTREE, JOUR, "libellé"),
        ("x", "0", SensMouvement.ENTREE, JOUR, "strictement positif"),
        ("x", "10", "AUTRE", JOUR, "Sens inconnu"),
        ("x", "10", SensMouvement.ENTREE, date(2999, 1, 1), "futur"),
    ],
)
def test_saisie_de_ligne_de_releve_invalide(libelle, montant, sens, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        services.saisir_ligne_releve(
            finances(), date_operation=jour, libelle=libelle, montant=Decimal(montant), sens=sens,
        )


def test_la_saisie_d_une_ligne_de_releve_est_reservee_a_la_saisie_facturation():
    with pytest.raises(ActionFactureNonAutorisee):
        _ligne_releve(acteur=UserFactory(role=Role.PARCAUTO))


def test_les_suggestions_proposent_le_mouvement_banque_de_meme_sens_et_montant_le_plus_proche():
    facture = emise(prix="1000000")
    proche = _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))
    _reglement(facture, "200000", ModePaiement.VIREMENT, jour=date(2026, 9, 3))  # autre montant
    _depense("100000", ModePaiement.ESPECES, jour=date(2026, 9, 4))  # autre compte (Caisse)
    ligne = _ligne_releve(montant="100000", jour=date(2026, 9, 5))

    suggestions = services.suggestions_pointage(ligne)

    assert len(suggestions) == 1
    assert suggestions[0]["origine"] == "REGLEMENT" and suggestions[0]["pk"] == proche.pk


def test_pointer_associe_la_ligne_au_mouvement_choisi():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="100000")

    pointee = services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    assert pointee.pointee is True
    assert pointee.mouvement_origine == "REGLEMENT" and pointee.mouvement_id == reglement.pk


def test_pointer_refuse_un_mouvement_deja_pointe_sur_une_autre_ligne():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    premiere = _ligne_releve(montant="100000")
    services.pointer_ligne_releve(premiere, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)
    seconde = _ligne_releve(montant="100000", libelle="Doublon")

    with pytest.raises(MontantInvalide, match="déjà pointé"):
        services.pointer_ligne_releve(seconde, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)


def test_pointer_refuse_une_origine_inconnue():
    ligne = _ligne_releve()
    with pytest.raises(MontantInvalide, match="Origine"):
        services.pointer_ligne_releve(ligne, finances(), origine="AUTRE", mouvement_id=1)


def test_pointer_est_reserve_a_la_saisie_facturation():
    ligne = _ligne_releve()
    with pytest.raises(ActionFactureNonAutorisee):
        services.pointer_ligne_releve(ligne, UserFactory(role=Role.PARCAUTO), origine="MANUEL", mouvement_id=1)


def test_depointer_annule_le_pointage():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT)
    ligne = _ligne_releve(montant="100000")
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    depointee = services.depointer_ligne_releve(ligne, finances())

    assert depointee.pointee is False
    assert depointee.mouvement_origine == "" and depointee.mouvement_id is None


def test_depointer_est_reserve_a_la_saisie_facturation():
    ligne = _ligne_releve()
    with pytest.raises(ActionFactureNonAutorisee):
        services.depointer_ligne_releve(ligne, UserFactory(role=Role.PARCAUTO))


def test_le_rapprochement_calcule_les_deux_soldes_et_l_ecart_quand_ils_concordent():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))
    ligne = _ligne_releve(montant="100000", jour=date(2026, 9, 4))
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_releve"] == Decimal("100000")
    assert etat["solde_comptable"] == Decimal("100000")
    assert etat["ecart"] == 0
    assert etat["lignes_non_pointees"] == []
    assert etat["mouvements_non_pointes"] == []


def test_le_rapprochement_signale_un_ecart_quand_une_operation_n_a_pas_ete_saisie():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.VIREMENT, jour=date(2026, 9, 4))  # jamais pointé
    _ligne_releve(montant="50000", jour=date(2026, 9, 5))  # frais bancaires jamais comptabilisés

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_releve"] == Decimal("50000")
    assert etat["solde_comptable"] == Decimal("100000")
    assert etat["ecart"] == Decimal("-50000")
    assert len(etat["lignes_non_pointees"]) == 1
    assert len(etat["mouvements_non_pointes"]) == 1


def test_le_rapprochement_ignore_la_caisse_et_le_mobile_money():
    _depense("20000", ModePaiement.ESPECES, jour=date(2026, 9, 4))
    facture = emise(prix="1000000")
    _reglement(facture, "30000", ModePaiement.WAVE, jour=date(2026, 9, 4))

    etat = services.rapprochement_bancaire(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert etat["solde_comptable"] == 0
    assert etat["mouvements_banque"] == []
```

## Étape 3 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -64,4 +64,6 @@
     "apps.fuel",
     "apps.billing",
+    "apps.finance",
+    "apps.accounting",
 ]
 
```

```bash
python manage.py makemigrations accounting
```

Le fichier ci-dessous n'est pas généré par Django : c'est une **migration de données**, écrite à la main, qui charge le plan comptable de départ. Elle dépend de la migration générée à l'instant ; elle ne peut donc être créée qu'après elle.

#### `apps/accounting/migrations/0002_plan_comptable_seed.py`

*52 lignes* — Plan comptable de départ (SYSCOHADA révisé) — liste de travail, à valider par un

```python
"""Plan comptable de départ (SYSCOHADA révisé) — liste de travail, à valider par un
expert-comptable avant mise en production (voir apps/accounting/README.md et
avenant-comptabilite-syscohada.md). Seuls 411000, 706100, 443300 et les 3 comptes de trésorerie
sont mobilisés par le code de la Phase 1 ; le reste est seedé pour ne pas fragmenter la migration
de données quand les lots suivants (dépenses automatiques, saisie manuelle) arriveront.

``RunPython`` idempotent (``update_or_create``) : rejouable sans effet si déjà appliquée.
"""

from django.db import migrations

PLAN_COMPTABLE = [
    ("101000", "Capital social", "PASSIF"),
    ("108000", "Compte de l'exploitant", "PASSIF"),
    ("120000", "Résultat de l'exercice", "PASSIF"),
    ("401000", "Fournisseurs", "PASSIF"),
    ("411000", "Clients", "ACTIF"),
    ("443300", "État, TVA facturée sur ventes", "PASSIF"),
    ("445200", "État, TVA déductible", "ACTIF"),
    ("521000", "Banque", "ACTIF"),
    ("521900", "Mobile Money", "ACTIF"),
    ("571000", "Caisse", "ACTIF"),
    ("605100", "Carburants et lubrifiants", "CHARGE"),
    ("605800", "Pièces détachées et fournitures véhicules", "CHARGE"),
    ("624100", "Entretien, réparations (prestataires extérieurs)", "CHARGE"),
    ("628100", "Frais de mission et déplacements", "CHARGE"),
    ("631000", "Frais bancaires", "CHARGE"),
    ("658000", "Charges diverses de gestion courante", "CHARGE"),
    ("706100", "Prestations de transport", "PRODUIT"),
]


def seeder(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    for numero, libelle, nature in PLAN_COMPTABLE:
        Compte.objects.update_or_create(numero=numero, defaults={"libelle": libelle, "nature": nature})


def retirer(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    Compte.objects.filter(numero__in=[numero for numero, _, _ in PLAN_COMPTABLE]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seeder, retirer),
    ]
```

```bash
python manage.py makemigrations finance
python manage.py migrate
```

**Résultat attendu :** `Create model MouvementManuel`, puis `Applying accounting.0001_initial... OK`, `Applying accounting.0002_plan_comptable_seed... OK` et `Applying finance.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/accounting/tests/test_models.py apps/accounting/tests/test_receivers.py apps/accounting/tests/test_services.py apps/finance/tests/test_demandes.py apps/finance/tests/test_frais_mission_receivers.py apps/finance/tests/test_services.py -q --no-cov
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
