"""
Configuration ASGI : HTTP (Django) et WebSocket (suivi des missions en direct).

En production, gunicorn (WSGI) sert les pages ; ce module n'est lancé que par le conteneur `realtime`
(daphne), auquel Nginx envoie les connexions ``/ws/``. En développement, `runserver` (daphne) sert
tout à la fois.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

# Doit précéder l'import des consommateurs : il initialise le registre des applications Django.
application_http = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.missions.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": application_http,
    # L'origine de la page doit figurer dans ALLOWED_HOSTS (sans cela, n'importe quel site pourrait
    # ouvrir une WebSocket avec la session de l'utilisateur) ; la session identifie la personne.
    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
})
