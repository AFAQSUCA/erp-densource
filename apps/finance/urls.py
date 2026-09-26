from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.TresorerieView.as_view(), name="tresorerie"),
    path("imprimer/", views.TresorerieImprimerView.as_view(), name="imprimer"),
    path(
        "versements/<int:pk>/confirmer/",
        views.VersementConfirmerView.as_view(),
        name="versement_confirmer",
    ),
    path("mouvements/", views.MouvementCreateView.as_view(), name="mouvement_creer"),
    path("mouvements/<int:pk>/annuler/", views.MouvementAnnulerView.as_view(), name="mouvement_annuler"),
    path("demandes/", views.DemandeListView.as_view(), name="demandes"),
    path("demandes/nouvelle/", views.DemandeCreateView.as_view(), name="demande_nouvelle"),
    path("demandes/<int:pk>/", views.DemandeDetailView.as_view(), name="demande"),
    path("demandes/<int:pk>/decider/", views.DemandeDeciderView.as_view(), name="demande_decider"),
    path("ordres/<int:pk>/executer/", views.OrdreExecuterView.as_view(), name="ordre_executer"),
    path("ordres/<int:pk>/revalider/", views.OrdreRevaliderView.as_view(), name="ordre_revalider"),
    path("enveloppes/", views.EnveloppeListView.as_view(), name="enveloppes"),
    path("enveloppes/nouvelle/", views.EnveloppeCreateView.as_view(), name="enveloppe_nouvelle"),
]
