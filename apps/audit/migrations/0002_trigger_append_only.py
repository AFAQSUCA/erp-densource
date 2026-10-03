from django.db import migrations

from apps.core.immuable import poser_triggers, retirer_triggers

TABLE = "audit_log"


def poser(apps, schema_editor):
    # Seul détachement toléré : ``utilisateur_id`` -> NULL (``on_delete=SET_NULL``), le nom reste dénormalisé.
    poser_triggers(schema_editor, TABLE, tolere_detachement_utilisateur=True)


def retirer(apps, schema_editor):
    retirer_triggers(schema_editor, TABLE)


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunPython(poser, retirer)]
