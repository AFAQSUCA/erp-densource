from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class NiveauAlerte(models.TextChoices):
    """Alerte de surconsommation — cahier-des-charges.md:152-155."""

    AUCUNE = "AUCUNE", _("Aucune")
    JAUNE = "JAUNE", _("Jaune (> +20 %)")
    ROUGE = "ROUGE", _("Rouge (> +40 %)")


class Plein(BaseModel):
    """Plein de carburant d'un camion — cahier-des-charges.md:148-150.

    Les champs calculés (distance, consommation, écart, alertes) sont figés à
    la saisie : ils dépendent de l'historique tel qu'il était à ce moment-là.
    Ils ne se renseignent que par ``services.enregistrer_plein``.
    """

    date_plein = models.DateField(_("date"))
    vehicule = models.ForeignKey(
        "fleet.Vehicule",
        verbose_name=_("camion"),
        on_delete=models.PROTECT,
        related_name="pleins",
    )
    chauffeur = models.ForeignKey(
        "drivers.Chauffeur",
        verbose_name=_("chauffeur"),
        on_delete=models.PROTECT,
        related_name="pleins",
    )
    station = models.CharField(_("station"), max_length=100)
    quantite_litres = models.DecimalField(
        _("quantité (L)"), max_digits=8, decimal_places=2
    )
    prix_unitaire = models.DecimalField(
        _("prix unitaire (FCFA/L)"), max_digits=10, decimal_places=2
    )
    km_compteur = models.PositiveIntegerField(_("km compteur"))
    numero_ticket = models.CharField(_("n° ticket / reçu"), max_length=50)

    km_precedent = models.PositiveIntegerField(
        _("km du plein précédent"), null=True, blank=True
    )
    distance_km = models.PositiveIntegerField(
        _("distance depuis le plein précédent"), null=True, blank=True
    )
    consommation = models.DecimalField(
        _("consommation (L/100 km)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    moyenne_reference = models.DecimalField(
        _("moyenne des pleins précédents (L/100 km)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    ecart_pct = models.DecimalField(
        _("écart à la moyenne (%)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    niveau_alerte = models.CharField(
        _("alerte"),
        max_length=6,
        choices=NiveauAlerte.choices,
        default=NiveauAlerte.AUCUNE,
    )
    alerte_saisie = models.BooleanField(
        _("alerte de saisie (écart > ±60 %)"), default=False
    )
    anomalie = models.BooleanField(
        _("anomalie (> 45 ou < 20 L/100 km)"), default=False
    )

    class Meta:
        verbose_name = _("plein")
        verbose_name_plural = _("pleins")
        ordering = ["-date_plein", "-pk"]
        indexes = [models.Index(fields=["vehicule", "date_plein"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantite_litres__gt=0), name="plein_quantite_positive"
            ),
            models.CheckConstraint(
                condition=Q(prix_unitaire__gt=0), name="plein_prix_positif"
            ),
            models.UniqueConstraint(
                fields=["numero_ticket"],
                condition=Q(is_deleted=False),
                name="plein_ticket_unique",
            ),
        ]

    def __str__(self):
        return f"{self.date_plein} {self.vehicule.immatriculation} {self.quantite_litres} L"

    @property
    def montant_total(self):
        """Coût du plein en FCFA."""
        return self.quantite_litres * self.prix_unitaire
