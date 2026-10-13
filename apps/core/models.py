import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ActiveManager(models.Manager):
    """Manager par défaut : exclut les enregistrements soft-supprimés.

    ADR-006 (architecture.md:509-514) : tous les querysets doivent filtrer
    ``is_deleted=False``. ``BaseModel.all_objects`` reste disponible pour
    les vues ADMIN ayant besoin de voir les enregistrements supprimés.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    """Socle commun à tous les modèles métier.

    Timestamps + soft delete + hooks d'audit — conventions.md:25-26.
    Toute app métier doit hériter de ce modèle plutôt que de
    ``models.Model`` directement.
    """

    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    is_deleted = models.BooleanField(_("supprimé"), default=False)
    deleted_at = models.DateTimeField(_("supprimé le"), null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("supprimé par"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, deleted_by=None):
        """Suppression logique uniquement — conventions.md §3, §9.

        Aucun ``DELETE`` physique sur les données sensibles : ce modèle
        n'expose la suppression réelle que via :meth:`hard_delete`.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(
            using=using,
            update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"],
        )

    def hard_delete(self, using=None, keep_parents=False):
        """Suppression physique réelle — réservée aux migrations/purges RGPD."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])


class CompteurNumero(models.Model):
    """Dernier numéro attribué par préfixe et par année (MIS-2026-0007...).

    Table technique (pas de soft delete) : un compteur ne se supprime jamais,
    sous peine de réattribuer un numéro déjà émis.
    """

    prefixe = models.CharField(_("préfixe"), max_length=10)
    annee = models.PositiveSmallIntegerField(_("année"))
    dernier = models.PositiveIntegerField(_("dernier numéro attribué"), default=0)

    class Meta:
        verbose_name = _("compteur de numéros")
        verbose_name_plural = _("compteurs de numéros")
        constraints = [
            models.UniqueConstraint(
                fields=["prefixe", "annee"], name="compteur_numero_unique"
            ),
        ]

    def __str__(self):
        return f"{self.prefixe}-{self.annee} : {self.dernier}"


class StatutDocumentPdf(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", _("En préparation")
    PRET = "PRET", _("Prêt")
    ECHEC = "ECHEC", _("Échec")


def _chemin_document_pdf(document, nom):
    # Nom imprévisible (la clé) : le fichier n'est de toute façon servi qu'au demandeur (core.documents_pdf).
    return f"pdf-generes/{document.cle}.pdf"


class DocumentPdf(models.Model):
    """PDF préparé en tâche de fond par Celery (cahier-des-charges.md:294 ; audit TECH-70).

    Table technique, sans suppression logique : un fichier temporaire, réservé au demandeur et effacé après
    ``PDF_CONSERVATION_HEURES`` par les tâches quotidiennes. ``parametres`` porte les données du rapport le temps
    de la génération, puis est vidé.
    """

    cle = models.UUIDField(_("clé"), default=uuid.uuid4, unique=True, editable=False)
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("demandé par"), on_delete=models.CASCADE, related_name="+"
    )
    titre = models.CharField(_("titre"), max_length=200)
    nom_fichier = models.CharField(_("nom du fichier"), max_length=255)
    url_retour = models.CharField(_("page d'origine"), max_length=500, blank=True)
    parametres = models.JSONField(_("données du rapport"), default=dict, blank=True)
    statut = models.CharField(
        _("statut"), max_length=12, choices=StatutDocumentPdf.choices, default=StatutDocumentPdf.EN_ATTENTE
    )
    fichier = models.FileField(_("fichier"), upload_to=_chemin_document_pdf, blank=True)
    erreur = models.TextField(_("erreur"), blank=True)
    created_at = models.DateTimeField(_("demandé le"), auto_now_add=True)
    termine_le = models.DateTimeField(_("terminé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("document PDF")
        verbose_name_plural = _("documents PDF")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.titre} ({self.get_statut_display()})"
