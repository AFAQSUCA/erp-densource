"""Audit M1-05 / M8-06 : le journal d'audit et le journal des mouvements de stock refusent aussi les
modifications et suppressions en masse (``QuerySet``), pas seulement celles d'une instance."""

import pytest

from apps.audit.models import ActionChoices, AuditLog
from apps.inventory.models import MouvementStock
from apps.inventory.tests.factories import ArticleFactory
from apps.inventory import services as stock
from decimal import Decimal

pytestmark = pytest.mark.django_db


def _entree():
    return AuditLog.objects.create(action=ActionChoices.UPDATE, module="FLEET", entite="Vehicule", entite_id=1)


def test_le_journal_d_audit_refuse_update_et_delete_en_masse():
    _entree()

    with pytest.raises(ValueError, match="append-only"):
        AuditLog.objects.filter(module="FLEET").update(module="X")
    with pytest.raises(ValueError, match="append-only"):
        AuditLog.objects.all().delete()
    with pytest.raises(ValueError, match="append-only"):
        AuditLog.objects.bulk_update([_entree()], ["module"])

    assert AuditLog.objects.filter(module="FLEET").count() == 2


def test_le_journal_d_audit_reste_ecrivable_et_lisible():
    entree = _entree()

    assert AuditLog.objects.get(pk=entree.pk).module == "FLEET"
    assert AuditLog.objects.filter(action=ActionChoices.UPDATE).exists()


def test_le_journal_des_mouvements_de_stock_refuse_update_et_delete_en_masse():
    article = ArticleFactory()
    stock.enregistrer_entree(article, quantite=5, prix_unitaire=Decimal("1000"))

    with pytest.raises(ValueError, match="append-only"):
        MouvementStock.objects.update(variation=99)
    with pytest.raises(ValueError, match="append-only"):
        MouvementStock.objects.all().delete()

    assert MouvementStock.objects.count() == 1
