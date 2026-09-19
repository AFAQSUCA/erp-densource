from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="liste"),
    path("tout-lire/", views.ToutLireView.as_view(), name="tout_lire"),
    path("<int:pk>/lire/", views.LireView.as_view(), name="lire"),
]
