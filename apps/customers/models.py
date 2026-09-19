from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

TVA_DEFAUT = Decimal("18.00")


class MotifExoneration(models.TextChoices):
    """Motifs d'exonération de TVA — cahier-des-charges.md:187-188."""

    EXPORT = "EXPORT", _("Export")
    ONG = "ONG", _("ONG")
    CONVENTION = "CONVENTION", _("Convention")
    AUTRE = "AUTRE", _("Autre")


class Client(BaseModel):
    """Fiche client — cahier-des-charges.md:119-122."""

    raison_sociale = models.CharField(_("raison sociale"), max_length=200)
    ncc_nif = models.CharField(_("NCC / NIF"), max_length=50, unique=True)
    contact_principal = models.CharField(_("contact principal"), max_length=150)
    telephone = models.CharField(_("téléphone"), max_length=20)
    email = models.EmailField(_("email"), blank=True)
    adresse = models.TextField(_("adresse / siège"))
    charge_clientele = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("chargé clientèle attitré"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
        limit_choices_to={"role": "CHARGE_CLIENTELE"},
    )
    taux_tva = models.DecimalField(
        _("taux de TVA (%)"), max_digits=5, decimal_places=2, default=TVA_DEFAUT
    )
    motif_exoneration = models.CharField(
        _("motif d'exonération"),
        max_length=12,
        choices=MotifExoneration.choices,
        blank=True,
    )

    class Meta:
        verbose_name = _("client")
        verbose_name_plural = _("clients")
        ordering = ["raison_sociale"]
        indexes = [models.Index(fields=["raison_sociale"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(taux_tva__gt=0) | ~Q(motif_exoneration=""),
                name="client_tva_zero_requiert_motif",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gte=0) & Q(taux_tva__lte=100),
                name="client_taux_tva_entre_0_et_100",
            ),
        ]

    def __str__(self):
        return self.raison_sociale

    def clean(self):
        if self.taux_tva == 0 and not self.motif_exoneration:
            raise ValidationError(
                {"motif_exoneration": _("Motif obligatoire quand la TVA est à 0 %.")}
            )


class TypeInteraction(models.TextChoices):
    """Interactions commerciales — cahier-des-charges.md:123-124."""

    APPEL = "APPEL", _("Appel")
    MAIL = "MAIL", _("Mail")
    REUNION = "REUNION", _("Réunion")
    DEMANDE_DEVIS = "DEMANDE_DEVIS", _("Demande de devis")
    RECLAMATION = "RECLAMATION", _("Réclamation")


class Interaction(BaseModel):
    """Historique commercial d'un client."""

    client = models.ForeignKey(
        Client,
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="interactions",
    )
    type_interaction = models.CharField(
        _("type"), max_length=15, choices=TypeInteraction.choices
    )
    date_interaction = models.DateTimeField(_("date"), default=timezone.now)
    resume = models.TextField(_("résumé / notes d'échange"))
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("auteur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("interaction")
        verbose_name_plural = _("interactions")
        ordering = ["-date_interaction"]

    def __str__(self):
        return f"{self.get_type_interaction_display()} - {self.client}"
