from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Article(BaseModel):
    """Pièce détachée du magasin — cahier-des-charges.md:177-179.

    ``quantite`` et ``pump`` ne se modifient que par les mouvements de
    ``services.py`` : ne jamais les éditer à la main.
    """

    reference = models.CharField(_("référence"), max_length=50, unique=True)
    designation = models.CharField(_("désignation"), max_length=200)
    categorie = models.CharField(_("catégorie"), max_length=100, blank=True)
    emplacement = models.CharField(_("emplacement"), max_length=100, blank=True)
    quantite = models.PositiveIntegerField(_("quantité en stock"), default=0)
    seuil_minimal = models.PositiveIntegerField(
        _("seuil minimal"),
        default=0,
        help_text=_("0 = pas d'alerte de seuil pour cet article."),
    )
    pump = models.DecimalField(
        _("PUMP (FCFA)"),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_("Prix unitaire moyen pondéré."),
    )

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        ordering = ["reference"]
        indexes = [models.Index(fields=["designation"])]

    def __str__(self):
        return f"{self.reference} - {self.designation}"

    @property
    def sous_seuil(self) -> bool:
        """Stock au niveau du seuil minimal ou en dessous (seuil 0 = désactivé)."""
        return self.seuil_minimal > 0 and self.quantite <= self.seuil_minimal

    @property
    def valeur_stock(self) -> Decimal:
        """Valorisation du stock au PUMP."""
        return self.quantite * self.pump


class TypeMouvement(models.TextChoices):
    """3 types de mouvements — cahier-des-charges.md:180-181."""

    ENTREE = "ENTREE", _("Entrée (achat)")
    SORTIE = "SORTIE", _("Sortie (liée à un OR)")
    AJUSTEMENT = "AJUSTEMENT", _("Ajustement")


class MouvementStock(models.Model):
    """Ligne du journal des mouvements de stock — append-only.

    Comme ``AuditLog``, un mouvement ne se modifie ni ne se supprime : une
    erreur se corrige par un mouvement d'ajustement. Ce n'est donc pas un
    ``BaseModel`` (pas de soft delete) : la valeur de ``Article.quantite``
    doit toujours être la somme des variations.
    """

    article = models.ForeignKey(
        Article,
        verbose_name=_("article"),
        on_delete=models.PROTECT,
        related_name="mouvements",
    )
    type_mouvement = models.CharField(
        _("type"), max_length=12, choices=TypeMouvement.choices
    )
    variation = models.IntegerField(
        _("variation"), help_text=_("Positive en entrée, négative en sortie.")
    )
    quantite_apres = models.PositiveIntegerField(_("stock après mouvement"))
    prix_unitaire = models.DecimalField(
        _("prix unitaire (FCFA)"),
        max_digits=12,
        decimal_places=2,
        help_text=_("Prix d'achat en entrée ; PUMP au moment du mouvement sinon."),
    )
    ordre_reparation = models.ForeignKey(
        "garage.OrdreReparation",
        verbose_name=_("ordre de réparation"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mouvements_stock",
    )
    motif = models.TextField(_("motif"), blank=True)
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    date_mouvement = models.DateTimeField(_("date"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("mouvement de stock")
        verbose_name_plural = _("mouvements de stock")
        ordering = ["-date_mouvement", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.ENTREE) | Q(variation__gt=0),
                name="mouvement_entree_variation_positive",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.SORTIE) | Q(variation__lt=0),
                name="mouvement_sortie_variation_negative",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.AJUSTEMENT)
                | ~Q(variation=0),
                name="mouvement_ajustement_non_nul",
            ),
            # architecture.md:230 : or_id NULL si Entrée, NOT NULL si Sortie.
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.SORTIE)
                | Q(ordre_reparation__isnull=False),
                name="mouvement_sortie_requiert_or",
            ),
            models.CheckConstraint(
                condition=~Q(type_mouvement=TypeMouvement.ENTREE)
                | Q(ordre_reparation__isnull=True),
                name="mouvement_entree_sans_or",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_mouvement_display()} {self.variation:+d} {self.article.reference}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "MouvementStock est append-only : corriger par un ajustement."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("MouvementStock est append-only : suppression interdite.")
