# Déployer l'ERP DEN Source Group

Guide du déploiement sur un **serveur Linux unique avec Docker Compose** — le choix retenu pour ce
projet (cahier-des-charges.md §4 « Conteneurisation », architecture.md §6 « Vue déploiement »). Pas
de réplique de base, pas de cluster Redis, pas de CDN : un seul serveur, suffisant pour le volume
visé, que les mêmes fichiers (`docker-compose.yml`) laissent la porte ouverte à faire évoluer plus
tard sans réécrire l'application.

Ce que ce fichier décrit a été **testé en local** (voir « Ce qui a été vérifié » en bas de page) :
la pile complète (application, Celery, Nginx, PostgreSQL, Redis) démarre et sert de vraies pages à
travers Nginx, exactement comme en production — seul un vrai domaine et un vrai certificat TLS
manquent à l'essai local.

## 1. Ce qui tourne

```
Internet ──► Nginx (80/443) ──► Gunicorn (web, 3 workers) ──► PostgreSQL
                 │                      │                         ▲
                 │                      └──► Celery worker ───────┤
                 ├── /static/, /media/       Celery beat ─────────┘
                 │   (disque, pas Gunicorn)        │
                 └────────────────────────────► Redis (cache + file Celery)
```

6 conteneurs (`docker-compose.yml`) : `nginx`, `web` (Gunicorn), `celery_worker`, `celery_beat`,
`db` (PostgreSQL), `redis`. Un seul construit une image (`web`, `celery_worker`, `celery_beat`
partagent la même, définie par `Dockerfile`) ; `db`, `redis` et `nginx` sont des images officielles
telles quelles.

## 2. Choisir un serveur, à moindre coût

Pas besoin d'un gros serveur : `docker-compose.yml` fait tourner nginx, l'application, Celery,
PostgreSQL et Redis confortablement sur **2 Go de RAM**. Les niveaux « toujours gratuits » des
grands fournisseurs cloud (Oracle Cloud notamment) ne sont pas ouverts à l'inscription depuis tous
les pays ; plutôt que de perdre du temps à contourner ça, un petit VPS payant revient à
2 000-4 000 FCFA/mois (3-5 €) — à comparer aux 200 000 FCFA/mois prévus au cahier des charges pour
l'exploitation réelle, c'est un coût marginal pour un pilote ou une démo, et **rien dans ce dépôt
n'a besoin de changer** pour en profiter : ce sont les mêmes commandes, plus bas, sur n'importe quel
Linux avec Docker.

Quelques fournisseurs qui acceptent les paiements internationaux (carte, parfois PayPal) et ont des
centres en Europe — plus proches d'Abidjan qu'un serveur américain, donc une meilleure latence :

| Fournisseur | Offre indicative | Note |
|---|---|---|
| **Contabo** | ~4-5 €/mois, 8 Go de RAM | Très généreux pour le prix |
| **OVH** (VPS) | ~4-6 €/mois, 2 Go de RAM | Société française, présente en Afrique |
| **DigitalOcean** | ~6 $/mois, 1 Go de RAM | Documentation abondante, simple à prendre en main |
| **Hetzner** | ~4-5 €/mois, 4 Go de RAM | Très bon rapport prix/performance (Europe uniquement) |

Prendre l'offre la plus petite (1-2 Go de RAM) avec **Ubuntu 22.04 ou 24.04 LTS** suffit.

## 3. Prérequis sur le serveur

- Un serveur Linux (Debian/Ubuntu conviennent) avec **Docker** et le plugin **Docker Compose**
  installés (`docker compose version`) — une fois le VPS créé :

  ```bash
  curl -fsSL https://get.docker.com | sh   # script officiel Docker, installe aussi le plugin Compose
  ```

