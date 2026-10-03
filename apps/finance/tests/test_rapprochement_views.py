"""Écran de rapprochement bancaire (Lot G) : accès, saisie, suggestions, pointage."""

from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import JOUR, emise, finances
from apps.finance import services
from apps.finance.models import LigneReleve, SensMouvement

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees_ligne(**surcharges):
    donnees = {
        "date_operation": timezone.localdate().isoformat(), "libelle": "Virement client",
        "montant": "100000", "sens": "ENTREE", "reference": "",
    }
    donnees.update(surcharges)
    return donnees


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_le_rapprochement_est_accessible_a_admin_direction_finances_et_rh(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:rapprochement")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_rapprochement_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:rapprochement")).status_code == 403


def test_le_rapprochement_exige_la_connexion(client):
    assert client.get(reverse("finance:rapprochement")).status_code == 302


def test_les_soldes_et_l_ecart_s_affichent(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement = services.confirmer_versement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )[0]
    services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Virement client", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )

    reponse = client.get(f"{reverse('finance:rapprochement')}?debut=2026-09-01&fin=2026-09-30")
    texte = reponse.content.decode().replace("\xa0", " ").replace(" ", " ")

    assert reponse.context["etat"]["solde_releve"] == Decimal("100000")
    assert reponse.context["etat"]["solde_comptable"] == Decimal("100000")
    assert "100 000" in texte
    assert reglement.pk  # le règlement existe bien, utilisé comme mouvement de rapprochement


def test_finances_saisit_une_ligne_de_releve(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:ligne_releve_nouvelle"), _donnees_ligne(), follow=True)

    ligne = LigneReleve.objects.get()
    assert (ligne.sens, ligne.montant, ligne.libelle) == (SensMouvement.ENTREE, Decimal("100000"), "Virement client")
    assert any("ajoutée" in m for m in _messages(reponse))


@pytest.mark.parametrize(
    "surcharges",
    [{"montant": "0"}, {"libelle": ""}, {"date_operation": "2999-01-01"}, {"sens": "AUTRE"}],
)
def test_saisie_de_ligne_invalide_donne_un_message_sans_rien_enregistrer(client, surcharges):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:ligne_releve_nouvelle"), _donnees_ligne(**surcharges), follow=True)

    assert not LigneReleve.objects.exists() and _messages(reponse)


def test_une_suggestion_apparait_pour_un_mouvement_banque_correspondant(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement, _ = services.confirmer_versement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )
    services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Virement client", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )

    reponse = client.get(f"{reverse('finance:rapprochement')}?debut=2026-09-01&fin=2026-09-30")

    entrees = reponse.context["lignes_avec_suggestions"]
    assert len(entrees) == 1
    assert entrees[0]["suggestions"][0]["pk"] == reglement.pk


def test_pointer_une_ligne_depuis_l_ecran(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement, _ = services.confirmer_versement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )
    ligne = services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Virement client", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )

    reponse = client.post(
        reverse("finance:ligne_releve_pointer", args=[ligne.pk]),
        {"origine": "REGLEMENT", "mouvement_id": reglement.pk},
        follow=True,
    )

    ligne.refresh_from_db()
    assert ligne.pointee is True and ligne.mouvement_id == reglement.pk
    assert any("pointée" in m for m in _messages(reponse))


def test_pointer_un_mouvement_deja_pointe_donne_un_message_d_erreur(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement, _ = services.confirmer_versement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )
    premiere = services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="A", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )
    services.pointer_ligne_releve(premiere, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)
    seconde = services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="B", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )

    reponse = client.post(
        reverse("finance:ligne_releve_pointer", args=[seconde.pk]),
        {"origine": "REGLEMENT", "mouvement_id": reglement.pk},
        follow=True,
    )

    seconde.refresh_from_db()
    assert seconde.pointee is False
    assert any("déjà pointé" in m for m in _messages(reponse))


def test_pointer_avec_un_formulaire_invalide_donne_un_message_sans_rien_pointer(client):
    _connecte(client, Role.FINANCES)
    ligne = services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="A", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )

    reponse = client.post(
        reverse("finance:ligne_releve_pointer", args=[ligne.pk]),
        {"origine": "BIDON", "mouvement_id": ""},
        follow=True,
    )

    ligne.refresh_from_db()
    assert ligne.pointee is False and _messages(reponse)


def test_pointer_une_ligne_inexistante_donne_404(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("finance:ligne_releve_pointer", args=[999]), {"origine": "MANUEL", "mouvement_id": 1}
    )

    assert reponse.status_code == 404


def test_depointer_une_ligne_depuis_l_ecran(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement, _ = services.confirmer_versement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )
    ligne = services.saisir_ligne_releve(
        finances(), date_operation=JOUR, libelle="Virement client", montant=Decimal("100000"), sens=SensMouvement.ENTREE
    )
    services.pointer_ligne_releve(ligne, finances(), origine="REGLEMENT", mouvement_id=reglement.pk)

    reponse = client.post(reverse("finance:ligne_releve_depointer", args=[ligne.pk]), follow=True)

    ligne.refresh_from_db()
    assert ligne.pointee is False
    assert any("annulé" in m for m in _messages(reponse))


def test_les_actions_de_rapprochement_exigent_post_et_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))
    ligne = services.saisir_ligne_releve(
        UserFactory(role=Role.FINANCES), date_operation=JOUR, libelle="Apport",
        montant=Decimal("1000"), sens=SensMouvement.ENTREE,
    )

    assert http.get(reverse("finance:ligne_releve_nouvelle")).status_code == 405
    assert http.post(reverse("finance:ligne_releve_nouvelle"), _donnees_ligne()).status_code == 403
    assert http.post(
        reverse("finance:ligne_releve_pointer", args=[ligne.pk]), {"origine": "MANUEL", "mouvement_id": 1}
    ).status_code == 403
    assert http.post(reverse("finance:ligne_releve_depointer", args=[ligne.pk])).status_code == 403
    assert LigneReleve.objects.count() == 1
