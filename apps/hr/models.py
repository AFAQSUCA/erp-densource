from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
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
    type_contrat = models.CharField(_("type de contrat"), max_length=30, blank=True)
    solde_conges_jours = models.PositiveIntegerField(
        _("solde de congés (jours)"), default=0
    )
    est_chef_departement = models.BooleanField(
        _("chef de département"),
        default=False,
        help_text=_("Valide en N1 les congés des employés de son département."),
    )
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte utilisateur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personnel",
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


class StatutConge(models.TextChoices):
    """Statuts d'un congé — cahier-des-charges.md:217-218."""

    DEMANDE = "DEMANDE", _("Demande")
    VALIDATION_N1 = "VALIDATION_N1", _("Validé N1")
    APPROUVE = "APPROUVE", _("Approuvé")
    EN_COURS = "EN_COURS", _("En cours")
    TERMINE = "TERMINE", _("Terminé")
    REFUSE = "REFUSE", _("Refusé")


class Conge(BaseModel):
    """Demande de congé, workflow en 3 niveaux — cahier-des-charges.md:211-221.

    Les transitions passent exclusivement par ``hr/services.py``.
    """

    employe = models.ForeignKey(
        Personnel,
        verbose_name=_("employé"),
        on_delete=models.PROTECT,
        related_name="conges",
    )
    date_debut = models.DateField(_("début"))
    date_fin = models.DateField(_("fin"))
    jours = models.PositiveIntegerField(_("jours décomptés"))
    motif = models.TextField(_("motif"))
    statut = models.CharField(
        _("statut"),
        max_length=15,
        choices=StatutConge.choices,
        default=StatutConge.DEMANDE,
    )
    date_limite_n1 = models.DateTimeField(_("échéance validation N1"), null=True, blank=True)
    date_limite_n2 = models.DateTimeField(_("échéance validation N2"), null=True, blank=True)
    motif_decision = models.TextField(_("motif du refus / de l'annulation"), blank=True)

    class Meta:
        verbose_name = _("congé")
        verbose_name_plural = _("congés")
        ordering = ["-date_debut"]
        indexes = [models.Index(fields=["statut", "date_debut"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="conge_fin_apres_debut",
            ),
        ]

    def __str__(self):
        return f"{self.employe} : {self.date_debut} → {self.date_fin}"


class NiveauValidation(models.IntegerChoices):
    N1 = 1, _("N1 - chef de département")
    N2 = 2, _("N2 - RH")


class DecisionConge(models.TextChoices):
    APPROUVE = "APPROUVE", _("Approuvé")
    REFUSE = "REFUSE", _("Refusé")


class ValidationConge(BaseModel):
    """Décision d'un validateur (N1 ou N2) sur un congé — architecture.md:194-195."""

    conge = models.ForeignKey(
        Conge,
        verbose_name=_("congé"),
        on_delete=models.PROTECT,
        related_name="validations",
    )
    niveau = models.PositiveSmallIntegerField(_("niveau"), choices=NiveauValidation.choices)
    validateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validateur"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    decision = models.CharField(_("décision"), max_length=10, choices=DecisionConge.choices)
    commentaire = models.TextField(_("commentaire"), blank=True)
    date_decision = models.DateTimeField(_("date de décision"), default=timezone.now)

    class Meta:
        verbose_name = _("validation de congé")
        verbose_name_plural = _("validations de congé")
        ordering = ["date_decision"]

    def __str__(self):
        return f"N{self.niveau} {self.decision} - {self.conge}"
