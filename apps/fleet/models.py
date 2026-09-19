from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutVehicule(models.TextChoices):
    """5 statuts — cahier-des-charges.md:91-92."""

    DISPONIBLE = "DISPONIBLE", _("Disponible")
    EN_MISSION = "EN_MISSION", _("En mission")
    EN_MAINTENANCE = "EN_MAINTENANCE", _("En maintenance")
    IMMOBILISE = "IMMOBILISE", _("Immobilisé")
    HORS_SERVICE = "HORS_SERVICE", _("Hors service")


class Vehicule(BaseModel):
    """Fiche camion — cahier-des-charges.md:88-90."""

    immatriculation = models.CharField(_("immatriculation"), max_length=20, unique=True)
    marque = models.CharField(_("marque"), max_length=50)
    modele = models.CharField(_("modèle"), max_length=50)
    annee = models.PositiveSmallIntegerField(
        _("année"), validators=[MinValueValidator(1950)]
    )
    vin = models.CharField(_("n° de châssis (VIN)"), max_length=17, unique=True)
    kilometrage = models.PositiveIntegerField(_("kilométrage compteur"), default=0)
    capacite_charge_t = models.DecimalField(
        _("capacité de charge (t)"), max_digits=6, decimal_places=2
    )
    reservoir_l = models.PositiveIntegerField(_("réservoir (L)"))
    chauffeur_habituel = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur habituel"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vehicules_habituels",
    )
    statut = models.CharField(
        _("statut"),
        max_length=15,
        choices=StatutVehicule.choices,
        default=StatutVehicule.DISPONIBLE,
    )

    class Meta:
        verbose_name = _("véhicule")
        verbose_name_plural = _("véhicules")
        ordering = ["immatriculation"]
        indexes = [models.Index(fields=["statut"])]

    def __str__(self):
        return f"{self.immatriculation} ({self.marque} {self.modele})"


class TypeDocument(models.TextChoices):
    """4 documents réglementaires — cahier-des-charges.md:93-94."""

    CARTE_GRISE = "CARTE_GRISE", _("Carte grise")
    ASSURANCE = "ASSURANCE", _("Assurance")
    VISITE_TECHNIQUE = "VISITE_TECHNIQUE", _("Visite technique")
    PATENTE = "PATENTE", _("Patente")


class DocumentReglementaire(BaseModel):
    """Document d'un véhicule (dates de délivrance et d'expiration).

    Un seul document actif par type et par véhicule : un renouvellement met
    à jour les dates ; l'historique des anciennes dates reste dans
    ``audit_log`` (ancienne_valeur / nouvelle_valeur).
    """

    vehicule = models.ForeignKey(
        Vehicule,
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="documents",
    )
    type_document = models.CharField(
        _("type"), max_length=20, choices=TypeDocument.choices
    )
    date_delivrance = models.DateField(_("date de délivrance"))
    date_expiration = models.DateField(_("date d'expiration"))

    class Meta:
        verbose_name = _("document réglementaire")
        verbose_name_plural = _("documents réglementaires")
        ordering = ["date_expiration"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicule", "type_document"],
                condition=Q(is_deleted=False),
                name="document_unique_par_type_et_vehicule",
            ),
            models.CheckConstraint(
                condition=Q(date_expiration__gte=F("date_delivrance")),
                name="document_expiration_apres_delivrance",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_document_display()} - {self.vehicule.immatriculation}"

    def jours_restants(self, aujourd_hui=None) -> int:
        """Jours avant expiration (négatif si déjà expiré)."""
        return (self.date_expiration - (aujourd_hui or timezone.localdate())).days
