"""Couverture du journal d'audit (audit M1-67, M1-68) : chaque modèle sensible est tracé."""

from datetime import date

import pytest
from django.apps import apps
from django.db.models.signals import post_save

from apps.audit.models import ActionChoices, AuditLog
from apps.fuel.tests.factories import PleinFactory
from apps.hr.models import JourFerie
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

MODELES_SENSIBLES = (
    # Ajoutés par l'audit M1-67 / M1-68.
    "inventory.Article",
    "fuel.Plein",
    "billing.LigneFacture",
    "hr.ReportConge",
    "hr.ValidationConge",
    "hr.JourFerie",
    "customers.Interaction",
    "garage.ChecklistVehicule",
    # Déjà tracés : la liste sert aussi de garde-fou contre un retrait par erreur.
    "accounts.User",
    "hr.Personnel",
    "hr.Conge",
    "hr.SortiePersonnel",
    "customers.Client",
    "fleet.Vehicule",
    "fleet.DocumentReglementaire",
    "drivers.Chauffeur",
    "missions.Mission",
    "garage.OrdreReparation",
    "billing.Facture",
    "billing.Reglement",
    "billing.Depense",
    "parametres.Parametres",
)


def _audite(label: str) -> bool:
    # Chaque entrée : (clé de connexion = (dispatch_uid, émetteur), récepteur, asynchrone).
    return any(entree[0][0] == f"audit-post-{label}" for entree in post_save.receivers)


@pytest.mark.parametrize("label", MODELES_SENSIBLES)
def test_chaque_modele_sensible_est_trace(label):
    apps.get_model(label)  # le modèle existe
    assert _audite(label), f"{label} n'est pas enregistré au journal d'audit (audit_model)"


def test_la_modification_d_un_seuil_d_article_est_tracee():
    article = ArticleFactory(seuil_minimal=5)

    article.seuil_minimal = 2
    article.save()

    entree = AuditLog.objects.filter(entite="Article", entite_id=article.pk, action=ActionChoices.UPDATE).get()
    assert entree.ancienne_valeur["seuil_minimal"] == 5 and entree.nouvelle_valeur["seuil_minimal"] == 2


def test_un_plein_est_trace():
    plein = PleinFactory()

    assert AuditLog.objects.filter(entite="Plein", entite_id=plein.pk, action=ActionChoices.CREATE).exists()


def test_un_jour_ferie_est_trace():
    jour = JourFerie.objects.create(date=date(2026, 12, 25), libelle="Noël")

    assert AuditLog.objects.filter(entite="JourFerie", entite_id=jour.pk, module="RH").exists()
