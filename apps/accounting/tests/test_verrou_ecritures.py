"""Écritures validées immuables, même en masse et même hors de Django (PostgreSQL) — audit AV-06."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, connection, transaction

from apps.accounting import services
from apps.accounting.exceptions import EcritureVerrouillee
from apps.accounting.models import EcritureComptable, LigneEcriture, SensEcriture, StatutEcriture
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory, forcer_update
from .test_cloture_resultat import _vente

pytestmark = pytest.mark.django_db

postgresql_seulement = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="déclencheurs posés sur PostgreSQL seulement (production)"
)


def _validee():
    _vente(date(2026, 3, 1), "100000")
    return EcritureComptable.objects.filter(statut=StatutEcriture.VALIDEE, libelle="Vente").latest("pk")


def _brouillon_avec_lignes():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Brouillon")
    debit, credit = CompteFactory(), CompteFactory()
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=debit.numero, sens=SensEcriture.DEBIT, montant=Decimal("500"))
    services.ajouter_ligne_manuelle(ecriture, finances(), compte=credit.numero, sens=SensEcriture.CREDIT, montant=Decimal("500"))
    return ecriture


def test_une_ecriture_validee_ne_se_modifie_ni_ne_se_supprime_en_masse():
    ecriture = _validee()

    with pytest.raises(EcritureVerrouillee, match="même en masse"):
        EcritureComptable.objects.filter(pk=ecriture.pk).update(libelle="Falsifiée")
    with pytest.raises(EcritureVerrouillee, match="même en masse"):
        EcritureComptable.all_objects.filter(pk=ecriture.pk).delete()

    ecriture.refresh_from_db()
    assert ecriture.libelle != "Falsifiée"


def test_les_lignes_ne_se_modifient_jamais_et_ne_se_suppriment_que_dans_un_brouillon():
    validee, brouillon = _validee(), _brouillon_avec_lignes()

    with pytest.raises(EcritureVerrouillee, match="ne se modifie pas"):
        LigneEcriture.objects.filter(ecriture=brouillon).update(montant=Decimal("1"))
    with pytest.raises(EcritureVerrouillee, match="écriture validée"):
        LigneEcriture.objects.filter(ecriture=validee).delete()

    LigneEcriture.objects.filter(ecriture=brouillon).delete()
    assert not brouillon.lignes.exists() and validee.lignes.count() == 2


def test_un_brouillon_se_modifie_toujours_en_masse():
    brouillon = _brouillon_avec_lignes()

    EcritureComptable.objects.filter(pk=brouillon.pk).update(libelle="Corrigé")

    brouillon.refresh_from_db()
    assert brouillon.libelle == "Corrigé"


@postgresql_seulement
def test_postgresql_refuse_une_modification_directe_en_base():
    ecriture = _validee()
    ligne = ecriture.lignes.first()

    for requete, parametres in (
        ("UPDATE accounting_ecriturecomptable SET libelle = 'x' WHERE id = %s", [ecriture.pk]),
        ("DELETE FROM accounting_ecriturecomptable WHERE id = %s", [ecriture.pk]),
        ("UPDATE accounting_ligneecriture SET montant = 1 WHERE id = %s", [ligne.pk]),
        ("DELETE FROM accounting_ligneecriture WHERE id = %s", [ligne.pk]),
    ):
        with pytest.raises(DatabaseError, match="contre-pass"), transaction.atomic():
            with connection.cursor() as curseur:
                curseur.execute(requete, parametres)


@postgresql_seulement
def test_postgresql_laisse_valider_un_brouillon_et_les_tests_simuler_d_anciennes_donnees():
    brouillon = _brouillon_avec_lignes()
    services.valider_ecriture_manuelle(brouillon, direction())  # BROUILLON -> VALIDEE : permis
    ancienne = _validee()

    forcer_update(EcritureComptable.objects.filter(pk=ancienne.pk), origine="ANCIEN")

    ancienne.refresh_from_db()
    assert ancienne.origine == "ANCIEN"
