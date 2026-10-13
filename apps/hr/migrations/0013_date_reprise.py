"""Report de congé : le champ porte le jour de reprise du travail (décision du 13/10/2026, audit AV-01).

Renommage seul : les reports déjà enregistrés gardent leur date. Avant ce lot, elle était traitée comme le dernier jour
de congé ; les écrans, le PDF et les notifications l'affichaient déjà comme la date de reprise.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("hr", "0012_validation_conge_auto")]

    operations = [
        migrations.RenameField(model_name="reportconge", old_name="nouvelle_date_fin", new_name="date_reprise"),
        migrations.AlterField(
            model_name="reportconge", name="date_reprise", field=models.DateField(verbose_name="reprise du travail le"),
        ),
    ]
