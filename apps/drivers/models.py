from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutChauffeur(models.TextChoices):
    """5 statuts — cahier-des-charges.md:112-113."""

    DISPONIBLE = "DISPONIBLE", _("Disponible")
    EN_MISSION = "EN_MISSION", _("En mission")
    EN_CONGE = "EN_CONGE", _("En congé")
    SUSPENDU = "SUSPENDU", _("Suspendu")
    INACTIF = "INACTIF", _("Inactif")


class CategoriePermis(models.TextChoices):
    """Catégories de permis poids lourd — cahier-des-charges.md:110."""

    C = "C", "C"
    E = "E", "E"


class Chauffeur(BaseModel):
    """Extension 1-1 d'une fiche Personnel — cahier-des-charges.md:105-113.

    Matricule, nom et prénom viennent de ``Personnel`` (source de vérité,
    cahier-des-charges.md:107) et ne sont jamais dupliqués ici.
    """

    personnel = models.OneToOneField(
        "hr.Personnel",
        verbose_name=_("personnel"),
        on_delete=models.PROTECT,
        related_name="chauffeur",
    )
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)
    contact_urgence = models.CharField(_("contact d'urgence"), max_length=150, blank=True)
    numero_permis = models.CharField(_("n° de permis"), max_length=50, blank=True)
    categories_permis = models.JSONField(
        _("catégories de permis"), default=list, blank=True
    )
    date_expiration_permis = models.DateField(
        _("expiration du permis"), null=True, blank=True
    )
    date_expiration_visite_medicale = models.DateField(
        _("expiration de la visite médicale"), null=True, blank=True
    )
    statut = models.CharField(
        _("statut"),
        max_length=12,
        choices=StatutChauffeur.choices,
        default=StatutChauffeur.DISPONIBLE,
    )

    class Meta:
        verbose_name = _("chauffeur")
        verbose_name_plural = _("chauffeurs")
        ordering = ["personnel__matricule"]

    def __str__(self):
        return str(self.personnel)

    @property
    def matricule(self) -> str:
        return self.personnel.matricule

    @property
    def nom(self) -> str:
        return self.personnel.nom

    @property
    def prenom(self) -> str:
        return self.personnel.prenom

    def clean(self):
        valides = set(CategoriePermis.values)
        if not isinstance(self.categories_permis, list) or not set(
            self.categories_permis
        ) <= valides:
            raise ValidationError(
                {"categories_permis": _("Catégories autorisées : C, E.")}
            )
