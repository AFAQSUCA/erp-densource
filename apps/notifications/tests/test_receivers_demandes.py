"""Qui est prévenu de quoi pour les dépenses du parc auto pré-approuvées (R2)."""

from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.finance import demandes as services
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_direction_est_prevenue_d_une_demande_manuelle():
    direction = UserFactory(role=Role.DIRECTION)

    services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES,
        montant_estime=Decimal("150000"), motif="Pièce rare",
    )

    (notification,) = _de(direction)
    assert notification.categorie == CategorieNotification.DEMANDE_DEPENSE


def test_le_demandeur_est_prevenu_de_la_validation():
    parcauto = UserFactory(role=Role.PARCAUTO)
    demande = services.soumettre_demande(
        parcauto, categorie=CategorieDepense.PIECES, montant_estime=Decimal("150000"), motif="x"
    )

    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))

    notifications = [n for n in _de(parcauto) if n.categorie == CategorieNotification.DEMANDE_DEPENSE]
    assert any("validée" in n.titre for n in notifications)


def test_la_finance_est_prevenue_de_l_ordre_a_executer():
    finance = UserFactory(role=Role.FINANCES)
    demande = services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES, montant_estime=Decimal("150000"), motif="x"
    )

    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.DEMANDE_DEPENSE
    assert "à exécuter" in notification.titre.lower()


def test_la_direction_est_prevenue_d_un_depassement_a_l_execution():
    direction = UserFactory(role=Role.DIRECTION)
    demande = services.soumettre_demande(
        UserFactory(role=Role.PARCAUTO), categorie=CategorieDepense.PIECES, montant_estime=Decimal("100000"), motif="x"
    )
    services.valider_demande(demande, direction)
    ordre = demande.ordre_decaissement

    with pytest.raises(Exception):
        services.executer_ordre(ordre, UserFactory(role=Role.FINANCES), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("150000"))

    notifications = [n for n in _de(direction) if n.categorie == CategorieNotification.DEMANDE_DEPENSE]
    assert any("dépassement" in n.titre.lower() for n in notifications)
