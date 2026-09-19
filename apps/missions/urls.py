from django.urls import path

from . import views

app_name = "missions"

urlpatterns = [
    path("", views.MissionListView.as_view(), name="liste"),
    path("nouvelle/", views.MissionCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.MissionDetailView.as_view(), name="detail"),
    path("<int:pk>/planifier/", views.PlanifierView.as_view(), name="planifier"),
    path("<int:pk>/affecter/", views.AffecterView.as_view(), name="affecter"),
    path("<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("<int:pk>/cloturer/", views.CloturerView.as_view(), name="cloturer"),
    path("<int:pk>/qr/<str:qui>.png", views.CodeQrView.as_view(), name="qr"),
]
