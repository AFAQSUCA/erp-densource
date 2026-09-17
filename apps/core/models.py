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
