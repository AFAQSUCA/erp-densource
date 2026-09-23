from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import reverse_lazy

from . import throttle
from .models import Role
from .signals import mot_de_passe_reinitialise


class ConnexionView(LoginView):
    """Page de connexion. Les connexions réussies ou ratées sont tracées dans
    ``audit_log`` par les signaux de l'app ``audit``.

    Anti force brute : après trop d'échecs pour un même identifiant depuis une même adresse (ou
    trop d'échecs depuis l'adresse), la connexion est refusée pour un temps, **même avec le bon mot
    de passe** : la vérification n'est même pas tentée."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        restant = throttle.connexion_secondes_restantes(request, request.POST.get("username", ""))
        if restant:
            form = AuthenticationForm(request)  # non liée : aucune vérification de mot de passe
            blocage = f"Trop de tentatives échouées. Réessayez dans {throttle.phrase_attente(restant)}."
            reponse = self.render_to_response(self.get_context_data(form=form, blocage=blocage))
            reponse.status_code = 429
            return reponse
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reponse = super().form_valid(form)
        throttle.connexion_reinitialiser(self.request, form.cleaned_data.get("username", ""))
        if self.request.user.role == Role.CHAUFFEUR:
            # Espace mobile : 15 minutes d'inactivité (cahier-des-charges.md:285), 30 pour le bureau.
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE_MOBILE)
        return reponse


class DeconnexionView(LogoutView):
    """Déconnexion (POST uniquement, protégée par CSRF)."""


# --- mot de passe oublié ---
#
# Les 4 étapes standard de Django, avec nos gabarits (français, mise en page du site) : demande de
# l'adresse -> confirmation d'envoi -> lien reçu par e-mail -> nouveau mot de passe -> terminé.
# Ne dit jamais si l'adresse correspond à un compte (mêmes pages dans les deux cas) : un tiers ne
# peut pas s'en servir pour savoir qui a un compte ici. Le mot de passe choisi passe par les mêmes
# règles qu'à l'inscription (AUTH_PASSWORD_VALIDATORS, longueur 10, Argon2).


class ReinitialiserMotDePasseView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class ReinitialiserMotDePasseEnvoyeView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class ReinitialiserMotDePasseConfirmerView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        reponse = super().form_valid(form)
        mot_de_passe_reinitialise.send(sender=self.__class__, request=self.request, utilisateur=self.user)
        return reponse


class ReinitialiserMotDePasseTermineeView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"
