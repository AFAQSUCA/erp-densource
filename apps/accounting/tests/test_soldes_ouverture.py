"""Grand livre et balance d'une période : ils partent du solde au début de la période, pas de zéro — audit AV-07."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.models import Compte
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

from .test_cloture_resultat import _charge, _cloturer, _vente

pytestmark = pytest.mark.django_db

MARS = date(2026, 3, 1)


def _ligne(balance, numero):
    return next(l for l in balance if l["compte__numero"] == numero)


def test_le_grand_livre_d_une_periode_part_du_solde_d_ouverture():
    _vente(date(2026, 2, 10), "500000")
    _vente(date(2026, 3, 5), "200000")
    clients = Compte.objects.get(numero="411000")

    assert services.solde_ouverture(clients, avant=MARS) == Decimal("500000")
    lignes = services.grand_livre_avec_solde(clients, debut=MARS)
    assert [l["solde_cumule"] for l in lignes] == [Decimal("700000")]
    assert [l["solde_cumule"] for l in services.grand_livre_avec_solde(clients)] == [500000, 700000]


def test_la_balance_d_une_periode_reprend_l_ouverture_meme_sans_mouvement_dans_la_periode():
    _vente(date(2026, 2, 10), "500000")
    _charge(date(2026, 3, 5), "80000")

    balance = services.balance(debut=MARS)

    clients = _ligne(balance, "411000")  # aucun mouvement en mars, mais un solde à reprendre
    assert (clients["solde_ouverture_debiteur"], clients["total_debit"], clients["solde_debiteur"]) == (500000, 0, 500000)
    caisse = _ligne(balance, "571000")
    assert (caisse["solde_ouverture_debiteur"], caisse["total_credit"], caisse["solde_crediteur"]) == (0, 80000, 80000)
    assert sum(l["solde_debiteur"] for l in balance) == sum(l["solde_crediteur"] for l in balance)


def test_sans_date_de_debut_rien_ne_change():
    _vente(date(2026, 2, 10), "500000")

    clients = _ligne(services.balance(), "411000")

    assert (clients["solde_ouverture_debiteur"], clients["solde_ouverture_crediteur"]) == (0, 0)
    assert clients["solde_debiteur"] == 500000


def test_apres_cloture_les_charges_et_produits_repartent_de_zero_et_le_resultat_est_repris():
    _vente(date(2025, 6, 1), "1000000")
    _charge(date(2025, 6, 2), "300000")
    _cloturer(date(2025, 6, 1))

    balance = services.balance(debut=date(2026, 1, 1))

    numeros = {l["compte__numero"] for l in balance}
    assert "706100" not in numeros and "605100" not in numeros  # soldés par la clôture de 2025
    assert _ligne(balance, "120000")["solde_ouverture_crediteur"] == Decimal("700000")


def test_l_ecran_du_grand_livre_affiche_la_ligne_de_solde_d_ouverture(client):
    _vente(date(2026, 2, 10), "500000")
    clients = Compte.objects.get(numero="411000")
    client.force_login(UserFactory(role=Role.FINANCES))

    page = client.get(reverse("accounting:grand_livre"), {"compte": clients.numero, "debut": "2026-03-01"}).content.decode()

    assert "Solde au 01/03/2026" in page and "500" in page


def test_la_balance_et_les_exports_d_une_periode_montrent_l_ouverture(client):
    import io

    import openpyxl

    _vente(date(2026, 2, 10), "500000")
    client.force_login(UserFactory(role=Role.FINANCES))
    periode = {"debut": "2026-03-01"}

    assert "Ouverture débiteur" in client.get(reverse("accounting:balance"), periode).content.decode()
    assert "Ouverture débiteur" not in client.get(reverse("accounting:balance")).content.decode()
    for url, params in (
        (reverse("accounting:balance_xlsx"), periode),
        (reverse("accounting:grand_livre_xlsx"), {**periode, "compte": "411000"}),
    ):
        reponse = client.get(url, params)
        assert reponse.status_code == 200
        cellules = [c for ligne in openpyxl.load_workbook(io.BytesIO(reponse.content)).active.iter_rows(values_only=True)
                    for c in ligne]
        assert "Ouverture débiteur" in cellules or "Solde au 01/03/2026" in cellules
