from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class CategorieNotification(models.TextChoices):
    CONGE = "CONGE", _("Congé")
    STOCK = "STOCK", _("Stock")
    CARBURANT = "CARBURANT", _("Carburant")
    DOCUMENT = "DOCUMENT", _("Échéance")
    MISSION = "MISSION", _("Mission")
    FACTURE = "FACTURE", _("Facturation")
    PROFORMA = "PROFORMA", _("Devis")
    INCIDENT = "INCIDENT", _("Incident")


class NiveauNotification(models.TextChoices):
    INFO = "INFO", _("Information")
    ATTENTION = "ATTENTION", _("Attention")
    URGENT = "URGENT", _("Urgent")


class Notification(BaseModel):
    """Message adressé à un utilisateur (cloche de l'en-tête, page « Notifications »).

    Créée par ``services.notifier`` ; ``cle_unicite`` évite d'envoyer deux fois la même
    alerte au même destinataire (rappels quotidiens).
    """

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("destinataire"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    categorie = models.CharField(_("catégorie"), max_length=12, choices=CategorieNotification.choices)
    niveau = models.CharField(
        _("niveau"),
        max_length=10,
        choices=NiveauNotification.choices,
        default=NiveauNotification.INFO,
    )
    titre = models.CharField(_("titre"), max_length=200)
    message = models.TextField(_("message"), blank=True)
    url = models.CharField(_("lien"), max_length=300, blank=True)
    action = models.CharField(
        _("bouton d'action"),
        max_length=60,
        blank=True,
        help_text=_("Intitulé du bouton qui mène au lien (ex. « Confirmer le versement ») ; « Ouvrir » si vide."),
    )
    lue_le = models.DateTimeField(_("lue le"), null=True, blank=True)
    cle_unicite = models.CharField(_("clé d'unicité"), max_length=150, blank=True)
    email_envoye = models.BooleanField(_("e-mail envoyé"), default=False)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["destinataire", "lue_le"])]
        constraints = [
            models.UniqueConstraint(
                fields=["destinataire", "cle_unicite"],
                condition=~Q(cle_unicite=""),
                name="notification_cle_unique_par_destinataire",
            ),
        ]

    def __str__(self):
        return f"{self.destinataire} : {self.titre}"

    @property
    def est_lue(self) -> bool:
        return self.lue_le is not None
