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

    # MFA obligatoire ADMIN/DIRECTION — cahier-des-charges.md:276. Ce drapeau reflète l'état de
    # l'appareil TOTP (voir ``AppareilMFA``) : il est tenu à jour par ``accounts.mfa``, jamais à la main.
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


class AppareilMFA(models.Model):
    """Application d'authentification (TOTP) d'un utilisateur : un seul appareil par compte.

    Le secret sert à recalculer les codes à 6 chiffres ; tant que la personne n'a pas saisi un
    premier code valable (``confirme``), l'appareil n'est pas actif. ``dernier_pas`` mémorise le
    dernier intervalle de 30 secondes accepté : un même code ne sert qu'une fois (anti-rejeu).
    """

    utilisateur = models.OneToOneField(
        User, verbose_name=_("utilisateur"), on_delete=models.CASCADE, related_name="appareil_mfa"
    )
    secret = models.CharField(_("secret TOTP"), max_length=64)
    confirme = models.BooleanField(_("confirmé"), default=False)
    dernier_pas = models.BigIntegerField(_("dernier intervalle accepté"), default=0)
    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)
    confirme_le = models.DateTimeField(_("confirmé le"), null=True, blank=True)

    class Meta:
        db_table = "accounts_appareil_mfa"
        verbose_name = _("appareil MFA")
        verbose_name_plural = _("appareils MFA")

    def __str__(self):
        return f"MFA de {self.utilisateur}"


class CodeSecours(models.Model):
    """Code de secours à usage unique (téléphone perdu). Seule l'empreinte est conservée."""

    utilisateur = models.ForeignKey(
        User, verbose_name=_("utilisateur"), on_delete=models.CASCADE, related_name="codes_secours"
    )
    empreinte = models.CharField(_("empreinte SHA-256"), max_length=64, db_index=True)
    utilise_le = models.DateTimeField(_("utilisé le"), null=True, blank=True)

    class Meta:
        db_table = "accounts_code_secours"
        verbose_name = _("code de secours")
        verbose_name_plural = _("codes de secours")

    def __str__(self):
        return f"Code de secours de {self.utilisateur}"
