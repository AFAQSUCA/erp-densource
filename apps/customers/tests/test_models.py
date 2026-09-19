from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.customers.models import MotifExoneration, TypeInteraction

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def test_tva_par_defaut_est_18_pourcent():
    assert ClientFactory().taux_tva == Decimal("18.00")


def test_tva_zero_sans_motif_refusee_par_la_validation():
    client = ClientFactory.build(taux_tva=Decimal("0"), motif_exoneration="")

    with pytest.raises(ValidationError):
        client.clean()


def test_tva_zero_sans_motif_refusee_par_la_base_de_donnees():
    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(taux_tva=Decimal("0"), motif_exoneration="")


def test_tva_zero_avec_motif_acceptee():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.ONG)

    client.full_clean()


def test_taux_tva_superieur_a_100_refuse_par_la_base_de_donnees():
    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(taux_tva=Decimal("101"))


def test_ncc_nif_unique():
    ClientFactory(ncc_nif="CI-0001A")

    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(ncc_nif="CI-0001A")


def test_interaction_rattachee_au_client_et_triee_par_date_decroissante():
    from django.utils import timezone

    client = ClientFactory()
    ancienne = client.interactions.create(
        type_interaction=TypeInteraction.APPEL,
        resume="Premier appel",
        date_interaction=timezone.now() - timezone.timedelta(days=2),
    )
    recente = client.interactions.create(
        type_interaction=TypeInteraction.RECLAMATION, resume="Retard livraison"
    )

    assert list(client.interactions.all()) == [recente, ancienne]


def test_creation_client_est_auditee():
    from apps.audit.models import AuditLog

    client = ClientFactory()

    entree = AuditLog.objects.get(entite="Client", entite_id=client.pk)
    assert entree.module == "CLIENTELE"
