#!/bin/sh
# Rafraîchit nginx/cloudflare-ips.conf depuis la liste officielle de Cloudflare (audit TECH-71).
#
# Usage, depuis la racine du projet sur le serveur :
#     sh nginx/maj-ips-cloudflare.sh
#     docker compose up -d --build nginx
#
# Le fichier n'est remplacé que si les deux listes ont bien été téléchargées et ne contiennent que des plages
# d'adresses : une coupure réseau ne peut pas laisser Nginx sans liste (ou avec une page d'erreur à la place).
set -eu

DOSSIER="$(dirname "$0")"
CIBLE="${DOSSIER}/cloudflare-ips.conf"
TEMP="$(mktemp)"
trap 'rm -f "${TEMP}" "${TEMP}.v4" "${TEMP}.v6"' EXIT

curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4 -o "${TEMP}.v4"
curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 -o "${TEMP}.v6"

for liste in "${TEMP}.v4" "${TEMP}.v6"; do
    if [ ! -s "${liste}" ] || grep -qvE '^[0-9a-fA-F.:]+/[0-9]+$' "${liste}"; then
        echo "maj-ips-cloudflare : liste inattendue (${liste}), fichier inchangé." >&2
        exit 1
    fi
done

{
    # On garde l'en-tête explicatif du fichier actuel (tout ce qui précède « # IPv4 »).
    sed '/^# IPv4$/,$d' "${CIBLE}" | sed "s|(relevée le [0-9/]*)|(relevée le $(date +%d/%m/%Y))|"
    echo "# IPv4"
    awk '{ print "set_real_ip_from " $0 ";" }' "${TEMP}.v4"  # awk : même sans saut de ligne final
    echo
    echo "# IPv6"
    awk '{ print "set_real_ip_from " $0 ";" }' "${TEMP}.v6"
    echo
    echo "real_ip_header CF-Connecting-IP;"
} > "${TEMP}"

mv "${TEMP}" "${CIBLE}"
trap - EXIT
rm -f "${TEMP}.v4" "${TEMP}.v6"
echo "maj-ips-cloudflare : ${CIBLE} mis à jour. Relancez : docker compose up -d --build nginx"
