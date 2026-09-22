#!/bin/bash
# Sauvegarde chiffrée de la base (cahier-des-charges.md:282 « Sauvegardes chiffrées et testées »).
#
# `pg_dump` (format personnalisé, compressé) chiffré au repos avec GPG (symétrique : une phrase de
# passe partagée, pas de gestion de clés). Le fichier produit ne sert à rien sans elle — à conserver
# hors du serveur (cahier-des-charges.md:294 « offsite »), par exemple copiée chaque nuit vers un
# stockage distinct.
#
# Usage :
#   DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/sauvegarde.sh [dossier de destination]
#
# Dans docker-compose.yml, un cron du serveur hôte peut lancer, chaque nuit :
#   docker compose exec -T db sh -c 'pg_dump "$DATABASE_URL"' | gpg ... > sauvegardes/AAAA-MM-JJ.sql.gpg
# ou, plus simple, appeler ce script directement sur l'hôte s'il a `pg_dump` et `gpg` installés et
# peut joindre le port 5432 exposé par le service `db`.
set -euo pipefail
# pipefail : sans lui, un `pg_dump` qui échoue laisserait quand même passer un fichier chiffré
# (vide ou tronqué) comme si tout s'était bien passé, `gpg` réussissant sur une entrée vide.

: "${DATABASE_URL:?DATABASE_URL doit être défini (postgres://utilisateur:motdepasse@hôte:5432/base)}"
: "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE doit être défini (phrase de passe de chiffrement)}"

DESTINATION="${1:-.}"
HORODATAGE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
FICHIER="$DESTINATION/erp_densource_$HORODATAGE.dump.gpg"

mkdir -p "$DESTINATION"

echo "Sauvegarde de la base vers $FICHIER"
pg_dump --format=custom "$DATABASE_URL" \
    | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$SAUVEGARDE_PASSPHRASE" \
    > "$FICHIER"

echo "Empreinte SHA-256 (à noter pour vérifier l'intégrité avant restauration) :"
sha256sum "$FICHIER"

echo "OK : $(du -h "$FICHIER" | cut -f1)"