- Un **nom de domaine** pointé (DNS, enregistrement A) vers l'adresse IP du serveur — nécessaire
  pour obtenir un certificat HTTPS (étape 8). Pas besoin d'en acheter un pour démarrer :
  [DuckDNS](https://www.duckdns.org) donne gratuitement un sous-domaine (`mon-erp.duckdns.org`)
  qui fonctionne tout aussi bien avec Let's Encrypt qu'un domaine payant.
- Les ports **80** et **443** ouverts (pare-feu du serveur / du fournisseur cloud — souvent une
  « security list » ou un « firewall » à configurer dans le tableau de bord du fournisseur, en plus
  du pare-feu du système : `ufw allow 80,443/tcp` sous Ubuntu).
- Git, pour récupérer le dépôt.

## 4. Préparer le serveur

```bash
git clone <url-du-dépôt> erp-densource
cd erp-densource
cp .env.example .env
```

Éditer `.env` et renseigner au minimum (voir les commentaires du fichier) :

| Variable | Valeur |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `SECRET_KEY` | une valeur longue et aléatoire — jamais celle de `.env.example` ; générer avec `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | le domaine, ex. `erp.densourcegroup.ci` |
| `CSRF_TRUSTED_ORIGINS` | `https://` + le même domaine |
| `POSTGRES_PASSWORD` | un mot de passe long, différent de celui de `.env.example` |
| `TRUSTED_PROXY_COUNT` | `1` (Nginx est l'unique proxy devant l'application) |
| `SAUVEGARDE_PASSPHRASE` | une phrase de passe longue, **à conserver ailleurs que sur ce serveur** (étape 9) |

`DATABASE_URL` et `REDIS_URL` n'ont **pas** à être renseignées dans `.env` pour ces quatre services :
`docker-compose.yml` les fixe lui-même vers `db` et `redis` (les noms des conteneurs). Elles ne
servent, en valeur `localhost`, que pour un test depuis la machine hors conteneur (étape 7 lot 2).

## 5. Démarrer

```bash
docker compose up -d --build
```

Au premier démarrage, `web` collecte les fichiers statiques et applique les migrations avant de
lancer Gunicorn (`ops/entrypoint.sh`) ; `celery_worker` et `celery_beat` attendent que `web` soit en
bonne santé (les migrations sont donc déjà passées) avant de démarrer.

```bash
docker compose ps                 # les 6 services doivent être « healthy » ou « running »
docker compose logs -f web        # suivre le démarrage
curl -I http://localhost/connexion/   # doit répondre 301 (redirigé vers https, tant que le 4 n'est pas fait)
```

Créer le premier compte administrateur :

```bash
docker compose exec web python manage.py createsuperuser
```

## 6. Comptes de démonstration

**Ne jamais lancer `creer_comptes_demo` en production** (la commande refuse de tourner si
`DEBUG=False` — apps/hr/management/commands/creer_comptes_demo.py) : ces comptes sont réservés au
développement.

## 7. Vérifier avant la mise en service réelle

Avant que les vrais utilisateurs n'arrivent, il est légitime de saisir quelques fiches réalistes
(personnel, un client, une mission…) pour parcourir les écrans une dernière fois sur ce serveur.

1. Créez le premier compte administrateur si ce n'est pas déjà fait (étape 5), activez sa MFA.
2. Saisissez quelques fiches à la main (recrutement, import Excel du personnel, un client, une
   mission…) et vérifiez les écrans qui comptent pour vous.
3. **Avant la mise en service réelle, repartez d'une base vide** plutôt que de supprimer les
   fiches une par une : la suppression est *logique* (`BaseModel.delete`, cahier-des-charges.md
   « jamais de suppression physique ») — les lignes resteraient en base, et les numéros déjà
   attribués (matricule, missions…) ne redescendraient pas à 1. Le plus sûr est d'effacer le
   volume de la base et de repartir d'une migration propre :

   ```bash
   docker compose down
   docker volume rm erp-densource_db_data
   docker compose up -d --build
   docker compose exec web python manage.py createsuperuser
   ```

   (Adapter le nom du volume si le dossier du projet ne s'appelle pas `erp-densource` —
   `docker volume ls | grep db_data` l'affiche.) Le compte administrateur doit être recréé après
   ce nettoyage : lui aussi a été effacé.

## 8. Activer HTTPS (Let's Encrypt, certbot)

Tant que ce qui suit n'est pas fait, Nginx répond en HTTP (port 80) et `SECURE_SSL_REDIRECT`
(config/settings/prod.py) redirige chaque page vers `https://…`, qui n'existe pas encore : c'est
attendu, à corriger maintenant.

1. **Obtenir un certificat** (le domaine doit déjà pointer vers ce serveur — le défi HTTP-01 le
   vérifie) :

   ```bash
   mkdir -p certs
   docker run --rm \
     -v "$(pwd)/certs:/etc/letsencrypt" \
     -v erp-densource_certbot_www:/var/www/certbot \
     certbot/certbot certonly --webroot -w /var/www/certbot \
     -d erp.densourcegroup.ci --email vous@densourcegroup.ci --agree-tos --no-eff-email
   ```

   (Remplacer le nom du volume par celui qu'affiche `docker volume ls | grep certbot_www` si le
   dossier du projet ne s'appelle pas `erp-densource`.)

2. **Ajouter le bloc HTTPS** dans `nginx/nginx.conf`, à la suite du bloc `server { listen 80; … }` :

   ```nginx
   server {
       listen 443 ssl;
       server_name erp.densourcegroup.ci;

       ssl_certificate     /etc/nginx/certs/live/erp.densourcegroup.ci/fullchain.pem;
       ssl_certificate_key /etc/nginx/certs/live/erp.densourcegroup.ci/privkey.pem;

       location /static/ { alias /app/staticfiles/; expires 30d; access_log off; }
       location /media/  { alias /app/media/;       expires 7d;  access_log off; }
       location / {
           proxy_pass http://django;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   Et changer, dans le bloc `listen 80`, la `location /` pour ne plus proxyer mais rediriger (le défi
   `/.well-known/acme-challenge/` reste, lui, en HTTP) :

   ```nginx
   location / {
       return 301 https://$host$request_uri;
   }
   ```

3. **Décommenter**, dans `docker-compose.yml`, le port `443:443` et le volume `./certs:…` du service
   `nginx`, puis :

   ```bash
   docker compose up -d
   ```

4. **Renouvellement** : les certificats Let's Encrypt expirent après 90 jours. Programmer, dans la
   crontab du serveur (`crontab -e`), un renouvellement mensuel :

   ```cron
   0 3 1 * * cd /chemin/vers/erp-densource && docker run --rm -v "$(pwd)/certs:/etc/letsencrypt" -v erp-densource_certbot_www:/var/www/certbot certbot/certbot renew --webroot -w /var/www/certbot && docker compose restart nginx
   ```

## 9. Sauvegardes chiffrées (`ops/sauvegarde.sh`)

Sauvegarde quotidienne, chiffrée avec `SAUVEGARDE_PASSPHRASE` (GPG, symétrique), à copier vers un
stockage **hors de ce serveur** (cahier-des-charges.md « sauvegardes chiffrées et testées »,
« offsite ») :

```cron
0 2 * * * cd /chemin/vers/erp-densource && set -a && . ./.env && set +a && DATABASE_URL="postgres://erp_densource:${POSTGRES_PASSWORD}@localhost:5432/erp_densource" ops/sauvegarde.sh /chemin/vers/sauvegardes
```

(`pg_dump`/`gpg` doivent être installés sur l'hôte — `apt install postgresql-client gnupg` — ou lancés
dans un conteneur éphémère `postgres:16` avec les mêmes volumes réseau.)

### Tester une restauration (mensuel)

**Jamais sur la base de production.** Créer une base à part et y restaurer la dernière sauvegarde :

```bash
docker compose exec db createdb -U erp_densource erp_densource_essai_restauration
DATABASE_URL="postgres://erp_densource:${POSTGRES_PASSWORD}@localhost:5432/erp_densource_essai_restauration" \
  ops/restauration.sh /chemin/vers/sauvegardes/<fichier>.dump.gpg
docker compose exec db dropdb -U erp_densource erp_densource_essai_restauration   # nettoyage
```

Une restauration qui échoue silencieusement est pire qu'une absence de sauvegarde : ce test mensuel
est ce qui distingue les deux.

## 10. Supervision (Sentry)

Facultatif, mais recommandé (cahier-des-charges.md « Monitoring Sentry »). Créer un projet Django
sur [sentry.io](https://sentry.io) (ou une instance auto-hébergée), copier son DSN dans `.env` :

```
SENTRY_DSN=https://…@…ingest.sentry.io/…
```

Puis `docker compose up -d` (redémarre `web`, `celery_worker`, `celery_beat` avec Sentry actif —
config/settings/prod.py). Sans `SENTRY_DSN`, rien ne change : Sentry reste inactif.

*Prometheus/Grafana* (également cité au cahier des charges) n'est volontairement pas installé : pour
un serveur unique, deux conteneurs de plus pour un tableau de bord de métriques n'apportent pas
encore assez, face à Sentry qui couvre déjà les erreurs. À ajouter si le volume le justifie.

## 11. Mettre à jour l'application

```bash
git pull
docker compose up -d --build
```

Les migrations et `collectstatic` se rejouent automatiquement au démarrage de `web`
(`ops/entrypoint.sh`) ; `celery_worker`/`celery_beat` attendent que `web` soit de nouveau en bonne
santé avant de redémarrer.

## 12. Dépannage

| Symptôme | Piste |
|---|---|
| `web` ne devient jamais « healthy » | `docker compose logs web` — souvent une variable de `.env` manquante (`SECRET_KEY`, `ALLOWED_HOSTS`…) |
| Nginx répond 502 | `web` n'a pas encore fini de démarrer, ou a planté — voir ses journaux |
| Boucle de redirection HTTPS | `X-Forwarded-Proto` n'arrive pas jusqu'à Django : vérifier que la requête passe bien par Nginx (pas directement sur le port 8000 de `web`) |
| `celery_worker` ne traite rien | `docker compose logs celery_worker` : le plus souvent `REDIS_URL` injoignable |
| Page de connexion sans styles | `collectstatic` n'a pas tourné, ou le volume `static_data` n'est pas monté dans `nginx` |

---

## Ce qui a été vérifié

Testé en local avec `docker compose up -d --build` (domaine `localhost`, sans certificat réel) :
- les 6 services démarrent et `web` devient « healthy » (migrations + `collectstatic` appliqués) ;
- la page de connexion est servie par **Nginx**, pas directement par Gunicorn (styles chargés
  depuis `/static/`, non `web:8000`) ;
- `SECURE_SSL_REDIRECT` redirige correctement en HTTP simple (pas de boucle) et laisse passer une
  requête dont `X-Forwarded-Proto` vaut `https` (simulation du TLS terminé par Nginx) ;
- `celery_worker` et `celery_beat` démarrent, se connectent à Redis et exécutent une tâche réelle ;
- une sauvegarde chiffrée (`ops/sauvegarde.sh`) puis sa restauration (`ops/restauration.sh`) dans
  une base à part ont réellement été jouées contre le PostgreSQL du `docker-compose.yml`.

Non testés ici faute de domaine réel : l'obtention d'un certificat Let's Encrypt (étape 8.1) et son
renouvellement automatique (étape 8.4) — les commandes sont standard (image officielle
`certbot/certbot`, mode webroot) mais n'ont pas pu être rejouées sans nom de domaine public.
