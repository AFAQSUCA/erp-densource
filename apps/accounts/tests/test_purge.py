"""Purge quotidienne des sessions et des jetons API expirés — audit AUD-19."""

from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.tests.factories import UserFactory
from apps.notifications.taches import executer_taches_quotidiennes

pytestmark = pytest.mark.django_db


def _session(expire_dans):
    session = SessionStore()
    session["x"] = 1
    session.create()
    Session.objects.filter(session_key=session.session_key).update(expire_date=timezone.now() + expire_dans)
    return session.session_key


def test_les_sessions_et_jetons_expires_sont_purges_et_les_autres_gardes():
    perimee, valide = _session(timedelta(minutes=-1)), _session(timedelta(minutes=30))
    utilisateur = UserFactory()
    ancien, recent = RefreshToken.for_user(utilisateur), RefreshToken.for_user(utilisateur)
    ancien.blacklist()
    OutstandingToken.objects.filter(jti=ancien["jti"]).update(expires_at=timezone.now() - timedelta(days=1))

    resultat = services.purger_sessions_et_jetons_expires()

    assert resultat == {"sessions": 1, "jetons": 1}
    assert set(Session.objects.values_list("session_key", flat=True)) == {valide}
    assert list(OutstandingToken.objects.values_list("jti", flat=True)) == [recent["jti"]]
    assert not BlacklistedToken.objects.exists()
    assert perimee


def test_la_tache_quotidienne_lance_la_purge():
    _session(timedelta(minutes=-1))

    resultat = executer_taches_quotidiennes()

    assert resultat["sessions_purgees"] == 1 and "jetons_purges" in resultat
