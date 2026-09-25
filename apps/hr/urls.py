from django.urls import path

from . import views

app_name = "hr"

urlpatterns = [
    path("conges/", views.CongeListView.as_view(), name="conges_liste"),
    path("conges/imprimer/", views.CongeImprimerView.as_view(), name="conges_imprimer"),
    path("conges/nouveau/", views.CongeCreateView.as_view(), name="conges_nouveau"),
    path("conges/<int:pk>/", views.CongeDetailView.as_view(), name="conges_detail"),
    path("conges/<int:pk>/decision/", views.CongeDecisionView.as_view(), name="conges_decision"),
    path("personnel/", views.PersonnelListView.as_view(), name="personnel_liste"),
    path("personnel/imprimer/", views.PersonnelImprimerView.as_view(), name="personnel_imprimer"),
    path("personnel/nouveau/", views.PersonnelCreateView.as_view(), name="personnel_nouveau"),
    path("personnel/importer/", views.PersonnelImportView.as_view(), name="personnel_importer"),
    path(
        "personnel/importer/modele.xlsx",
        views.PersonnelModeleImportView.as_view(),
        name="personnel_import_modele",
    ),
    path("personnel/<int:pk>/", views.PersonnelDetailView.as_view(), name="personnel_detail"),
    path(
        "personnel/<int:pk>/modifier/",
        views.PersonnelUpdateView.as_view(),
        name="personnel_modifier",
    ),
    path(
        "personnel/<int:pk>/jours-exceptionnels/",
        views.AttributionView.as_view(),
        name="personnel_attribution",
    ),
]
