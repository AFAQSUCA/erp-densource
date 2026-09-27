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
    path("exercices/", views.ExerciceListView.as_view(), name="exercices"),
    path("exercices/<int:pk>/cloturer/", views.ExerciceCloturerView.as_view(), name="exercice_cloturer"),
    path("grand-livre/", views.GrandLivreView.as_view(), name="grand_livre"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("bilan/", views.BilanView.as_view(), name="bilan"),
    path("compte-de-resultat/", views.CompteDeResultatView.as_view(), name="compte_resultat"),
]
