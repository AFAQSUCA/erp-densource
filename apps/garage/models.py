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


# --- signalements du chauffeur (espace mobile) ---

# Points de la check-list véhicule : liste fixe (le CDC ne détaille pas son contenu,
# cahier-des-charges.md:54). Un point est « OK » ou « KO » ; un KO exige une remarque.
POINTS_CHECKLIST = (
    ("PNEUS", "Pneus (état et pression)"),
    ("FREINS", "Freins"),
    ("FEUX", "Feux et clignotants"),
    ("HUILE", "Niveau d'huile moteur"),
    ("EAU", "Niveau d'eau et de refroidissement"),
    ("CARROSSERIE", "Carrosserie et rétroviseurs"),
    ("DOCUMENTS", "Documents du camion à bord"),
    ("SECURITE", "Extincteur et triangle de signalisation"),
)
CODES_CHECKLIST = tuple(code for code, _libelle in POINTS_CHECKLIST)


class ChecklistVehicule(BaseModel):
    """Check-list remplie par le chauffeur avant le départ d'une mission.

    Non bloquante : un point KO prévient le Parc Auto sans empêcher le départ.
    ``points`` : liste de ``{"code", "libelle", "ok", "remarque"}``, un élément par point.
    """

    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        on_delete=models.PROTECT,
        related_name="checklists",
    )
    points = models.JSONField(_("points contrôlés"), default=list)
    nb_anomalies = models.PositiveSmallIntegerField(_("points KO"), default=0)
    remarque = models.TextField(_("remarque générale"), blank=True)

    class Meta:
        verbose_name = _("check-list véhicule")
        verbose_name_plural = _("check-lists véhicule")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["mission"],
                condition=Q(is_deleted=False),
                name="checklist_une_par_mission",
            ),
        ]

    def __str__(self):
        return f"Check-list {self.mission.numero}"


class TypeIncident(models.TextChoices):
    PANNE = "PANNE", _("Panne")
    ACCIDENT = "ACCIDENT", _("Accident")
    AUTRE = "AUTRE", _("Autre")


class GraviteIncident(models.TextChoices):
    FAIBLE = "FAIBLE", _("Faible : le camion peut rouler")
    MOYENNE = "MOYENNE", _("Moyenne : intervention nécessaire")
    GRAVE = "GRAVE", _("Grave : camion immobilisé")


class StatutIncident(models.TextChoices):
    SIGNALE = "SIGNALE", _("Signalé")
    PRIS_EN_COMPTE = "PRIS_EN_COMPTE", _("Pris en compte")
    CLOS = "CLOS", _("Clos")


class Incident(BaseModel):
    """Panne ou incident signalé par le chauffeur ; le Parc Auto décide de la suite.

    Aucune action automatique sur le camion : c'est le Parc Auto qui ouvre un OR
    s'il le juge utile (décision de l'utilisateur).
    """

    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("véhicule"),
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    mission = models.ForeignKey(
        "missions.Mission",
        verbose_name=_("mission"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    type_incident = models.CharField(_("type"), max_length=10, choices=TypeIncident.choices)
    gravite = models.CharField(_("gravité"), max_length=10, choices=GraviteIncident.choices)
    description = models.TextField(_("description"))
    lieu = models.CharField(_("lieu"), max_length=200, blank=True)
    statut = models.CharField(
        _("statut"), max_length=15, choices=StatutIncident.choices, default=StatutIncident.SIGNALE
    )
    note_traitement = models.TextField(_("suite donnée"), blank=True)
    traite_par = models.ForeignKey(
        "accounts.User",
        verbose_name=_("traité par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_traitement = models.DateTimeField(_("traité le"), null=True, blank=True)

    class Meta:
        verbose_name = _("incident")
        verbose_name_plural = _("incidents")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["statut", "gravite"])]

    def __str__(self):
        return f"{self.get_type_incident_display()} {self.vehicule.immatriculation}"
