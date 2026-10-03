#!/bin/sh
# Prépare la configuration de Nginx avant son lancement (exécuté par l'image, voir nginx/Dockerfile) :
#
# 1. écrit /etc/nginx/nginx.conf à partir du modèle (nginx/nginx.conf), en y mettant le domaine (DOMAINE) ;
# 2. choisit le certificat TLS : le vrai (Let's Encrypt, ./certs) s'il existe, sinon un certificat
#    auto-signé provisoire.
#
# Sans l'étape 2, Nginx refuse de démarrer tant que le certificat n'existe pas, et ne peut donc pas servir le
# défi HTTP-01 (port 80) dont Let's Encrypt a besoin pour le délivrer : on ne pouvait jamais l'obtenir sur un
# serveur neuf. Avec le certificat provisoire, Nginx démarre, certbot obtient le vrai certificat, et un
# `docker compose restart nginx` suffit pour l'adopter (GUIDE-DEPLOIEMENT.md § 8).
set -eu

DOMAINE="${DOMAINE:-densource.tech}"
VRAI_DOSSIER="/etc/nginx/certs/live/${DOMAINE}"
PROVISOIRE_DOSSIER="/etc/nginx/certificat-provisoire"

if [ -s "${VRAI_DOSSIER}/fullchain.pem" ] && [ -s "${VRAI_DOSSIER}/privkey.pem" ]; then
    CERTIFICAT="${VRAI_DOSSIER}/fullchain.pem"
    CLE="${VRAI_DOSSIER}/privkey.pem"
    echo "preparer-https : certificat Let's Encrypt trouvé pour ${DOMAINE}."
else
    mkdir -p "${PROVISOIRE_DOSSIER}"
    CERTIFICAT="${PROVISOIRE_DOSSIER}/fullchain.pem"
    CLE="${PROVISOIRE_DOSSIER}/privkey.pem"
    openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
        -keyout "${CLE}" -out "${CERTIFICAT}" -subj "/CN=${DOMAINE}" >/dev/null 2>&1
    echo "preparer-https : AUCUN certificat Let's Encrypt pour ${DOMAINE} dans ./certs/live/ —" \
         "certificat auto-signé provisoire utilisé (le navigateur affichera un avertissement)." \
         "Obtenez le vrai certificat puis relancez : docker compose restart nginx (GUIDE-DEPLOIEMENT.md § 8)."
fi

cat > /etc/nginx/certificat-tls.conf <<CONF
ssl_certificate     ${CERTIFICAT};
ssl_certificate_key ${CLE};
CONF

# Seul ${DOMAINE} est remplacé : les variables de Nginx ($host, $http_upgrade...) restent intactes.
envsubst '${DOMAINE}' < /etc/nginx/nginx.conf.modele > /etc/nginx/nginx.conf
