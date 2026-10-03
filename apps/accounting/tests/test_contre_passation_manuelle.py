"""Corriger une opération diverse validée : contre-passation depuis l'écran, DIRECTION seulement, motif obligatoire."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.exceptions import ActionComptableNonAutorisee, ContrePassationImpossible
from apps.accounting.models import EcritureComptable, SensEcriture, StatutEcriture
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

pytestmark = pytest.mark.django_db


def _od_validee():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Apport")
    services.ajouter_ligne_manuelle(ecriture, finances(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    services.ajouter_ligne_manuelle(ecriture, finances(), compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))
    return services.valider_ecriture_manuelle(ecriture, direction())


def test_la_direction_contre_passe_une_operation_diverse_validee():
    ecriture = _od_validee()

    inverse = services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Montant erroné")

    assert inverse.statut == StatutEcriture.VALIDEE
    assert services.contre_passation_de(ecriture) == inverse
    sens = {(l.compte.numero, l.sens) for l in inverse.lignes.select_related("compte")}
    assert sens == {("571000", SensEcriture.CREDIT), ("101000", SensEcriture.DEBIT)}
    assert "Montant erroné" in inverse.libelle


def test_la_contre_passation_est_reservee_a_la_direction_en_controle_strict():
    ecriture = _od_validee()

    for acteur in (finances(), UserFactory(role=Role.ADMIN, is_superuser=True)):
        with pytest.raises(ActionComptableNonAutorisee):
            services.contre_passer_ecriture_manuelle(ecriture, acteur, motif="Test")


def test_le_motif_est_obligatoire():
    with pytest.raises(ContrePassationImpossible, match="motif"):
        services.contre_passer_ecriture_manuelle(_od_validee(), direction(), motif="   ")


def test_une_ecriture_deja_contre_passee_ne_l_est_pas_deux_fois():
    ecriture = _od_validee()
    services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Erreur")

    with pytest.raises(ContrePassationImpossible, match="déjà contre-passée"):
        services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Encore")

    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CONTRE_PASSATION).count() == 1


def test_une_ecriture_automatique_ne_se_contre_passe_pas_par_cette_voie():
    automatique = services.passer_ecriture(
        journal="OD", date_ecriture=date(2026, 3, 1), libelle="Auto", origine="MOUVEMENT", origine_id=1,
        lignes=[
            services.LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("10")),
            services.LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("10")),
        ],
    )

    with pytest.raises(ContrePassationImpossible, match="à la source"):
        services.contre_passer_ecriture_manuelle(automatique, direction(), motif="Test")


def test_un_brouillon_ne_se_contre_passe_pas():
    brouillon = services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="B")

    with pytest.raises(ContrePassationImpossible):
        services.contre_passer_ecriture_manuelle(brouillon, direction(), motif="Test")


def test_l_ecran_propose_la_contre_passation_a_la_direction_seulement(client):
    ecriture = _od_validee()
    url_detail = reverse("accounting:ecriture_manuelle", args=[ecriture.pk])
    url_action = reverse("accounting:ecriture_manuelle_contre_passer", args=[ecriture.pk])

    client.force_login(UserFactory(role=Role.DIRECTION))
    assert url_action in client.get(url_detail).content.decode()
    client.force_login(UserFactory(role=Role.FINANCES))
    assert url_action not in client.get(url_detail).content.decode()
    assert client.post(url_action, {"motif": "x"}).status_code == 403


def test_contre_passer_via_l_ecran_affiche_le_resultat_puis_masque_le_bouton(client):
    ecriture = _od_validee()
    client.force_login(UserFactory(role=Role.DIRECTION))
    url_detail = reverse("accounting:ecriture_manuelle", args=[ecriture.pk])
    url_action = reverse("accounting:ecriture_manuelle_contre_passer", args=[ecriture.pk])

    sans_motif = client.post(url_action, {"motif": ""}, follow=True)
    assert "motif" in sans_motif.content.decode().lower()
    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CONTRE_PASSATION).exists()

    reponse = client.post(url_action, {"motif": "Montant erroné"}, follow=True)
    page = reponse.content.decode()
    assert "contre-passée par" in page
    assert url_action not in client.get(url_detail).content.decode()
