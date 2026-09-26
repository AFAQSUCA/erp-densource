from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.FactureListView.as_view(), name="factures"),
    path("imprimer/", views.FactureImprimerView.as_view(), name="factures_imprimer"),
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
    path("depenses/imprimer/", views.DepenseImprimerView.as_view(), name="depenses_imprimer"),
    path("depenses/nouvelle/", views.DepenseCreateView.as_view(), name="depense_nouvelle"),
    path("depenses/<int:pk>/mode/", views.DepenseModeView.as_view(), name="depense_mode"),
    path("devis/", views.ProformaListView.as_view(), name="proformas"),
    path("devis/imprimer/", views.ProformaImprimerView.as_view(), name="proformas_imprimer"),
    path("devis/nouveau/", views.ProformaCreateView.as_view(), name="proforma_nouveau"),
    path("devis/<int:pk>/", views.ProformaDetailView.as_view(), name="proforma"),
    path("devis/<int:pk>/imprimer/", views.ProformaPrintView.as_view(), name="proforma_imprimer"),
    path("devis/<int:pk>/modifier/", views.ProformaModifierView.as_view(), name="proforma_modifier"),
    path("devis/<int:pk>/abandonner/", views.ProformaAbandonnerView.as_view(), name="proforma_abandonner"),
    path("devis/<int:pk>/soumettre/", views.ProformaSoumettreView.as_view(), name="proforma_soumettre"),
    path(
        "devis/<int:pk>/contre-proposer/",
        views.ProformaContreProposerView.as_view(),
        name="proforma_contre_proposer",
    ),
    path(
        "devis/<int:pk>/valider-finances/",
        views.ProformaValiderFinancesView.as_view(),
        name="proforma_valider_finances",
    ),
    path(
        "devis/<int:pk>/valider-direction/",
        views.ProformaValiderDirectionView.as_view(),
        name="proforma_valider_direction",
    ),
    path(
        "devis/<int:pk>/envoyer-client/",
        views.ProformaEnvoyerClientView.as_view(),
        name="proforma_envoyer_client",
    ),
    path(
        "devis/<int:pk>/decision-client/",
        views.ProformaDecisionClientView.as_view(),
        name="proforma_decision_client",
    ),
    path(
        "devis/<int:pk>/creer-mission/",
        views.ProformaCreerMissionView.as_view(),
        name="proforma_creer_mission",
    ),
]
