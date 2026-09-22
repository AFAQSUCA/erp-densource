#!/bin/sh
# Point d'entrée du conteneur applicatif (étape 7 lot 3) : préparé avant de lancer la commande
# reçue en argument (Gunicorn par défaut ; `celery worker` ou `celery beat` dans docker-compose.yml,
# qui n'ont besoin ni de collectstatic ni de migrer deux fois).
set -eu

if [ "${1:-}" = "gunicorn" ]; then
    echo "entrypoint : collecte des fichiers statiques"
    python manage.py collectstatic --noinput

    echo "entrypoint : migrations"
    python manage.py migrate --noinput
fi

exec "$@"
