"""Intégration : la validation d'une facture (billing) génère toujours son écriture comptable —
cahier-des-charges.md:340."""

from decimal import Decimal

import pytest

from apps.accounting.constants import COMPTE_CLIENTS, COMPTE_TVA_COLLECTEE, COMPTE_VENTES_TRANSPORT
from apps.accounting.models import EcritureComptable, Journal, SensEcriture
from apps.billing import services as billing_services
from apps.billing.tests.helpers import a_valider, direction, emise
from apps.customers.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


def test_facture_validee_genere_une_ecriture_equilibree():
    facture = emise(prix="1000000")

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)

    assert ecriture.journal == Journal.VENTES
    assert ecriture.numero.startswith("VTE-2026-")
    assert ecriture.piece_reference == facture.numero
    lignes = {l.compte.numero: (l.sens, l.montant) for l in ecriture.lignes.all()}
    assert lignes[COMPTE_CLIENTS] == (SensEcriture.DEBIT, facture.montant_ttc)
    assert lignes[COMPTE_VENTES_TRANSPORT] == (SensEcriture.CREDIT, facture.montant_ht)
    assert lignes[COMPTE_TVA_COLLECTEE] == (SensEcriture.CREDIT, facture.montant_tva)
    total_debit = sum(m for sens, m in lignes.values() if sens == SensEcriture.DEBIT)
    total_credit = sum(m for sens, m in lignes.values() if sens == SensEcriture.CREDIT)
    assert total_debit == total_credit == facture.montant_ttc


def test_ligne_clients_est_rattachee_au_client_de_la_facture():
    facture = emise()

    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    ligne_clients = ecriture.lignes.get(compte__numero=COMPTE_CLIENTS)

    assert ligne_clients.tiers_type == "CLIENT"
    assert ligne_clients.tiers_id == facture.client_id


def test_une_facture_exoneree_ne_cree_pas_de_ligne_tva():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = emise(client=client)

    assert facture.montant_tva == 0
    ecriture = EcritureComptable.objects.get(origine="FACTURE", origine_id=facture.pk)
    assert ecriture.lignes.count() == 2
    assert not ecriture.lignes.filter(compte__numero=COMPTE_TVA_COLLECTEE).exists()


def test_valider_une_facture_deja_validee_ne_duplique_pas_l_ecriture():
    facture = emise()
    nb_avant = EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count()

    from apps.billing.exceptions import TransitionFactureInterdite

    with pytest.raises(TransitionFactureInterdite):
        billing_services.valider(facture, direction())

    assert EcritureComptable.objects.filter(origine="FACTURE", origine_id=facture.pk).count() == nb_avant == 1
