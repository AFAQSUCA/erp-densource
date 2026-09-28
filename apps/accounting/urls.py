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
    path("grand-livre/imprimer/", views.GrandLivreImprimerView.as_view(), name="grand_livre_imprimer"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("balance/imprimer/", views.BalanceImprimerView.as_view(), name="balance_imprimer"),
    path("bilan/", views.BilanView.as_view(), name="bilan"),
    path("bilan/imprimer/", views.BilanImprimerView.as_view(), name="bilan_imprimer"),
    path("compte-de-resultat/", views.CompteDeResultatView.as_view(), name="compte_resultat"),
    path("compte-de-resultat/imprimer/", views.CompteDeResultatImprimerView.as_view(), name="compte_resultat_imprimer"),
]
