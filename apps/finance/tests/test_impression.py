"""Rapport imprimable de la trésorerie : mêmes filtres que le journal, sans pagination."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


def _connecte(client, role=Role.FINANCES):
    client.force_login(UserFactory(role=role))


def test_impression_de_la_tresorerie(client):
    _connecte(client)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 9, 10)
    )

    texte = _texte(client.get(reverse("finance:imprimer")))

    assert "Trésorerie" in texte and facture.numero in texte and "500 000" in texte
    assert "Banque" in texte and "Caisse" in texte and "Mobile Money" in texte


def test_impression_reprend_les_filtres_de_periode_et_de_compte(client):
    _connecte(client)
    ancien = emise(prix="100000", aujourd_hui=date(2026, 1, 1))
    billing.enregistrer_reglement(
        ancien, finances(), montant=Decimal("118000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 1, 5)
    )
    recent = emise(prix="200000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        recent, finances(), montant=Decimal("236000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 9, 10)
    )

    reponse = client.get(
        reverse("finance:imprimer"),
        {"date_debut": "2026-09-01", "date_fin": "2026-09-30", "compte": "BANQUE"},
    )
    texte = _texte(reponse)

    assert recent.numero in texte and ancien.numero not in texte
    assert "01/09/2026 au 30/09/2026" in texte and "compte : Banque" in texte


def test_seule_l_entree_ou_la_sortie_demandee_apparait(client):
    _connecte(client)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("300000"), mode=ModePaiement.WAVE, date_reglement=date(2026, 9, 5)
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=date(2026, 9, 6), libelle="Péage",
        montant=Decimal("10000"), mode=ModePaiement.ESPECES,
    )

    texte_entrees = _texte(client.get(reverse("finance:imprimer"), {"sens": "ENTREE"}))
    assert facture.numero in texte_entrees and "Péage" not in texte_entrees

    texte_sorties = _texte(client.get(reverse("finance:imprimer"), {"sens": "SORTIE"}))
    assert "Péage" in texte_sorties and facture.numero not in texte_sorties


def test_accessible_en_lecture_a_la_direction_et_a_la_rh_mais_pas_aux_autres(client):
    # Retour réunion : la RH fait tout ce que fait la FINANCES, y compris consulter la trésorerie.
    _connecte(client, Role.DIRECTION)
    assert client.get(reverse("finance:imprimer")).status_code == 200

    _connecte(client, Role.RH)
    assert client.get(reverse("finance:imprimer")).status_code == 200

    _connecte(client, Role.PARCAUTO)
    assert client.get(reverse("finance:imprimer")).status_code == 403


def test_sans_mouvement_le_rapport_le_dit(client):
    _connecte(client)

    texte = _texte(client.get(reverse("finance:imprimer")))

    assert "Aucun mouvement pour ces critères." in texte


def test_au_dela_de_la_limite_le_journal_est_tronque(monkeypatch, client):
    from apps.finance.views import TresorerieImprimerView

    monkeypatch.setattr(TresorerieImprimerView, "limite", 2)
    _connecte(client)
    for i in range(3):
        f = emise(prix="100000", aujourd_hui=date(2026, 9, 1 + i))
        billing.enregistrer_reglement(
            f, finances(), montant=Decimal("118000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 9, 15)
        )

    reponse = client.get(reverse("finance:imprimer"))

    assert reponse.context["nombre"] == 2 and reponse.context["tronque"] is True
    assert "limité" in _texte(reponse)


def test_le_lien_imprimer_est_sur_la_page_tresorerie_avec_les_filtres(client):
    _connecte(client)

    page = client.get(reverse("finance:tresorerie"), {"compte": "CAISSE"}).content.decode()

    assert reverse("finance:imprimer") in page and "compte%3DCAISSE" in page or "compte=CAISSE" in page
