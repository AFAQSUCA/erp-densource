from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("operations-diverses/", views.EcritureManuelleListView.as_view(), name="ecritures_manuelles"),
    path("operations-diverses/nouvelle/", views.EcritureManuelleCreateView.as_view(), name="ecriture_manuelle_nouvelle"),
    path("operations-diverses/<int:pk>/", views.EcritureManuelleDetailView.as_view(), name="ecriture_manuelle"),
    path("operations-diverses/<int:pk>/valider/", views.EcritureManuelleValiderView.as_view(), name="ecriture_manuelle_valider"),
    path("operations-diverses/<int:pk>/abandonner/", views.EcritureManuelleAbandonnerView.as_view(), name="ecriture_manuelle_abandonner"),
    path("operations-diverses/<int:pk>/lignes/", views.LigneAjouterView.as_view(), name="ligne_ajouter"),
    path("operations-diverses/<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.LigneSupprimerView.as_view(), name="ligne_supprimer"),
]
