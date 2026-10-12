from django.urls import path

from . import views

app_name = "sauvegardes"

urlpatterns = [
    path("", views.SauvegardesView.as_view(), name="liste"),
]
