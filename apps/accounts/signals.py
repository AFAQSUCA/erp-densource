"""Signaux de l'app ``accounts``.

``mfa_evenement`` : émis à chaque étape de la double authentification (activation, code vérifié ou
refusé, codes régénérés, réinitialisation). ``mot_de_passe_reinitialise`` : émis quand un compte
choisit un nouveau mot de passe via « mot de passe oublié » (``views.ReinitialiserMotDePasseConfirmerView``) ;
``mot_de_passe_change`` : quand un compte connecté change le sien (``views.ChangerMotDePasseView``).
L'app ``audit`` s'y abonne pour inscrire ces deux au journal : ``accounts`` n'importe pas ``audit``
(sens des dépendances, architecture.md:134).

Les récepteurs ci-dessous branchent aussi la limitation d'essais et l'oubli de la vérification MFA
sur les signaux d'authentification de Django.
"""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver

from . import mfa, throttle

# providing_args : request, utilisateur, evenement (str), succes (bool)
mfa_evenement = Signal()

# providing_args : request, utilisateur
mot_de_passe_reinitialise = Signal()

# providing_args : request, utilisateur
mot_de_passe_change = Signal()

# Un compte vient d'être créé avec le rôle DIRECTION, ou de recevoir ce rôle (admin Django compris) : la
# Direction en est prévenue (``notifications``, décision du 13/10/2026, audit AUD-09). Argument : ``utilisateur``.
compte_direction_attribue = Signal()


@receiver(user_login_failed)
def compter_echec_de_connexion(sender, credentials, request=None, **kwargs):
    """Chaque échec (formulaire web, administration, API) alimente le compteur anti force brute."""
    if request is not None:
        throttle.connexion_enregistrer_echec(request, credentials.get("username", ""))


@receiver(user_logged_in)
def repartir_sans_mfa_verifiee(sender, request=None, user=None, **kwargs):
    """Une nouvelle ouverture de session doit repasser la MFA, même pour la même personne."""
    session = getattr(request, "session", None)
    if session is not None:
        mfa.oublier_verification(request)


# --- jetons de l'API révoqués quand le compte change (audit TECH-43) ---

CHAMPS_SENSIBLES = ("password", "role", "is_active")


@receiver(pre_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="accounts-jetons-avant")
def memoriser_les_champs_sensibles(sender, instance, update_fields=None, **kwargs):
    """Avant l'enregistrement : mot de passe, rôle et activation tels qu'en base, pour détecter un changement quel
    que soit le chemin (écran, admin Django, mot de passe oublié, services)."""
    instance._champs_sensibles_avant = None
    if instance.pk is None or (update_fields is not None and not set(update_fields) & set(CHAMPS_SENSIBLES)):
        return
    instance._champs_sensibles_avant = (
        sender.objects.filter(pk=instance.pk).values_list(*CHAMPS_SENSIBLES).first()
    )


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="accounts-jetons-apres")
def revoquer_les_jetons_si_le_compte_change(sender, instance, created=False, **kwargs):
    avant = getattr(instance, "_champs_sensibles_avant", None)
    if created or avant is None:
        return
    if avant != tuple(getattr(instance, champ) for champ in CHAMPS_SENSIBLES):
        from . import services

        services.revoquer_jetons_api(instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="accounts-compte-direction")
def signaler_un_compte_direction(sender, instance, created=False, **kwargs):
    """Création d'un compte DIRECTION ou attribution de ce rôle (audit AUD-09)."""
    from .models import Role

    if instance.role != Role.DIRECTION:
        return
    avant = getattr(instance, "_champs_sensibles_avant", None)
    if created or (avant is not None and avant[CHAMPS_SENSIBLES.index("role")] != Role.DIRECTION):
        compte_direction_attribue.send(sender=sender, utilisateur=instance)
