"""Routes de l'API mobile : montées sous ``/api/v1/mobile/`` par ``apps.api.urls``."""

from django.urls import path

from . import views

app_name = "mobile"

urlpatterns = [
    path("missions/", views.MissionsView.as_view(), name="missions"),
    path("missions/<int:pk>/", views.MissionView.as_view(), name="mission"),
    path("missions/<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("missions/<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("missions/<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("missions/<int:pk>/checklist/", views.ChecklistView.as_view(), name="checklist"),
    path("pleins/", views.PleinsView.as_view(), name="pleins"),
    path("incidents/", views.IncidentsView.as_view(), name="incidents"),
]
