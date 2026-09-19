from django.urls import path

from . import views

app_name = "fleet"

urlpatterns = [
    path("", views.VehiculeListView.as_view(), name="liste"),
    path("nouveau/", views.VehiculeCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.VehiculeDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.VehiculeUpdateView.as_view(), name="modifier"),
    path("<int:pk>/document/", views.DocumentView.as_view(), name="document"),
]
