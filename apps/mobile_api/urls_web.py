"""Écrans mobiles du chauffeur, montés sous ``/chauffeur/`` par ``config/urls.py``."""

from django.urls import path

from . import views_web as v

app_name = "chauffeur"

urlpatterns = [
    path("", v.AccueilView.as_view(), name="accueil"),
    path("missions/", v.MissionsView.as_view(), name="missions"),
    path("missions/<int:pk>/", v.MissionView.as_view(), name="mission"),
    path("missions/<int:pk>/demarrer/", v.DemarrerView.as_view(), name="demarrer"),
    path("missions/<int:pk>/recuperation/", v.RecuperationView.as_view(), name="recuperation"),
    path("missions/<int:pk>/livraison/", v.LivraisonView.as_view(), name="livraison"),
    path("missions/<int:pk>/checklist/", v.ChecklistView.as_view(), name="checklist"),
    path("plein/", v.PleinView.as_view(), name="plein"),
    path("incident/", v.IncidentView.as_view(), name="incident"),
    path("manifest.webmanifest", v.ManifesteView.as_view(), name="manifeste"),
    path("sw.js", v.ServiceWorkerView.as_view(), name="sw"),
    path("hors-ligne/", v.HorsLigneView.as_view(), name="hors_ligne"),
]
