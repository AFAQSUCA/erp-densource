from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.TresorerieView.as_view(), name="tresorerie"),
    path("mouvements/", views.MouvementCreateView.as_view(), name="mouvement_creer"),
    path("mouvements/<int:pk>/annuler/", views.MouvementAnnulerView.as_view(), name="mouvement_annuler"),
]
