from django.urls import path

from . import views, views_terrain

app_name = "garage"

urlpatterns = [
    path("", views.OrListView.as_view(), name="liste"),
    path("imprimer/", views.OrImprimerView.as_view(), name="imprimer"),
    path("nouveau/", views.OrCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.OrDetailView.as_view(), name="detail"),
    path("<int:pk>/cloturer/", views.OrCloturerView.as_view(), name="cloturer"),
    path("incidents/", views_terrain.IncidentListView.as_view(), name="incidents"),
    path("incidents/imprimer/", views_terrain.IncidentImprimerView.as_view(), name="incidents_imprimer"),
    path("incidents/<int:pk>/", views_terrain.IncidentDetailView.as_view(), name="incident"),
    path(
        "incidents/<int:pk>/traiter/",
        views_terrain.IncidentTraiterView.as_view(),
        name="incident_traiter",
    ),
    path("checklists/", views_terrain.ChecklistListView.as_view(), name="checklists"),
    path("camions/<int:pk>/immobiliser/", views.ImmobiliserView.as_view(), name="immobiliser"),
    path("camions/<int:pk>/hors-service/", views.HorsServiceView.as_view(), name="hors_service"),
    path(
        "camions/<int:pk>/remise-en-service/",
        views.RemiseEnServiceView.as_view(),
        name="remise_en_service",
    ),
]
