from django.urls import path

from . import views

app_name = "drivers"

urlpatterns = [
    path("", views.ChauffeurListView.as_view(), name="liste"),
    path("<int:pk>/", views.ChauffeurDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ChauffeurUpdateView.as_view(), name="modifier"),
    path("<int:pk>/statut/", views.StatutView.as_view(), name="statut"),
]
