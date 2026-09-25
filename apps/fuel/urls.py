from django.urls import path

from . import views

app_name = "fuel"

urlpatterns = [
    path("", views.PleinListView.as_view(), name="liste"),
    path("imprimer/", views.PleinImprimerView.as_view(), name="imprimer"),
    path("nouveau/", views.PleinCreateView.as_view(), name="creer"),
    path("analyse/", views.AnalyseView.as_view(), name="analyse"),
]
