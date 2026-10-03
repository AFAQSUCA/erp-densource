from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("operations-diverses/", views.EcritureManuelleListView.as_view(), name="ecritures_manuelles"),
    path("operations-diverses/nouvelle/", views.EcritureManuelleCreateView.as_view(), name="ecriture_manuelle_nouvelle"),
    path("operations-diverses/<int:pk>/", views.EcritureManuelleDetailView.as_view(), name="ecriture_manuelle"),
    path("operations-diverses/<int:pk>/valider/", views.EcritureManuelleValiderView.as_view(), name="ecriture_manuelle_valider"),
    path("operations-diverses/<int:pk>/contre-passer/", views.EcritureManuelleContrePasserView.as_view(), name="ecriture_manuelle_contre_passer"),
    path("operations-diverses/<int:pk>/abandonner/", views.EcritureManuelleAbandonnerView.as_view(), name="ecriture_manuelle_abandonner"),
    path("operations-diverses/<int:pk>/lignes/", views.LigneAjouterView.as_view(), name="ligne_ajouter"),
    path("operations-diverses/<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.LigneSupprimerView.as_view(), name="ligne_supprimer"),
    path("exercices/", views.ExerciceListView.as_view(), name="exercices"),
    path("exercices/<int:pk>/cloturer/", views.ExerciceCloturerView.as_view(), name="exercice_cloturer"),
    path("plan-comptable/", views.PlanComptableListView.as_view(), name="plan_comptable"),
    path("plan-comptable/nouveau/", views.CompteCreateView.as_view(), name="compte_nouveau"),
    path("plan-comptable/<int:pk>/modifier/", views.CompteModifierView.as_view(), name="compte_modifier"),
    path("grand-livre/", views.GrandLivreView.as_view(), name="grand_livre"),
    path("grand-livre/imprimer/", views.GrandLivreImprimerView.as_view(), name="grand_livre_imprimer"),
    path("grand-livre/excel/", views.GrandLivreXlsxView.as_view(), name="grand_livre_xlsx"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("balance/imprimer/", views.BalanceImprimerView.as_view(), name="balance_imprimer"),
    path("balance/excel/", views.BalanceXlsxView.as_view(), name="balance_xlsx"),
    path("bilan/", views.BilanView.as_view(), name="bilan"),
    path("bilan/imprimer/", views.BilanImprimerView.as_view(), name="bilan_imprimer"),
    path("bilan/excel/", views.BilanXlsxView.as_view(), name="bilan_xlsx"),
    path("compte-de-resultat/", views.CompteDeResultatView.as_view(), name="compte_resultat"),
    path("compte-de-resultat/imprimer/", views.CompteDeResultatImprimerView.as_view(), name="compte_resultat_imprimer"),
    path("compte-de-resultat/excel/", views.CompteDeResultatXlsxView.as_view(), name="compte_resultat_xlsx"),
    path("declaration-tva/", views.DeclarationTvaView.as_view(), name="declaration_tva"),
    path("declaration-tva/imprimer/", views.DeclarationTvaImprimerView.as_view(), name="declaration_tva_imprimer"),
    path("declaration-tva/excel/", views.DeclarationTvaXlsxView.as_view(), name="declaration_tva_xlsx"),
]
