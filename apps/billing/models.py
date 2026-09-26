from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.customers.models import MotifExoneration


class ModePaiement(models.TextChoices):
    """6 modes de règlement — cahier-des-charges.md:189-190."""

    VIREMENT = "VIREMENT", _("Virement")
    CHEQUE = "CHEQUE", _("Chèque")
    ESPECES = "ESPECES", _("Espèces")
    WAVE = "WAVE", _("Wave")
    ORANGE_MONEY = "ORANGE_MONEY", _("Orange Money")
    MTN_MONEY = "MTN_MONEY", _("MTN Mobile Money")


class CompteTresorerie(models.TextChoices):
    """Où se trouve l'argent : le mode de paiement détermine le compte."""

    BANQUE = "BANQUE", _("Banque")
    CAISSE = "CAISSE", _("Caisse")
    MOBILE_MONEY = "MOBILE_MONEY", _("Mobile Money")


COMPTE_DU_MODE = {
    ModePaiement.VIREMENT: CompteTresorerie.BANQUE,
    ModePaiement.CHEQUE: CompteTresorerie.BANQUE,
    ModePaiement.ESPECES: CompteTresorerie.CAISSE,
    ModePaiement.WAVE: CompteTresorerie.MOBILE_MONEY,
    ModePaiement.ORANGE_MONEY: CompteTresorerie.MOBILE_MONEY,
    ModePaiement.MTN_MONEY: CompteTresorerie.MOBILE_MONEY,
}


class StatutFacture(models.TextChoices):
    """Cycle de vie : le brouillon est préparé par FINANCES, validé par la DIRECTION
    (architecture.md:432), puis suivi jusqu'au paiement complet."""

    BROUILLON = "BROUILLON", _("Brouillon")
    A_VALIDER = "A_VALIDER", _("À valider")
    EMISE = "EMISE", _("Émise")
    PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE", _("Partiellement payée")
    PAYEE = "PAYEE", _("Payée")


STATUTS_EMIS = (
    StatutFacture.EMISE,
    StatutFacture.PARTIELLEMENT_PAYEE,
    StatutFacture.PAYEE,
)
STATUTS_A_RECOUVRER = (StatutFacture.EMISE, StatutFacture.PARTIELLEMENT_PAYEE)


