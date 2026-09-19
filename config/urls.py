"""Routes du projet.

Chaque app expose ses écrans dans son propre ``urls.py`` (espace de noms =
nom de l'app) ; ce fichier ne fait que les monter.
"""

from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import AccueilView

urlpatterns = [
    path("", AccueilView.as_view(), name="home"),
    path("", include("apps.accounts.urls")),
    path("missions/", include("apps.missions.urls")),
    path("flotte/", include("apps.fleet.urls")),
    path("chauffeurs/", include("apps.drivers.urls")),
    path("admin/", admin.site.urls),
]
