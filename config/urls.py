"""Routes du projet.

Chaque app expose ses écrans dans son propre ``urls.py`` (espace de noms =
nom de l'app) ; ce fichier ne fait que les monter.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.dashboard.views import DashboardImprimerView, DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="home"),
    path("imprimer/", DashboardImprimerView.as_view(), name="home_imprimer"),
    # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
    path("", include("apps.accounts.urls")),
    path("missions/", include("apps.missions.urls")),
    path("clients/", include("apps.customers.urls")),
    path("flotte/", include("apps.fleet.urls")),
    path("rh/", include("apps.hr.urls")),
    path("chauffeurs/", include("apps.drivers.urls")),
    path("garage/", include("apps.garage.urls")),
    path("carburant/", include("apps.fuel.urls")),
    path("stock/", include("apps.inventory.urls")),
    path("facturation/", include("apps.billing.urls")),
    path("finances/", include("apps.finance.urls")),
    path("audit/", include("apps.audit.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("chauffeur/", include("apps.mobile_api.urls_web")),
    path("admin/", admin.site.urls),
]
