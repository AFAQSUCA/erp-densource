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
]
