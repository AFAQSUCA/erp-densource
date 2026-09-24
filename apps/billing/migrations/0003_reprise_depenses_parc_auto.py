"""Reprise de l'existant : chaque plein, achat de pièces et OR clôturé (main-d'œuvre) déjà enregistré devient une
dépense automatique, comme ceux d'aujourd'hui (``finance.receivers``). Mode de paiement : espèces, que la Finance
peut corriger. Rejouable sans doublon (une seule dépense par source)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations
from django.utils import timezone

CENTIME = Decimal("0.01")


def _creer(Depense, *, origine, origine_id, **champs):
    montant = Decimal(champs["montant"]).quantize(CENTIME, rounding=ROUND_HALF_UP)
    if montant <= 0:
        return
    Depense.objects.get_or_create(
        origine=origine,
        origine_id=origine_id,
        defaults={**champs, "montant": montant, "mode": "ESPECES", "libelle": champs["libelle"][:200]},
    )


def reprendre(apps, schema_editor):
    Depense = apps.get_model("billing", "Depense")
    Plein = apps.get_model("fuel", "Plein")
    Mouvement = apps.get_model("inventory", "MouvementStock")
    Ordre = apps.get_model("garage", "OrdreReparation")

    for plein in Plein.objects.filter(is_deleted=False).select_related("vehicule"):
        _creer(
            Depense, origine="PLEIN", origine_id=plein.pk, categorie="CARBURANT",
            date_depense=plein.date_plein,
            libelle=f"Carburant · {plein.vehicule.immatriculation} · {plein.station} ({plein.quantite_litres.normalize():f} L)",
            montant=plein.quantite_litres * plein.prix_unitaire, reference=plein.numero_ticket[:100],
        )
    for m in Mouvement.objects.filter(type_mouvement="ENTREE").select_related("article"):
        _creer(
            Depense, origine="ACHAT_STOCK", origine_id=m.pk, categorie="PIECES",
            date_depense=timezone.localtime(m.date_mouvement).date(),
            libelle=f"Achat de pièces · {m.article.designation} ({m.article.reference}) × {m.variation}",
            montant=m.variation * m.prix_unitaire, reference="",
        )
    for ordre in Ordre.objects.filter(is_deleted=False, statut="CLOTURE").select_related("vehicule"):
        _creer(
            Depense, origine="MAIN_OEUVRE_OR", origine_id=ordre.pk, categorie="MAINTENANCE",
            date_depense=timezone.localtime(ordre.date_cloture).date(),
            libelle=f"Main-d'œuvre · {ordre.numero} · {ordre.vehicule.immatriculation}",
            montant=ordre.cout_main_oeuvre, reference=ordre.numero,
        )


def annuler(apps, schema_editor):
    apps.get_model("billing", "Depense").objects.exclude(origine="").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_depenses_automatiques_parc_auto"),
        ("fuel", "0001_initial"),
        ("inventory", "0001_initial"),
        ("garage", "0002_incidents_checklists"),
    ]

    operations = [migrations.RunPython(reprendre, annuler)]
