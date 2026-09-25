from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.JournalListView.as_view(), name="journal"),
    path("imprimer/", views.JournalImprimerView.as_view(), name="imprimer"),
    path("export.csv", views.JournalExporterCsvView.as_view(), name="export_csv"),
]
