#!/bin/bash
# Restaure une sauvegarde chiffrée (ops/sauvegarde.sh) — pour l'essai mensuel exigé par le cahier des charges
# (« sauvegardes chiffrées et testées ») autant que pour un vrai incident.
#
# Usage :
#   Base :     DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/restauration.sh erp_densource_<date>.dump.gpg
#   Fichiers : RESTAURATION_MEDIAS=/dossier SAUVEGARDE_PASSPHRASE=... ops/restauration.sh erp_densource_medias_<date>.tar.gz.gpg
#   (ou SAUVEGARDE_PASSPHRASE_FILE=/chemin/fichier ; aucun secret n'est passé en argument de commande, visible de
#   tous dans la liste des processus : ops/fonctions-sauvegarde.sh)
#
# ATTENTION : une base est restaurée dans celle de DATABASE_URL en écrasant son contenu (--clean) ; des fichiers
# sont extraits dans RESTAURATION_MEDIAS en remplaçant ceux du même nom. Pour l'essai mensuel, pointez vers une
# base et un dossier à part (jamais ceux de la production) — voir GUIDE-DEPLOIEMENT.md « Tester une restauration ».
set -euo pipefail

. "$(dirname "$0")/fonctions-sauvegarde.sh"
trap supprimer_temporaires EXIT

FICHIER="${1:?Usage : ops/restauration.sh fichier.dump.gpg (base) ou fichier.tar.gz.gpg (fichiers déposés)}"
preparer_phrase_de_passe

dechiffrer() {
    gpg --batch --yes --decrypt --pinentry-mode loopback --passphrase-file "$SAUVEGARDE_PASSPHRASE_FILE" "$FICHIER"
}

case "$FICHIER" in
    *.tar.gz.gpg)
        : "${RESTAURATION_MEDIAS:?RESTAURATION_MEDIAS doit indiquer le dossier où extraire les fichiers (jamais celui de la production pour un essai)}"
        echo "Restauration des fichiers de $FICHIER vers $RESTAURATION_MEDIAS"
        mkdir -p "$RESTAURATION_MEDIAS"
        dechiffrer | tar -C "$RESTAURATION_MEDIAS" -xzf -
        echo "OK : $(find "$RESTAURATION_MEDIAS" -type f | wc -l) fichier(s) restauré(s)."
        ;;
    *)
        : "${DATABASE_URL:?DATABASE_URL doit être défini (la base à restaurer, jamais la production pour un essai)}"
        preparer_connexion "$DATABASE_URL"
        echo "Restauration de $FICHIER vers $(echo "$URL_SANS_MOT_DE_PASSE" | sed -E 's#//[^@]+@#//***@#')"
        dechiffrer | pg_restore --clean --if-exists --no-owner --dbname "$URL_SANS_MOT_DE_PASSE"
        echo "OK : restauration terminée."
        ;;
esac
