"""Qui est prévenu de quoi pour un devis (R5) : finance, direction, chargé clientèle."""

from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import SEUIL_VALIDATION_DIRECTION
from apps.billing.tests.helpers import JOUR, charge_clientele, direction, finances, proforma_soumise
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_finance_est_prevenue_d_un_devis_soumis():
    finance = UserFactory(role=Role.FINANCES)
    proforma = proforma_soumise()

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.PROFORMA
    assert proforma.client.raison_sociale in notification.titre


def test_la_direction_est_prevenue_au_dela_du_seuil():
    responsable = UserFactory(role=Role.DIRECTION)
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    (notification,) = _de(responsable)
    assert notification.categorie == CategorieNotification.PROFORMA
    assert "direction" in notification.titre.lower() or "élevé" in notification.titre.lower()


def test_l_auteur_est_prevenu_de_la_validation():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    notifications = _de(auteur)
    assert any(n.categorie == CategorieNotification.PROFORMA and proforma.numero in n.titre for n in notifications)


def test_l_auteur_est_prevenu_d_une_contre_proposition():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)

    services.contre_proposer_proforma(proforma, finances(), motif="Prix trop bas")

    notifications = [n for n in _de(auteur) if n.categorie == CategorieNotification.PROFORMA]
    assert notifications and "Prix trop bas" in notifications[-1].message


def test_l_auteur_est_prevenu_de_l_expiration():
    auteur = charge_clientele()
    proforma = proforma_soumise(acteur=auteur)
    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)
    services.envoyer_proforma_au_client(proforma, auteur, aujourd_hui=JOUR)

    from datetime import timedelta

    services.expirer_proformas(aujourd_hui=JOUR + timedelta(days=31))

    notifications = [n for n in _de(auteur) if n.categorie == CategorieNotification.PROFORMA]
    assert any("expiré" in n.titre.lower() for n in notifications)
