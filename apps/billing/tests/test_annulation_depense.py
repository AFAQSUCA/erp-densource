"""Annuler une dépense saisie à la main — décision du 13/10/2026, audit AV-12.

Par ceux qui saisissent les dépenses (Finance, RH, Direction, administrateur), avec un motif ; l'écriture est
contre-passée et le pointage bancaire défait, comme pour un règlement. Une dépense automatique (plein, achat, OR)
s'annule avec son opération d'origine, pas ici.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.models import EcritureComptable
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import finances

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 10)


def _peage(montant="5000"):
    return services.enregistrer_depense(
        finances(), categorie=CategorieDepense.PEAGES, date_depense=JOUR, libelle="Péage Yamoussoukro",
        montant=Decimal(montant), mode=ModePaiement.ESPECES,
    )


def test_annuler_une_depense_manuelle_contre_passe_son_ecriture():
    depense = _peage()

    services.annuler_depense(depense, finances(), motif="Saisie en double")

    depense = Depense.all_objects.get(pk=depense.pk)
    assert depense.is_deleted and depense.motif_annulation == "Saisie en double"
    assert services.total_depenses(JOUR, JOUR) == 0
    assert EcritureComptable.objects.filter(origine="CONTRE_PASSATION").count() == 1


@pytest.mark.parametrize("role", [Role.FINANCES, Role.RH, Role.DIRECTION, Role.ADMIN])
def test_ceux_qui_saisissent_annulent(role):
    depense = _peage()

    services.annuler_depense(depense, UserFactory(role=role), motif="Erreur")

    assert not Depense.objects.filter(pk=depense.pk).exists()


def test_les_autres_roles_le_motif_vide_et_les_depenses_automatiques_sont_refuses():
    depense = _peage()
    automatique = Depense.objects.create(
        categorie=CategorieDepense.CARBURANT, date_depense=JOUR, libelle="Carburant", montant=Decimal("6000"),
        mode=ModePaiement.ESPECES, origine=OrigineDepense.PLEIN, origine_id=1,
    )

    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_depense(depense, UserFactory(role=Role.PARCAUTO), motif="Erreur")
    with pytest.raises(MontantInvalide, match="motif"):
        services.annuler_depense(depense, finances(), motif="  ")
    with pytest.raises(ActionFactureNonAutorisee, match="opération d'origine"):
        services.annuler_depense(automatique, finances(), motif="Erreur")

    assert Depense.objects.filter(pk__in=[depense.pk, automatique.pk]).count() == 2


def test_l_ecran_annule_une_depense_manuelle_avec_un_motif(client):
    depense = _peage()
    client.force_login(finances())

    assert reverse("billing:depense_annuler", args=[depense.pk]) in client.get(reverse("billing:depenses")).content.decode()
    reponse = client.post(reverse("billing:depense_annuler", args=[depense.pk]), {"motif": "Saisie en double"}, follow=True)

    assert any("annulée" in str(m) for m in reponse.context["messages"])
    assert not Depense.objects.filter(pk=depense.pk).exists()
