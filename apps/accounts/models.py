from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """7 rôles utilisateurs — cahier-des-charges.md:44-55."""

    ADMIN = "ADMIN", _("Administrateur")
    DIRECTION = "DIRECTION", _("Direction")
    RH = "RH", _("Ressources Humaines")
    CHARGE_CLIENTELE = "CHARGE_CLIENTELE", _("Chargé clientèle")
    PARCAUTO = "PARCAUTO", _("Parc Auto")
    FINANCES = "FINANCES", _("Finances")
    CHAUFFEUR = "CHAUFFEUR", _("Chauffeur")


class User(AbstractUser):
    """Utilisateur de l'ERP.

    RBAC simple : un utilisateur = un rôle principal
    (architecture.md:534, hypothèse H2). La désactivation utilise le
    champ standard ``is_active`` de Django plutôt que le soft delete de
    ``BaseModel`` : un compte auth n'est pas un « enregistrement métier »
    et le queryset par défaut d'authentification ne doit jamais être
    filtré silencieusement.
    """

    role = models.CharField(_("rôle"), max_length=20, choices=Role.choices)
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)

    # MFA obligatoire ADMIN/DIRECTION — cahier-des-charges.md:276.
    # Le flag ci-dessous ne fait qu'exposer l'état ; le flux TOTP complet
    # (django-otp ou équivalent) sera ajouté à la phase durcissement
    # sécurité (étape 7) — voir README.md de l'app.
    mfa_enabled = models.BooleanField(_("MFA activé"), default=False)

    class Meta:
        db_table = "accounts_user"
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_effectif(self) -> str:
        """Rôle utilisé pour les droits : un superutilisateur agit en ADMIN.

        ``createsuperuser`` ne renseigne pas ``role`` ; sans cela le premier
        compte créé ne verrait aucun écran de l'interface.
        """
        return Role.ADMIN if self.is_superuser else self.role

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_direction(self):
        return self.role == Role.DIRECTION
