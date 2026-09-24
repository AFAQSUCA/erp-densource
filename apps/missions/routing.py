from django.urls import path

from .consumers import MissionSuiviConsumer

websocket_urlpatterns = [
    path("ws/missions/suivi/", MissionSuiviConsumer.as_asgi()),
]
