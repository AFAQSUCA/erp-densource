from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.billing.models import ModePaiement
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
