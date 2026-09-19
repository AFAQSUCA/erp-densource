from django.contrib.auth.views import LoginView, LogoutView


class ConnexionView(LoginView):
    """Page de connexion. Les connexions réussies ou ratées sont tracées dans
    ``audit_log`` par les signaux de l'app ``audit``."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True


class DeconnexionView(LogoutView):
    """Déconnexion (POST uniquement, protégée par CSRF)."""
