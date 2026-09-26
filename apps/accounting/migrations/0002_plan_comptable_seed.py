"""Plan comptable de départ (SYSCOHADA révisé) — liste de travail, à valider par un
expert-comptable avant mise en production (voir apps/accounting/README.md et
avenant-comptabilite-syscohada.md). Seuls 411000, 706100, 443300 et les 3 comptes de trésorerie
sont mobilisés par le code de la Phase 1 ; le reste est seedé pour ne pas fragmenter la migration
de données quand les lots suivants (dépenses automatiques, saisie manuelle) arriveront.

``RunPython`` idempotent (``update_or_create``) : rejouable sans effet si déjà appliquée.
"""

from django.db import migrations

PLAN_COMPTABLE = [
    ("101000", "Capital social", "PASSIF"),
    ("108000", "Compte de l'exploitant", "PASSIF"),
    ("120000", "Résultat de l'exercice", "PASSIF"),
    ("401000", "Fournisseurs", "PASSIF"),
    ("411000", "Clients", "ACTIF"),
    ("443300", "État, TVA facturée sur ventes", "PASSIF"),
    ("445200", "État, TVA déductible", "ACTIF"),
    ("521000", "Banque", "ACTIF"),
    ("521900", "Mobile Money", "ACTIF"),
    ("571000", "Caisse", "ACTIF"),
    ("605100", "Carburants et lubrifiants", "CHARGE"),
    ("605800", "Pièces détachées et fournitures véhicules", "CHARGE"),
    ("624100", "Entretien, réparations (prestataires extérieurs)", "CHARGE"),
    ("628100", "Frais de mission et déplacements", "CHARGE"),
    ("631000", "Frais bancaires", "CHARGE"),
    ("658000", "Charges diverses de gestion courante", "CHARGE"),
    ("706100", "Prestations de transport", "PRODUIT"),
]


def seeder(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    for numero, libelle, nature in PLAN_COMPTABLE:
        Compte.objects.update_or_create(numero=numero, defaults={"libelle": libelle, "nature": nature})


def retirer(apps, schema_editor):
    Compte = apps.get_model("accounting", "Compte")
    Compte.objects.filter(numero__in=[numero for numero, _, _ in PLAN_COMPTABLE]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seeder, retirer),
    ]
