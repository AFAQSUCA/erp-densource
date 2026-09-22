# Image de production — étape 7 lot 3 (architecture.md §6 « Vue déploiement »).
#
# Les styles, icônes et Alpine.js sont déjà compilés et versionnés dans static/ (frontend/README.md) :
# Node n'est pas nécessaire ici, une seule étape suffit.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 : bibliothèque cliente PostgreSQL utilisée par psycopg au démarrage (le wheel « binary »
# embarque le nécessaire à l'installation, mais la garder explicite évite une surprise si le wheel
# venait à manquer pour une architecture donnée).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt

COPY . .

# Compte non privilégié : l'application n'a besoin d'écrire que staticfiles/ et media/ (montés en
# volumes par docker-compose.yml). Les créer ici, avant le premier montage du volume : Docker
# reprend alors les droits de ce dossier pour initialiser le volume (sinon, root).
RUN useradd --create-home --uid 1000 django \
    && mkdir -p staticfiles media \
    && chown -R django:django /app
USER django

EXPOSE 8000

ENTRYPOINT ["ops/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "ops/gunicorn.conf.py"]
