"""WebSocket du suivi des missions : pousse au navigateur chaque changement d'une mission.

Seuls les rôles qui consultent les missions (``permissions.CONSULTATION``) peuvent se connecter, avec
les mêmes garanties que les pages HTTP : session authentifiée, compte actif, et double authentification
vérifiée pour l'ADMIN et la DIRECTION (le middleware MFA n'agit que sur les requêtes HTTP : sans ce
contrôle, une session « mot de passe seul » pourrait suivre les missions par WebSocket). Le chauffeur
n'a pas accès à ces écrans, donc pas non plus à ce flux.

L'origine de la page est contrôlée en amont (``config/asgi.py``, AllowedHostsOriginValidator).
"""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts import mfa

from . import permissions
from .temps_reel import GROUPE_SUIVI

CODE_REFUSE = 4403  # « interdit », dans la plage réservée aux applications


def est_autorise(scope) -> bool:
    utilisateur = scope.get("user")
    if utilisateur is None or not utilisateur.is_authenticated or not utilisateur.is_active:
        return False
    if utilisateur.role_effectif not in permissions.CONSULTATION:
        return False
    session = scope.get("session")
    if mfa.mfa_requise(utilisateur) and not (session is not None and session.get(mfa.CLE_SESSION)):
        return False
    return True


class MissionSuiviConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not est_autorise(self.scope):
            await self.close(code=CODE_REFUSE)  # avant accept() : la connexion est refusée (HTTP 403)
            return
        await self.channel_layer.group_add(GROUPE_SUIVI, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUPE_SUIVI, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Le navigateur n'envoie rien d'utile : ce flux est en sens unique."""

    async def mission_maj(self, evenement):
        await self.send_json(evenement["donnees"])
