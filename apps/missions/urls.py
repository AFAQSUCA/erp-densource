from django.urls import path

from . import views

app_name = "missions"

urlpatterns = [
    path("", views.MissionListView.as_view(), name="liste"),
    path("imprimer/", views.MissionImprimerView.as_view(), name="imprimer"),
    path("nouvelle/", views.MissionCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.MissionDetailView.as_view(), name="detail"),
    path("<int:pk>/planifier/", views.PlanifierView.as_view(), name="planifier"),
    path("<int:pk>/affecter/", views.AffecterView.as_view(), name="affecter"),
    path("<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("<int:pk>/cloturer/", views.CloturerView.as_view(), name="cloturer"),
    path("<int:pk>/codes.pdf", views.CodesPdfView.as_view(), name="codes_pdf"),
    path("<int:pk>/qr/<str:qui>.png", views.CodeQrView.as_view(), name="qr"),
    path("frais/", views.FraisMissionListeView.as_view(), name="frais_liste"),
    path("<int:pk>/frais/", views.FraisMissionDetailView.as_view(), name="frais"),
    path("<int:pk>/frais/imprimer/", views.FraisMissionPrintView.as_view(), name="frais_imprimer"),
    path("<int:pk>/frais/planifier/", views.FraisPlanifierView.as_view(), name="frais_planifier"),
    path(
        "frais/<int:frais_pk>/valider-parcauto/",
        views.FraisValiderParcautoView.as_view(),
        name="frais_valider_parcauto",
    ),
    path(
        "frais/<int:frais_pk>/valider-finances/",
        views.FraisValiderFinancesView.as_view(),
        name="frais_valider_finances",
    ),
    path("frais/<int:frais_pk>/rejeter/", views.FraisRejeterView.as_view(), name="frais_rejeter"),
]
