"""Signaux de l'app ``accounts``.

``mfa_evenement`` : émis à chaque étape de la double authentification (activation, code vérifié ou
refusé, codes régénérés, réinitialisation). ``mot_de_passe_reinitialise`` : émis quand un compte
choisit un nouveau mot de passe via « mot de passe oublié » (``views.ReinitialiserMotDePasseConfirmerView``).
L'app ``audit`` s'y abonne pour inscrire ces deux au journal : ``accounts`` n'importe pas ``audit``
(sens des dépendances, architecture.md:134).

Les récepteurs ci-dessous branchent aussi la limitation d'essais et l'oubli de la vérification MFA
sur les signaux d'authentification de Django.
"""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import Signal, receiver

from . import mfa, throttle

# providing_args : request, utilisateur, evenement (str), succes (bool)
mfa_evenement = Signal()

# providing_args : request, utilisateur
mot_de_passe_reinitialise = Signal()


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
