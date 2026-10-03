from django.db import migrations

from apps.core.immuable import poser_triggers, retirer_triggers

TABLE = "inventory_mouvementstock"


def poser(apps, schema_editor):
    poser_triggers(schema_editor, TABLE)


def retirer(apps, schema_editor):
    retirer_triggers(schema_editor, TABLE)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(poser, retirer)]
