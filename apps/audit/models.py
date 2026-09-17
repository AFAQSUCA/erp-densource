from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ActionChoices(models.TextChoices):
    CREATE = "CREATE", _("Création")
    UPDATE = "UPDATE", _("Modification")
    DELETE = "DELETE", _("Suppression")
    LOGIN = "LOGIN", _("Connexion")
    LOGOUT = "LOGOUT", _("Déconnexion")
    VALIDATE = "VALIDATE", _("Validation")


class StatutChoices(models.TextChoices):
    SUCCESS = "SUCCESS", _("Succès")
    FAILED = "FAILED", _("Échec")


class AuditLog(models.Model):
    """Journal d'audit append-only — cahier-des-charges.md:56-82 (14 champs).

    Immuabilité stricte : ``save()`` refuse toute modification d'une ligne
    existante, ``delete()`` est désactivé. Conservation ≥ 5 ans (purge hors
    applicatif, cf. politique de rétention BDD).
    """

    date_heure = models.DateTimeField(_("date/heure"), auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("utilisateur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    utilisateur_nom = models.CharField(_("nom utilisateur"), max_length=150, blank=True)
    role = models.CharField(_("rôle"), max_length=20, blank=True)
    action = models.CharField(_("action"), max_length=10, choices=ActionChoices.choices)
    module = models.CharField(_("module"), max_length=50)
    entite = models.CharField(_("entité"), max_length=100)
    entite_id = models.BigIntegerField(_("ID entité"), null=True, blank=True)
    ancienne_valeur = models.JSONField(_("ancienne valeur"), null=True, blank=True)
    nouvelle_valeur = models.JSONField(_("nouvelle valeur"), null=True, blank=True)
    adresse_ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    user_agent = models.CharField(_("user-agent"), max_length=255, blank=True)
    statut = models.CharField(
        _("statut"),
        max_length=10,
        choices=StatutChoices.choices,
        default=StatutChoices.SUCCESS,
    )

    class Meta:
        db_table = "audit_log"
        verbose_name = _("entrée d'audit")
        verbose_name_plural = _("journal d'audit")
        ordering = ["-date_heure"]
        indexes = [
            models.Index(fields=["module", "entite", "entite_id"]),
            models.Index(fields=["utilisateur", "date_heure"]),
        ]

    def __str__(self):
        return f"{self.date_heure:%Y-%m-%d %H:%M:%S} {self.action} {self.module}.{self.entite}#{self.entite_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "AuditLog est append-only : modification d'une entrée existante interdite."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog est append-only : suppression interdite.")
