from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TypeOr(models.TextChoices):
    """4 types d'ordre de réparation — cahier-des-charges.md:163-164."""

    CURATIF = "CURATIF", _("Curatif")
    PREVENTIF = "PREVENTIF", _("Préventif")
    DIAGNOSTIC = "DIAGNOSTIC", _("Diagnostic")
    PNEUMATIQUES = "PNEUMATIQUES", _("Pneumatiques")


class LieuReparation(models.TextChoices):
    """Lieu de la réparation — cahier-des-charges.md:164-165."""

    INTERNE = "INTERNE", _("Garage interne DEN Source")
    EXTERNE = "EXTERNE", _("Prestataire externe")


class StatutOr(models.TextChoices):
    OUVERT = "OUVERT", _("Ouvert")
    CLOTURE = "CLOTURE", _("Clôturé")


class OrdreReparation(BaseModel):
    """Ordre de réparation (OR) — cahier-des-charges.md:161-168.

    Ouvrir un OR passe le camion « En maintenance » ; le clôturer déclenche le
    recalcul automatique du statut (``services.cloturer_or``).
    """

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="ordres_reparation",
    )
    type_or = models.CharField(_("type"), max_length=15, choices=TypeOr.choices)
    lieu = models.CharField(_("lieu"), max_length=10, choices=LieuReparation.choices)
    motif = models.TextField(_("motif / symptômes"))
    statut = models.CharField(
        _("statut"), max_length=10, choices=StatutOr.choices, default=StatutOr.OUVERT
    )
    date_ouverture = models.DateTimeField(_("ouvert le"), default=timezone.now)
    date_cloture = models.DateTimeField(_("clôturé le"), null=True, blank=True)
    cout_main_oeuvre = models.DecimalField(
        _("coût de la main-d'œuvre (FCFA)"),
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    class Meta:
        verbose_name = _("ordre de réparation")
        verbose_name_plural = _("ordres de réparation")
        ordering = ["-numero"]
        indexes = [models.Index(fields=["vehicule", "statut"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(statut=StatutOr.OUVERT) | Q(date_cloture__isnull=False),
                name="or_cloture_requiert_date",
            ),
            models.CheckConstraint(
                condition=Q(cout_main_oeuvre__gte=0),
                name="or_cout_main_oeuvre_positif_ou_nul",
            ),
        ]

    def __str__(self):
        return f"{self.numero} ({self.vehicule.immatriculation})"
