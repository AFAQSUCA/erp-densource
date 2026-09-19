from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.FactureListView.as_view(), name="factures"),
    path("nouvelle/", views.FactureCreateView.as_view(), name="nouvelle"),
    path("<int:pk>/", views.FactureDetailView.as_view(), name="facture"),
    path("<int:pk>/imprimer/", views.FacturePrintView.as_view(), name="imprimer"),
    path("<int:pk>/lignes/", views.LigneAjouterView.as_view(), name="ligne_ajouter"),
    path("<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.LigneSupprimerView.as_view(), name="ligne_supprimer"),
    path("<int:pk>/conditions/", views.ConditionsView.as_view(), name="conditions"),
    path("<int:pk>/soumettre/", views.SoumettreView.as_view(), name="soumettre"),
    path("<int:pk>/abandonner/", views.AbandonnerView.as_view(), name="abandonner"),
    path("<int:pk>/valider/", views.ValiderView.as_view(), name="valider"),
    path("<int:pk>/refuser/", views.RefuserView.as_view(), name="refuser"),
    path("<int:pk>/reglements/", views.ReglementAjouterView.as_view(), name="reglement_ajouter"),
    path(
        "<int:pk>/reglements/<int:reglement_pk>/annuler/",
        views.ReglementAnnulerView.as_view(),
        name="reglement_annuler",
    ),
    path("depenses/", views.DepenseListView.as_view(), name="depenses"),
    path("depenses/nouvelle/", views.DepenseCreateView.as_view(), name="depense_nouvelle"),
]
