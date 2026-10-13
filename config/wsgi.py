"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Point d'entrée des serveurs de production (gunicorn, daphne, celery) : sans DJANGO_SETTINGS_MODULE, on part
# sur la production, qui exige ses secrets, jamais sur le développement (DEBUG actif) — audit TECH-47.
# ``manage.py`` garde le développement par défaut.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

application = get_wsgi_application()
