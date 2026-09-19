from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView

from .models import Role


class ConnexionView(LoginView):
    """Page de connexion. Les connexions réussies ou ratées sont tracées dans
    ``audit_log`` par les signaux de l'app ``audit``."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        reponse = super().form_valid(form)
        if self.request.user.role == Role.CHAUFFEUR:
            # Espace mobile : 15 minutes d'inactivité (cahier-des-charges.md:285), 30 pour le bureau.
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE_MOBILE)
        return reponse


class DeconnexionView(LogoutView):
    """Déconnexion (POST uniquement, protégée par CSRF)."""
