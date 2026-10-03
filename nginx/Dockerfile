# Nginx + openssl : l'image officielle n'embarque pas la commande `openssl`, dont le script de démarrage
# se sert pour fabriquer un certificat provisoire quand Let's Encrypt n'a encore rien délivré
# (voir nginx/preparer-https.sh et GUIDE-DEPLOIEMENT.md § 8).
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

# Les scripts de /docker-entrypoint.d/ s'exécutent, dans l'ordre alphabétique, avant le lancement de Nginx.
COPY preparer-https.sh /docker-entrypoint.d/10-preparer-https.sh
RUN chmod +x /docker-entrypoint.d/10-preparer-https.sh
