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

    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieDepense.choices)
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
    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieDepense.choices)
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
