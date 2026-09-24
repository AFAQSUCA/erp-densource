"""Notifications de facturation : soumission, validation, refus, factures échues."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.notifications import taches
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_direction_est_prevenue_d_une_facture_a_valider():
    chef, autre_direction, finance = (UserFactory(role=r) for r in (Role.DIRECTION, Role.DIRECTION, Role.FINANCES))
    preparateur = UserFactory(role=Role.FINANCES)
    facture = brouillon(prix="1000000", acteur=preparateur)

    services.soumettre(facture, preparateur)

    for compte in (chef, autre_direction):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.FACTURE
        assert notification.niveau == NiveauNotification.ATTENTION
        assert facture.client.raison_sociale in notification.titre
        assert "1 180 000 FCFA TTC" in notification.message.replace("\xa0", " ").replace(" ", " ")
        assert facture.mission.numero in notification.message
        assert notification.url == reverse("billing:facture", args=[facture.pk])
        assert notification.action == "Examiner et valider"  # bouton d'accès direct à la validation
    assert _de(finance) == []


def test_finances_et_l_auteur_sont_prevenus_de_la_validation():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.ADMIN)  # un ADMIN peut aussi préparer
    autre_finances = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    # La FINANCES reçoit le bouton « Confirmer le versement » (écran de confirmation, pas la facture) ...
    notification = _de(autre_finances)[-1]
    assert notification.titre == f"Facture {facture.numero} validée : versement à confirmer"
    assert notification.niveau == NiveauNotification.INFO
    assert "échéance le 01/10/2026" in notification.message
    assert "ajouté en entrée de trésorerie" in notification.message
    assert notification.action == "Confirmer le versement"
    assert notification.url == reverse("finance:versement_confirmer", args=[facture.pk])
    # ... l'auteur qui n'est pas de la FINANCES est seulement prévenu, avec le lien de la facture.
    notification = _de(preparateur)[-1]
    assert notification.titre == f"Facture {facture.numero} validée"
    assert "échéance le 01/10/2026" in notification.message
    assert notification.action == "" and notification.url == reverse("billing:facture", args=[facture.pk])
    assert all("validée" not in n.titre for n in _de(chef))


def test_un_auteur_de_la_finances_ne_recoit_qu_une_notification_de_validation():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    validations = [n for n in _de(preparateur) if "validée" in n.titre]
    assert len(validations) == 1 and validations[0].action == "Confirmer le versement"


def test_l_auteur_est_prevenu_du_refus_avec_le_motif():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.FINANCES)
    autre_finances = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.refuser(facture, chef, motif="Prix à revoir")

    notification = _de(preparateur)[-1]
    assert notification.titre.startswith("Facture renvoyée par la direction")
    assert "Prix à revoir" in notification.message
    assert notification.niveau == NiveauNotification.ATTENTION
    assert _de(autre_finances) == []


# --- factures échues ---


def test_les_factures_echues_previennent_finances_et_direction_une_seule_fois():
    finance, chef, rh = UserFactory(role=Role.FINANCES), UserFactory(role=Role.DIRECTION), UserFactory(role=Role.RH)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))  # échéance 31/07/2026
    services.enregistrer_reglement(
        facture, finance, montant=Decimal("180000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 7, 5)
    )
    aujourd_hui = date(2026, 8, 10)

    premiere = taches.alerter_factures_echues(aujourd_hui=aujourd_hui)
    seconde = taches.alerter_factures_echues(aujourd_hui=aujourd_hui + timedelta(days=1))

    destinataires = User.objects.filter(role__in=[Role.FINANCES, Role.DIRECTION]).count()
    assert premiere == destinataires >= 2 and seconde == 0  # un message par compte, jamais renvoyé
    for compte in (finance, chef):
        alerte = [n for n in _de(compte) if "échue" in n.titre][0]
        assert alerte.niveau == NiveauNotification.URGENT
        assert alerte.titre == f"Facture {facture.numero} échue : {facture.client.raison_sociale}"
        assert "1 000 000 FCFA" in alerte.message.replace("\xa0", " ").replace(" ", " ")
        assert "échue depuis 10 jours" in alerte.message
    # La FINANCES peut confirmer le versement d'un clic ; la DIRECTION, qui ne saisit pas, consulte la facture.
    alerte_finance = [n for n in _de(finance) if "échue" in n.titre][0]
    assert alerte_finance.action == "Confirmer le versement"
    assert alerte_finance.url == reverse("finance:versement_confirmer", args=[facture.pk])
    alerte_direction = [n for n in _de(chef) if "échue" in n.titre][0]
    assert alerte_direction.action == ""
    assert alerte_direction.url == reverse("billing:facture", args=[facture.pk])
    assert _de(rh) == []


def test_pas_d_alerte_pour_une_facture_non_echue_ou_soldee():
    finance = UserFactory(role=Role.FINANCES)
    emise(aujourd_hui=date(2026, 8, 25))  # échéance 24/09
    soldee = emise(prix="1000", aujourd_hui=date(2026, 7, 1))
    services.enregistrer_reglement(
        soldee, finance, montant=Decimal("1180"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 7, 2)
    )

    assert taches.alerter_factures_echues(aujourd_hui=date(2026, 9, 1)) == 0


def test_les_taches_quotidiennes_incluent_les_factures_echues():
    UserFactory(role=Role.FINANCES)
    emise(aujourd_hui=date(2026, 7, 1))

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=date(2026, 9, 1))

    assert resultat["factures_echues"] == User.objects.filter(role__in=[Role.FINANCES, Role.DIRECTION]).count()
