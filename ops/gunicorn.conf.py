"""Réglages Gunicorn (étape 7 lot 3) — cahier-des-charges.md:249 « Serveur : Gunicorn / WSGI ».

Logs sur la sortie standard : c'est `docker compose logs` (ou tout collecteur de logs de conteneurs)
qui les récupère, pas de fichier à gérer dans l'image.
"""

import multiprocessing
import os

bind = "0.0.0.0:8000"

# 2×CPU + 1 (repère standard Gunicorn), plafonné à 5 pour rester raisonnable sur un petit serveur ;
# réglable directement par variable d'environnement si le matériel réel demande autre chose.
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 5)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))

accesslog = "-"
errorlog = "-"