class Facture(BaseModel):
    """Facture d'une mission — cahier-des-charges.md:181-186.

    Le numéro ``FACT-AAAA-XXXX`` n'est attribué qu'à la validation : les brouillons
    abandonnés ne laissent aucun trou dans la numérotation. Une facture validée ne se
    modifie plus. Les montants sont en francs entiers (le FCFA n'a pas de centimes).
    """

    numero = models.CharField(_("numéro"), max_length=20, blank=True)
    client = models.ForeignKey(
        "customers.Client",
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="factures",
    )
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        on_delete=models.PROTECT,
        related_name="factures",
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutFacture.choices,
        default=StatutFacture.BROUILLON,
    )
    taux_tva = models.DecimalField(_("taux de TVA (%)"), max_digits=5, decimal_places=2)
    motif_exoneration = models.CharField(
        _("motif d'exonération"), max_length=12, choices=MotifExoneration.choices, blank=True
    )
    delai_paiement_jours = models.PositiveSmallIntegerField(_("délai de paiement (jours)"))
    date_emission = models.DateField(_("date d'émission"), null=True, blank=True)
    date_echeance = models.DateField(_("date d'échéance"), null=True, blank=True)
    montant_ht = models.DecimalField(_("total HT (FCFA)"), max_digits=14, decimal_places=2, default=0)
    montant_tva = models.DecimalField(_("TVA (FCFA)"), max_digits=14, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(_("total TTC (FCFA)"), max_digits=14, decimal_places=2, default=0)
    motif_refus = models.TextField(_("motif du dernier refus"), blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("préparée par"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validée par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_validation = models.DateTimeField(_("validée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("facture")
        verbose_name_plural = _("factures")
        ordering = ["-date_emission", "-created_at", "-pk"]
        indexes = [models.Index(fields=["statut", "date_echeance"])]
        constraints = [
            models.UniqueConstraint(
                fields=["numero"], condition=~Q(numero=""), name="facture_numero_unique"
            ),
            models.UniqueConstraint(
                fields=["mission"],
                condition=Q(is_deleted=False),
                name="facture_une_par_mission",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gt=0) | ~Q(motif_exoneration=""),
                name="facture_tva_zero_requiert_motif",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gte=0) & Q(taux_tva__lte=100),
                name="facture_taux_tva_entre_0_et_100",
            ),
            models.CheckConstraint(
                condition=Q(montant_ttc=F("montant_ht") + F("montant_tva")),
                name="facture_ttc_egal_ht_plus_tva",
            ),
            models.CheckConstraint(
                condition=Q(statut__in=["BROUILLON", "A_VALIDER"])
                | (~Q(numero="") & Q(date_emission__isnull=False) & Q(date_echeance__isnull=False)),
                name="facture_emise_a_numero_et_dates",
            ),
        ]

    def __str__(self):
        return self.numero or f"Brouillon ({self.client})"

    @property
    def est_emise(self) -> bool:
        return self.statut in STATUTS_EMIS

    @property
    def est_modifiable(self) -> bool:
        return self.statut == StatutFacture.BROUILLON


class LigneFacture(BaseModel):
    """Ligne d'une facture : la prestation de la mission, plus d'éventuelles refacturations."""

    facture = models.ForeignKey(
        Facture, verbose_name=_("facture"), on_delete=models.PROTECT, related_name="lignes"
    )
    designation = models.CharField(_("désignation"), max_length=255)
    quantite = models.DecimalField(_("quantité"), max_digits=10, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(_("prix unitaire HT (FCFA)"), max_digits=12, decimal_places=2)
    montant_ht = models.DecimalField(_("montant HT (FCFA)"), max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = _("ligne de facture")
        verbose_name_plural = _("lignes de facture")
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(quantite__gt=0), name="ligne_facture_quantite_positive"),
            models.CheckConstraint(
                condition=Q(prix_unitaire_ht__gte=0), name="ligne_facture_prix_positif"
            ),
        ]

    def __str__(self):
        return f"{self.designation} ({self.montant_ht})"


class Reglement(BaseModel):
    """Encaissement d'une facture (acompte ou solde) — cahier-des-charges.md:189-191."""

    facture = models.ForeignKey(
        Facture, verbose_name=_("facture"), on_delete=models.PROTECT, related_name="reglements"
    )
    date_reglement = models.DateField(_("date du règlement"))
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode de paiement"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(
        _("référence"), max_length=100, blank=True, help_text=_("N° de chèque, de virement ou de transaction.")
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    motif_annulation = models.TextField(_("motif d'annulation"), blank=True)

    class Meta:
        verbose_name = _("règlement")
        verbose_name_plural = _("règlements")
        ordering = ["-date_reglement", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="reglement_montant_positif"),
        ]

    def __str__(self):
        return f"{self.facture} : {self.montant} ({self.get_mode_display()})"


class CategorieDepense(models.TextChoices):
    """Catégories du CDC (cahier-des-charges.md:192) ; « Autre » pour le reste."""

    PEAGES = "PEAGES", _("Péages")
    ENTRETIEN = "ENTRETIEN", _("Entretien")
    FRAIS_ADMIN = "FRAIS_ADMIN", _("Frais administratifs")
    AUTRE = "AUTRE", _("Autre")
    # Catégories du parc auto : créées automatiquement (voir OrigineDepense), pas proposées à la saisie manuelle.
    CARBURANT = "CARBURANT", _("Carburant")
    PIECES = "PIECES", _("Pièces détachées")
    MAINTENANCE = "MAINTENANCE", _("Main-d'œuvre des réparations")


CATEGORIES_AUTOMATIQUES = (CategorieDepense.CARBURANT, CategorieDepense.PIECES, CategorieDepense.MAINTENANCE)


class OrigineDepense(models.TextChoices):
    """D'où vient une dépense créée automatiquement (vide : saisie à la main)."""

    PLEIN = "PLEIN", _("Plein de carburant")
    ACHAT_STOCK = "ACHAT_STOCK", _("Achat de pièces")
    MAIN_OEUVRE_OR = "MAIN_OEUVRE_OR", _("Main-d'œuvre d'un OR")
    ORDRE_DECAISSEMENT = "ORDRE_DECAISSEMENT", _("Ordre de décaissement exécuté")


class Depense(BaseModel):
    """Dépense de l'entreprise, par catégorie, éventuellement rattachée à une mission."""

    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieDepense.choices)
    date_depense = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=200)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode de paiement"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(_("n° de pièce"), max_length=100, blank=True)
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="depenses",
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    origine = models.CharField(
        _("origine"), max_length=20, choices=OrigineDepense.choices, blank=True,
        help_text=_("Renseignée pour une dépense créée automatiquement (plein, achat de pièces, OR)."),
    )
    origine_id = models.PositiveBigIntegerField(
        _("identifiant de l'origine"), null=True, blank=True,
        help_text=_("Numéro du plein, du mouvement de stock ou de l'OR à l'origine de la dépense."),
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="depenses",
        help_text=_("Renseigné pour un plein, une main-d'œuvre d'OR ou un ordre de décaissement lié à un camion."),
    )

    class Meta:
        verbose_name = _("dépense")
        verbose_name_plural = _("dépenses")
        ordering = ["-date_depense", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="depense_montant_positif"),
            # Une source (un plein, un achat, un OR) ne donne jamais deux dépenses.
            models.UniqueConstraint(
                fields=["origine", "origine_id"], condition=~Q(origine=""), name="depense_une_par_origine"
            ),
        ]

    @property
    def est_automatique(self) -> bool:
        return bool(self.origine)

    def __str__(self):
        return f"{self.libelle} ({self.montant})"
