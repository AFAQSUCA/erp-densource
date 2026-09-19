from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

POSTE_CHAUFFEUR = "Chauffeur"


class Departement(models.TextChoices):
    """5 départements — cahier-des-charges.md:207-208."""

    EXPLOITATION = "EXPLOITATION", _("Exploitation")
    PARC_AUTO = "PARC_AUTO", _("Parc Auto")
    COMPTABILITE = "COMPTABILITE", _("Comptabilité")
    COMMERCIAL = "COMMERCIAL", _("Commercial")
    DIRECTION = "DIRECTION", _("Direction")


class Personnel(BaseModel):
    """Fiche employé — cahier-des-charges.md:206-208.

    Le matricule est la source de vérité de l'identité d'un employé
    (cahier-des-charges.md:107) : il reste unique même après suppression
    logique, pour ne jamais être réattribué.
    """

    matricule = models.CharField(_("matricule"), max_length=20, unique=True)
    nom = models.CharField(_("nom"), max_length=100)
    prenom = models.CharField(_("prénom"), max_length=100)
    poste = models.CharField(_("poste"), max_length=100)
    departement = models.CharField(
        _("département"), max_length=20, choices=Departement.choices
    )
    date_embauche = models.DateField(_("date d'embauche"))
    salaire_base = models.DecimalField(
        _("salaire de base (FCFA)"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = _("personnel")
        verbose_name_plural = _("personnel")
        ordering = ["matricule"]
        indexes = [models.Index(fields=["nom", "prenom"])]

    def __str__(self):
        return f"{self.matricule} - {self.prenom} {self.nom}"

    @property
    def est_chauffeur(self) -> bool:
        """Vrai si le poste est « Chauffeur » (cahier-des-charges.md:108)."""
        return self.poste.strip().casefold() == POSTE_CHAUFFEUR.casefold()
