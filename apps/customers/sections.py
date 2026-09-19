"""Blocs ajoutés à la fiche d'un client par des apps situées « en dessous ».

``DETAIL_CLIENT`` : fournisseurs appelés avec ``(client, utilisateur)``. ``missions`` y
ajoute l'historique des missions du client.
"""

from apps.core.sections import RegistreSections

DETAIL_CLIENT = RegistreSections()
