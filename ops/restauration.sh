#!/bin/bash
# Restaure une sauvegarde chiffrée (ops/sauvegarde.sh) dans une base — pour l'essai mensuel exigé par
# le cahier des charges (« sauvegardes chiffrées et testées ») autant que pour un vrai incident.
#
# Usage :
#   DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/restauration.sh fichier.dump.gpg
#
# ATTENTION : restaure dans la base de DATABASE_URL, en écrasant son contenu (--clean). Pour l'essai
# mensuel, pointez DATABASE_URL vers une base à part (jamais la base de production) — voir
# GUIDE-DEPLOIEMENT.md « Tester une restauration ».
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL doit être défini (la base à restaurer, jamais la production pour un essai)}"
: "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE doit être défini (phrase de passe de chiffrement)}"

FICHIER="${1:?Usage : ops/restauration.sh fichier.dump.gpg}"

echo "Restauration de $FICHIER vers $(echo "$DATABASE_URL" | sed -E 's#//[^@]+@#//***@#')"
gpg --batch --yes --decrypt --passphrase "$SAUVEGARDE_PASSPHRASE" "$FICHIER" \
    | pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL"

echo "OK : restauration terminée."
