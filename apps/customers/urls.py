from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.ClientListView.as_view(), name="liste"),
    path("nouveau/", views.ClientCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.ClientDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ClientUpdateView.as_view(), name="modifier"),
    path("<int:pk>/interactions/", views.InteractionCreateView.as_view(), name="interaction"),
]
