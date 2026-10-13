"""Réglages du serveur ASGI de la recette du suivi en direct (scénario E1, ``test_temps_reel.py``).

Ceux du développement (``runserver`` de Daphne : pages, fichiers statiques et WebSocket dans un seul processus),
mais sur une base jetable : jamais la base de démonstration.
"""

import os

from config.settings.dev import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ["RECETTE_BASE"],
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
NOTIFICATIONS_EMAIL = False
