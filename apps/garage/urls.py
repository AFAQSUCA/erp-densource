from django.urls import path

from . import views

app_name = "garage"

urlpatterns = [
    path("", views.OrListView.as_view(), name="liste"),
    path("nouveau/", views.OrCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.OrDetailView.as_view(), name="detail"),
    path("<int:pk>/cloturer/", views.OrCloturerView.as_view(), name="cloturer"),
    path("camions/<int:pk>/immobiliser/", views.ImmobiliserView.as_view(), name="immobiliser"),
    path("camions/<int:pk>/hors-service/", views.HorsServiceView.as_view(), name="hors_service"),
    path(
        "camions/<int:pk>/remise-en-service/",
        views.RemiseEnServiceView.as_view(),
        name="remise_en_service",
    ),
]
