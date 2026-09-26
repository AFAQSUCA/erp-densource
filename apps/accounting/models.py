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
        raise EcritureVerrouillee("Une écriture comptable ne se supprime jamais : contre-passez-la.")


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
        raise ValueError("LigneEcriture est append-only : contre-passez plutôt que supprimer.")
