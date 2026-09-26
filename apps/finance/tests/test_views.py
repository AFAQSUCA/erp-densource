"""Écran de trésorerie : accès, journal, soldes, mouvements manuels."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "sens": "ENTREE", "date_mouvement": timezone.localdate().isoformat(),
        "libelle": "Solde d'ouverture", "montant": "250000", "mode": "VIREMENT", "reference": "",
    }
    donnees.update(surcharges)
    return donnees


def _texte(reponse):
    return reponse.content.decode().replace("\xa0", " ").replace(" ", " ")


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_tresorerie_est_accessible_a_admin_direction_finances_et_rh(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_tresorerie_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 403


def test_la_tresorerie_exige_la_connexion(client):
    assert client.get(reverse("finance:tresorerie")).status_code == 302


def test_la_direction_et_la_rh_consultent_et_saisissent_desormais(client):
    """Retour réunion : la DIRECTION (même largeur que l'ADMIN) et la RH (tout ce que fait
    la FINANCES) peuvent désormais saisir un mouvement de trésorerie."""
    for role in (Role.DIRECTION, Role.RH):
        _connecte(client, role)
        texte = client.get(reverse("finance:tresorerie")).content.decode()
        assert "Autre mouvement" in texte
        assert client.post(reverse("finance:mouvement_creer"), _donnees()).status_code == 302


def test_soldes_et_journal_s_affichent(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("600000"), mode=ModePaiement.WAVE,
        date_reglement=timezone.localdate(),
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=timezone.localdate(), libelle="Péage Bouaké",
        montant=Decimal("25000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("finance:tresorerie"))
    texte = _texte(reponse)

    assert reponse.context["soldes"]["total"] == Decimal("575000")
    assert "575 000" in texte and "Mobile Money" in texte
    assert f"Règlement {facture.numero}" in texte and "Dépense : Péage Bouaké" in texte
    assert reverse("billing:facture", args=[facture.pk]) in texte  # lien du règlement vers sa facture
    assert reponse.context["mois"]["variation"] == Decimal("575000")


def test_le_journal_se_filtre(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    aujourd_hui = timezone.localdate()
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.WAVE, date_reglement=aujourd_hui
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=aujourd_hui, libelle="Péage",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )
    url = reverse("finance:tresorerie")

    assert [m["origine"] for m in client.get(url, {"sens": "ENTREE"}).context["mouvements"]] == ["REGLEMENT"]
    assert [m["origine"] for m in client.get(url, {"compte": "CAISSE"}).context["mouvements"]] == ["DEPENSE"]
    assert len(client.get(url, {"date_debut": aujourd_hui.isoformat()}).context["mouvements"]) == 2
    assert len(client.get(url, {"sens": "N_IMPORTE_QUOI", "compte": "???", "date_debut": "abc"}).context["mouvements"]) == 2


def test_une_periode_a_l_envers_est_signalee_et_ignoree(client):
    _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        finances(), sens="ENTREE", date_mouvement=timezone.localdate(), libelle="Apport",
        montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    reponse = client.get(reverse("finance:tresorerie"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"})

    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["mouvements"]) == 1


def test_le_journal_est_pagine_et_tolerant(client):
    compte = _connecte(client, Role.FINANCES)
    for i in range(30):
        services.enregistrer_mouvement(
            compte, sens="ENTREE", date_mouvement=timezone.localdate() - timedelta(days=i % 5),
            libelle=f"Apport {i}", montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
        )

    premiere = client.get(reverse("finance:tresorerie"))
    trop_loin = client.get(reverse("finance:tresorerie"), {"page": 99})
    illisible = client.get(reverse("finance:tresorerie"), {"page": "abc"})

    assert len(premiere.context["mouvements"]) == 25
    assert trop_loin.context["page_obj"].number == 2 and illisible.context["page_obj"].number == 1


def test_journal_vide(client):
    _connecte(client, Role.FINANCES)

    assert "Aucun mouvement" in client.get(reverse("finance:tresorerie")).content.decode()


def test_finances_enregistre_un_mouvement_manuel(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:mouvement_creer"), _donnees(), follow=True)

    mouvement = MouvementManuel.objects.get()
    assert (mouvement.sens, mouvement.montant) == (SensMouvement.ENTREE, Decimal("250000"))
    assert any("250 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))
    assert services.soldes_par_compte()["BANQUE"] == Decimal("250000")


@pytest.mark.parametrize(
    "surcharges",
    [{"montant": "0"}, {"libelle": ""}, {"date_mouvement": "2999-01-01"}, {"sens": "AUTRE"}, {"mode": "TROC"}],
)
def test_mouvement_invalide_donne_un_message_sans_rien_enregistrer(client, surcharges):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:mouvement_creer"), _donnees(**surcharges), follow=True)

    assert not MouvementManuel.objects.exists() and _messages(reponse)


def test_annuler_un_mouvement_exige_un_motif(client):
    compte = _connecte(client, Role.FINANCES)
    mouvement = services.enregistrer_mouvement(
        compte, sens="SORTIE", date_mouvement=timezone.localdate(), libelle="Retrait",
        montant=Decimal("10000"), mode=ModePaiement.ESPECES,
    )
    url = reverse("finance:mouvement_annuler", args=[mouvement.pk])

    client.post(url, {"motif": " "}, follow=True)
    assert MouvementManuel.objects.filter(pk=mouvement.pk).exists()

    reponse = client.post(url, {"motif": "Erreur de saisie"}, follow=True)
    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert any("Mouvement annulé" in m for m in _messages(reponse))
    assert services.soldes_par_compte()["total"] == 0


def test_annuler_un_mouvement_inexistant_donne_404(client):
    _connecte(client, Role.FINANCES)

    assert client.post(reverse("finance:mouvement_annuler", args=[999]), {"motif": "x"}).status_code == 404


def test_les_actions_de_tresorerie_exigent_post_et_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))
    mouvement = services.enregistrer_mouvement(
        UserFactory(role=Role.FINANCES), sens="ENTREE", date_mouvement=timezone.localdate(),
        libelle="Apport", montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    assert http.get(reverse("finance:mouvement_creer")).status_code == 405
    assert http.post(reverse("finance:mouvement_creer"), _donnees()).status_code == 403
    assert http.get(reverse("finance:mouvement_annuler", args=[mouvement.pk])).status_code == 405
    assert http.post(reverse("finance:mouvement_annuler", args=[mouvement.pk]), {"motif": "x"}).status_code == 403
    assert MouvementManuel.objects.count() == 1


def test_les_libelles_sont_echappes(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        compte, sens="ENTREE", date_mouvement=timezone.localdate(), libelle="<script>alert(1)</script>",
        montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    texte = client.get(reverse("finance:tresorerie")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "&lt;script&gt;" in texte


def test_le_compte_mobile_money_s_affiche_avec_son_vrai_nom(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        compte, sens="ENTREE", date_mouvement=timezone.localdate(), libelle="Dépôt Wave",
        montant=Decimal("1000"), mode=ModePaiement.WAVE,
    )

    texte = client.get(reverse("finance:tresorerie")).content.decode()

    assert "Mobilemoney" not in texte and "Mobile Money" in texte
