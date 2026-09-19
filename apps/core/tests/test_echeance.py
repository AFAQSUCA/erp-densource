"""Calcul d'échéance partagé — alerte à 30 jours (cahier-des-charges.md:95)."""

from datetime import date

import pytest

from apps.core.services import etat_echeance

AUJOURDHUI = date(2026, 9, 20)


@pytest.mark.parametrize(
    ("expiration", "etat", "restants"),
    [
        (None, "MANQUANT", None),
        (date(2026, 9, 19), "EXPIRE", -1),  # hier : expiré
        (date(2026, 8, 1), "EXPIRE", -50),
        (date(2026, 9, 20), "A_RENOUVELER", 0),  # aujourd'hui : encore valable, à renouveler
        (date(2026, 10, 20), "A_RENOUVELER", 30),  # 30 jours : alerte
        (date(2026, 10, 21), "VALIDE", 31),  # 31 jours : pas encore
        (date(2030, 1, 1), "VALIDE", 1199),
    ],
)
def test_etat_echeance_selon_les_jours_restants(expiration, etat, restants):
    assert etat_echeance(expiration, aujourd_hui=AUJOURDHUI) == (etat, restants)


def test_le_delai_d_alerte_est_parametrable():
    assert etat_echeance(date(2026, 10, 20), aujourd_hui=AUJOURDHUI, jours=15) == ("VALIDE", 30)
    assert etat_echeance(date(2026, 10, 5), aujourd_hui=AUJOURDHUI, jours=15) == ("A_RENOUVELER", 15)


def test_par_defaut_la_date_du_jour_est_utilisee():
    from django.utils import timezone

    aujourdhui = timezone.localdate()

    assert etat_echeance(aujourdhui) == ("A_RENOUVELER", 0)
