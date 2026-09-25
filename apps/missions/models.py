from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutMission(models.TextChoices):
    """Cycle de vie — cahier-des-charges.md:132-134, architecture.md:239-256.

    « En cours » se décompose en deux étapes : départ, puis colis récupéré.
    """

    BROUILLON = "BROUILLON", _("Brouillon")
    PLANIFIEE = "PLANIFIEE", _("Planifiée")
    AFFECTEE = "AFFECTEE", _("Affectée")
    EN_COURS_DEPART = "EN_COURS_DEPART", _("En cours : départ")
    EN_COURS_COLIS_RECUPERE = "EN_COURS_COLIS_RECUPERE", _("En cours : colis récupéré")
    LIVREE = "LIVREE", _("Livrée")
    CLOTUREE = "CLOTUREE", _("Clôturée et validée")


# Camion et chauffeur réservés : la mission a été affectée mais n'est pas terminée.
STATUTS_ACTIFS = (
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
    StatutMission.EN_COURS_COLIS_RECUPERE,
)

# Modification autorisée tant que le colis n'est pas encore récupéré : au-delà, le client a déjà le
# camion à quai / la marchandise est en route sur la base de ces informations (règle de séparation des
# tâches, avenant-separation-des-taches.md § R3).
STATUTS_MODIFIABLES = (
    StatutMission.BROUILLON,
    StatutMission.PLANIFIEE,
    StatutMission.AFFECTEE,
    StatutMission.EN_COURS_DEPART,
)


class Mission(BaseModel):
    """Mission de transport — cahier-des-charges.md:127-143."""

    numero = models.CharField(_("numéro"), max_length=20, unique=True)
    client = models.ForeignKey(
        "customers.Client",
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="missions",
    )
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="missions",
    )
    lieu_chargement = models.CharField(_("lieu de chargement"), max_length=200)
    lieu_livraison = models.CharField(_("lieu de livraison"), max_length=200)
    nature_marchandise = models.CharField(_("nature de la marchandise"), max_length=200)
    poids_t = models.DecimalField(_("poids (t)"), max_digits=8, decimal_places=2)
    prix_convenu = models.DecimalField(
        _("prix convenu (FCFA)"), max_digits=12, decimal_places=2
    )
    date_depart_prevue = models.DateField(
        _("départ prévu"),
        null=True,
        blank=True,
        help_text=_(
            "Nécessaire à l'alerte N1 « chauffeur avec mission sur la période » "
            "des congés (cahier-des-charges.md:219-221)."
        ),
    )
    statut = models.CharField(
        _("statut"),
        max_length=25,
        choices=StatutMission.choices,
        default=StatutMission.BROUILLON,
    )

    # Codes remis à l'expéditeur (récupération du colis) et au destinataire
    # (confirmation de livraison) — cahier-des-charges.md:135-137. Exclus de
    # l'audit (voir apps.py). Le QR ne fait qu'encoder ces codes.
    code_expediteur = models.CharField(_("code expéditeur"), max_length=12)
    code_destinataire = models.CharField(_("code destinataire"), max_length=12)

    km_depart = models.PositiveIntegerField(_("km au départ"), null=True, blank=True)
    km_arrivee = models.PositiveIntegerField(_("km à l'arrivée"), null=True, blank=True)
    date_depart = models.DateTimeField(_("départ effectif"), null=True, blank=True)
    date_recuperation = models.DateTimeField(_("colis récupéré le"), null=True, blank=True)
    date_livraison = models.DateTimeField(_("livrée le"), null=True, blank=True)
    date_cloture = models.DateTimeField(_("clôturée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("mission")
        verbose_name_plural = _("missions")
        ordering = ["-numero"]
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["vehicule", "statut"]),
            models.Index(fields=["chauffeur", "statut"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    statut__in=[StatutMission.BROUILLON, StatutMission.PLANIFIEE]
                )
                | (Q(vehicule__isnull=False) & Q(chauffeur__isnull=False)),
                name="mission_affectee_requiert_camion_et_chauffeur",
            ),
            models.CheckConstraint(
                condition=Q(poids_t__gt=0), name="mission_poids_positif"
            ),
            models.CheckConstraint(
                condition=Q(prix_convenu__gte=0), name="mission_prix_positif_ou_nul"
            ),
            models.CheckConstraint(
                condition=Q(km_arrivee__isnull=True)
                | Q(km_depart__isnull=True)
                | Q(km_arrivee__gte=F("km_depart")),
                name="mission_km_arrivee_apres_depart",
            ),
        ]

    def __str__(self):
        return f"{self.numero} ({self.client})"

    @property
    def est_en_cours(self) -> bool:
        return self.statut in (
            StatutMission.EN_COURS_DEPART,
            StatutMission.EN_COURS_COLIS_RECUPERE,
        )
