"""Suivi des missions en direct : qui peut se connecter, ce qui est poussé, et ce qui ne casse jamais."""

import asyncio
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from channels.layers import channel_layers
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.accounts import mfa
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import temps_reel
from apps.missions.consumers import MissionSuiviConsumer, est_autorise

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def couche_neuve():
    """Une couche de messages vierge par test (elle est mise en mémoire, donc partagée sinon)."""
    channel_layers.backends = {}


def _communicateur(utilisateur, session=None):
    communicateur = WebsocketCommunicator(MissionSuiviConsumer.as_asgi(), "/ws/missions/suivi/")
    communicateur.scope["user"] = utilisateur
    communicateur.scope["session"] = session if session is not None else {}
    return communicateur


def _se_connecte(utilisateur, session=None) -> bool:
    async def scenario():
        communicateur = _communicateur(utilisateur, session)
        connecte, _ = await communicateur.connect()
        if connecte:
            await communicateur.disconnect()
        return connecte

    return asyncio.run(scenario())


# --- qui peut se connecter ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_roles_qui_consultent_les_missions_se_connectent(role):
    assert _se_connecte(UserFactory.build(role=role)) is True


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.RH, Role.PARCAUTO, Role.FINANCES])
def test_les_autres_roles_sont_refuses(role):
    assert _se_connecte(UserFactory.build(role=role)) is False


def test_un_visiteur_non_connecte_est_refuse():
    assert _se_connecte(AnonymousUser()) is False


def test_un_compte_desactive_est_refuse():
    assert _se_connecte(UserFactory.build(role=Role.ADMIN, is_active=False)) is False


def test_sans_double_authentification_verifiee_un_admin_est_refuse(settings):
    """Le middleware MFA ne voit que le HTTP : la WebSocket refait ce contrôle elle-même."""
    settings.MFA_ENFORCED = True
    admin = UserFactory.build(role=Role.ADMIN)

    assert _se_connecte(admin, session={}) is False
    assert _se_connecte(admin, session={mfa.CLE_SESSION: True}) is True


def test_le_charge_clientele_n_a_pas_besoin_de_la_mfa(settings):
    settings.MFA_ENFORCED = True

    assert _se_connecte(UserFactory.build(role=Role.CHARGE_CLIENTELE), session={}) is True


def test_est_autorise_sans_session_refuse_un_role_soumis_a_la_mfa(settings):
    settings.MFA_ENFORCED = True
    scope = {"user": SimpleNamespace(is_authenticated=True, is_active=True, role_effectif=Role.DIRECTION)}

    assert est_autorise(scope) is False


# --- ce qui est poussé ---


def test_un_changement_de_mission_est_pousse_aux_ecrans_connectes():
    mission = MissionFactory(numero="MIS-2026-0077")

    async def scenario():
        communicateur = _communicateur(UserFactory.build(role=Role.DIRECTION))
        await communicateur.connect()
        await sync_to_async(temps_reel.diffuser)(mission)
        recu = await communicateur.receive_json_from()
        await communicateur.disconnect()
        return recu

    recu = asyncio.run(scenario())

    assert recu == {"id": mission.pk, "numero": "MIS-2026-0077", "statut": "BROUILLON", "statut_libelle": "Brouillon"}


def test_le_message_ne_contient_aucun_code_secret():
    mission = MissionFactory()

    contenu = str(temps_reel.message_mission(mission))

    assert mission.code_expediteur not in contenu and mission.code_destinataire not in contenu


def test_un_ecran_deconnecte_ne_recoit_plus_rien():
    async def scenario():
        communicateur = _communicateur(UserFactory.build(role=Role.ADMIN))
        await communicateur.connect()
        await communicateur.disconnect()
        await sync_to_async(temps_reel.diffuser)(MissionFactory.build(pk=1, numero="MIS-2026-0001"))
        return await communicateur.receive_nothing()

    assert asyncio.run(scenario()) is True


# --- diffusion depuis le métier ---


def test_enregistrer_une_mission_la_diffuse_apres_la_validation(monkeypatch, django_capture_on_commit_callbacks):
    diffusees = []
    monkeypatch.setattr(temps_reel, "diffuser", lambda mission: diffusees.append(mission.numero))

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        mission = MissionFactory(numero="MIS-2026-0088")

    assert diffusees == []  # rien n'est parti avant la validation de la transaction
    for callback in callbacks:
        callback()
    assert diffusees == [mission.numero]


def test_une_couche_de_messages_en_panne_ne_fait_pas_echouer_le_metier(monkeypatch, caplog):
    class CoucheCassee:
        async def group_send(self, *args, **kwargs):
            raise ConnectionError("Redis injoignable")

    monkeypatch.setattr(temps_reel, "get_channel_layer", lambda: CoucheCassee())

    temps_reel.diffuser(MissionFactory.build(pk=5, numero="MIS-2026-0005"))  # ne lève rien

    assert "Diffusion du suivi de la mission 5 impossible" in caplog.text
