"""Tests du mixin BaseModel — conventions.md §7.

BaseModel est abstrait et n'a pas encore de modèle concret réel (arrivera
avec fleet/hr à l'étape 2). On le teste via un modèle jetable créé pour la
durée du test (``isolate_apps`` + ``schema_editor``), pattern recommandé
par Django pour tester des mixins de modèles.
"""

from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps

from apps.core.models import BaseModel


@isolate_apps("apps.core")
class BaseModelSoftDeleteTests(TransactionTestCase):
    """TransactionTestCase (pas TestCase) : la création de table via
    schema_editor est incompatible avec le bloc atomic ouvert par
    TestCase.setUpClass sous SQLite."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class Gadget(BaseModel):
            nom = models.CharField(max_length=50)

            class Meta:
                app_label = "core"

        cls.Gadget = Gadget
        with connection.schema_editor() as editor:
            editor.create_model(cls.Gadget)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.Gadget)
        super().tearDownClass()

    def test_default_manager_excludes_soft_deleted_records(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        gadget.delete()

        self.assertEqual(self.Gadget.objects.count(), 0)
        self.assertEqual(self.Gadget.all_objects.count(), 1)

    def test_delete_sets_soft_delete_fields_without_removing_row(self):
        gadget = self.Gadget.objects.create(nom="Pneu")

        gadget.delete()
        gadget.refresh_from_db()

        self.assertTrue(gadget.is_deleted)
        self.assertIsNotNone(gadget.deleted_at)

    def test_hard_delete_removes_row_physically(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        pk = gadget.pk

        gadget.hard_delete()

        self.assertFalse(self.Gadget.all_objects.filter(pk=pk).exists())

    def test_restore_clears_soft_delete_fields(self):
        gadget = self.Gadget.objects.create(nom="Pneu")
        gadget.delete()

        gadget.restore()

        self.assertTrue(self.Gadget.objects.filter(pk=gadget.pk).exists())
        self.assertFalse(self.Gadget.objects.get(pk=gadget.pk).is_deleted)
