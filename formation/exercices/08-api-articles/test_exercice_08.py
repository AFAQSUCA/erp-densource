"""Exercice 8 — Le stock de pièces dans l'API, en lecture seule (formation/exercices/08-api-articles).

À copier dans apps/api/tests/ puis : python -m pytest apps/api/tests/test_exercice_08.py -q --no-cov
"""

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.inventory.models import Article

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _api(role):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    return client


def _article(**champs):
    valeurs = dict(reference="FLT-001", designation="Filtre à huile", categorie="Filtres", quantite=12,
                   seuil_minimal=5, pump=Decimal("8500"))
    valeurs.update(champs)
    return Article.objects.create(**valeurs)


@pytest.mark.parametrize("role", list(Role.values))
def test_seuls_les_roles_du_stock_lisent_les_articles(role):
    attendu = 200 if role in {Role.ADMIN, Role.DIRECTION, Role.PARCAUTO} else 403

    assert _api(role).get(reverse("api:article-list")).status_code == attendu


def test_la_liste_expose_les_champs_utiles_et_se_pagine():
    _article()

    reponse = _api(Role.PARCAUTO).get(reverse("api:article-list")).json()

    assert reponse["count"] == 1
    article = reponse["results"][0]
    assert set(article) == {"id", "reference", "designation", "categorie", "quantite", "seuil_minimal", "pump", "sous_seuil"}
    assert article["sous_seuil"] is False


def test_un_article_sous_le_seuil_est_signale_et_filtrable():
    _article()
    _article(reference="PLQ-002", designation="Plaquettes de frein", quantite=2)

    api = _api(Role.PARCAUTO)
    sous_seuil = api.get(reverse("api:article-list"), {"alerte": "1"}).json()["results"]

    assert [a["reference"] for a in sous_seuil] == ["PLQ-002"] and sous_seuil[0]["sous_seuil"] is True
    assert api.get(reverse("api:article-list"), {"q": "plaquette"}).json()["count"] == 1


def test_l_api_ne_modifie_rien():
    article = _article()
    api = _api(Role.ADMIN)

    assert api.post(reverse("api:article-list"), {"reference": "X"}).status_code == 405
    assert api.delete(reverse("api:article-detail", args=[article.pk])).status_code == 405
