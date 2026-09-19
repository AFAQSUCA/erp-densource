from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("or/<int:pk>/sortie/", views.SortieOrView.as_view(), name="sortie_or"),
]
