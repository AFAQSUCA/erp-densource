from django.urls import path

from . import views

app_name = "importation"

urlpatterns = [
    path("", views.ImportView.as_view(), name="importer"),
    path("modele.xlsx", views.ModeleView.as_view(), name="modele"),
]
