"""Routes de l'API versionnée ``/api/v1/`` (architecture.md, ADR-007)."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.routers import SimpleRouter

from . import auth
from .permissions import EstAdminOuDirection
from .v1 import views

app_name = "api"

routeur = SimpleRouter()
routeur.register("missions", views.MissionViewSet, basename="mission")
routeur.register("camions", views.VehiculeViewSet, basename="camion")
routeur.register("chauffeurs", views.ChauffeurViewSet, basename="chauffeur")
routeur.register("clients", views.ClientViewSet, basename="client")
routeur.register("factures", views.FactureViewSet, basename="facture")

# La documentation décrit toute l'API : réservée à l'ADMIN et à la DIRECTION, connectés à l'interface web.
_protection = {"authentication_classes": [SessionAuthentication], "permission_classes": [EstAdminOuDirection]}

urlpatterns = [
    path("auth/token/", auth.ConnexionView.as_view(), name="token"),
    path("auth/token/refresh/", auth.RenouvellementView.as_view(), name="token_refresh"),
    path("auth/logout/", auth.DeconnexionView.as_view(), name="logout"),
    path("moi/", auth.ProfilView.as_view(), name="moi"),
    path("schema/", SpectacularAPIView.as_view(**_protection), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema", **_protection), name="docs"),
    path("mobile/", include("apps.mobile_api.urls")),
    path("", include(routeur.urls)),
]
