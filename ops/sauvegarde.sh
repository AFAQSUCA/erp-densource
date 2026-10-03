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
# La phrase de passe n'est jamais passée en argument de commande (elle serait visible de tous dans la liste des
# processus) : elle est lue depuis un fichier, soit celui de SAUVEGARDE_PASSPHRASE_FILE (à préférer), soit un
# fichier temporaire (droits 600, supprimé en sortie) fabriqué à partir de SAUVEGARDE_PASSPHRASE.
#
# Options (variables d'environnement) :
#   SAUVEGARDE_CONSERVER_JOURS   rotation : supprime les sauvegardes du dossier plus vieilles que N jours
#                                (défaut 30 ; 0 = ne rien supprimer). N'a lieu qu'après une sauvegarde réussie.
#   SAUVEGARDE_COPIE_RSYNC       copie hors serveur : destination rsync (ex. utilisateur@hôte:/chemin/) où
#                                le fichier chiffré est envoyé juste après sa création.
#
# Dans docker-compose.yml, un cron du serveur hôte peut lancer, chaque nuit :
#   docker compose exec -T db sh -c 'pg_dump "$DATABASE_URL"' | gpg ... > sauvegardes/AAAA-MM-JJ.sql.gpg
# ou, plus simple, appeler ce script directement sur l'hôte s'il a `pg_dump` et `gpg` installés et
# peut joindre le port 5432 exposé par le service `db`.
set -euo pipefail
# pipefail : sans lui, un `pg_dump` qui échoue laisserait quand même passer un fichier chiffré
# (vide ou tronqué) comme si tout s'était bien passé, `gpg` réussissant sur une entrée vide.

: "${DATABASE_URL:?DATABASE_URL doit être défini (postgres://utilisateur:motdepasse@hôte:5432/base)}"

if [ -z "${SAUVEGARDE_PASSPHRASE_FILE:-}" ]; then
    : "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE (ou SAUVEGARDE_PASSPHRASE_FILE) doit être défini : phrase de passe de chiffrement}"
    umask 077
    SAUVEGARDE_PASSPHRASE_FILE=$(mktemp)
    trap 'rm -f "$SAUVEGARDE_PASSPHRASE_FILE"' EXIT
    printf '%s' "$SAUVEGARDE_PASSPHRASE" > "$SAUVEGARDE_PASSPHRASE_FILE"
fi
CONSERVER_JOURS="${SAUVEGARDE_CONSERVER_JOURS:-30}"

DESTINATION="${1:-.}"
HORODATAGE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
FICHIER="$DESTINATION/erp_densource_$HORODATAGE.dump.gpg"

mkdir -p "$DESTINATION"

echo "Sauvegarde de la base vers $FICHIER"
pg_dump --format=custom "$DATABASE_URL" \
    | gpg --batch --yes --symmetric --cipher-algo AES256 --pinentry-mode loopback \
        --passphrase-file "$SAUVEGARDE_PASSPHRASE_FILE" \
    > "$FICHIER"

echo "Empreinte SHA-256 (à noter pour vérifier l'intégrité avant restauration) :"
sha256sum "$FICHIER"

echo "OK : $(du -h "$FICHIER" | cut -f1)"

if [ -n "${SAUVEGARDE_COPIE_RSYNC:-}" ]; then
    echo "Copie hors serveur vers $SAUVEGARDE_COPIE_RSYNC"
    rsync -a "$FICHIER" "$SAUVEGARDE_COPIE_RSYNC"
fi

if [ "$CONSERVER_JOURS" -gt 0 ]; then
    # Rotation : seulement les sauvegardes de ce script (même préfixe), seulement après une réussite.
    find "$DESTINATION" -maxdepth 1 -name 'erp_densource_*.dump.gpg' -mtime +"$CONSERVER_JOURS" -print -delete
fi
