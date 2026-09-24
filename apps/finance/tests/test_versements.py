"""Versements attendus : la Finance confirme qu'une facture émise a été payée, et l'entrée apparaît en trésorerie."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, ReglementInvalide
from apps.billing.models import CompteTresorerie, ModePaiement, StatutFacture
from apps.billing.tests.helpers import a_valider, brouillon, emise, finances
from apps.finance import services

pytestmark = pytest.mark.django_db

JOUR_PAIEMENT = date(2026, 9, 10)  # après l'émission (2026-09-01), avant aujourd'hui


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


# --- versements attendus (service) ---


def test_les_versements_attendus_listent_les_factures_emises_non_soldees_les_plus_en_retard_d_abord():
    a_venir = emise(prix="500000", aujourd_hui=date(2026, 8, 1))  # échéance 31/08
    echue = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))  # échéance 31/07
    brouillon(prix="300000")  # pas émise : rien à attendre
    a_valider(prix="300000")

    attendus = services.versements_attendus(aujourd_hui=date(2026, 8, 10))

    assert [ligne["facture"].pk for ligne in attendus["lignes"]] == [echue.pk, a_venir.pk]
    assert attendus["nombre"] == 2
    premiere, seconde = attendus["lignes"]
    assert (premiere["echue"], premiere["jours"]) == (True, 10)
    assert (seconde["echue"], seconde["jours"]) == (False, 21)
    assert premiere["reste"] == Decimal("1180000") and seconde["reste"] == Decimal("590000")
    assert attendus["total"] == Decimal("1770000")
    assert attendus["echu"] == Decimal("1180000")
    assert attendus["a_venir"] == Decimal("590000")


def test_un_acompte_reduit_le_versement_attendu_et_le_solde_le_retire():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
    )

    reste = services.versements_attendus()["lignes"][0]["reste"]
    assert reste == Decimal("780000")

    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("780000"), mode=ModePaiement.ESPECES, date_reglement=JOUR_PAIEMENT
    )
    assert services.versements_attendus()["nombre"] == 0


def test_aucune_facture_a_encaisser():
    assert services.versements_attendus() == {
        "lignes": [], "nombre": 0, "total": Decimal("0"), "echu": Decimal("0"), "a_venir": Decimal("0"),
    }


# --- confirmation (service) ---


def test_confirmer_un_versement_l_ajoute_en_entree_de_tresorerie_sur_le_bon_compte():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    avant = services.soldes_par_compte()

    reglement, compte = services.confirmer_versement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.WAVE,
        date_reglement=JOUR_PAIEMENT, reference="WV-123",
    )

    facture.refresh_from_db()
    apres = services.soldes_par_compte()
    assert compte == CompteTresorerie.MOBILE_MONEY
    assert facture.statut == StatutFacture.PAYEE
    assert apres["MOBILE_MONEY"] - avant["MOBILE_MONEY"] == Decimal("1180000")
    assert apres["total"] - avant["total"] == Decimal("1180000")
    entree = next(m for m in services.mouvements() if m["origine"] == "REGLEMENT")
    assert (entree["sens"], entree["montant"], entree["reference"]) == ("ENTREE", Decimal("1180000"), "WV-123")
    assert facture.numero in entree["libelle"]


def test_on_ne_confirme_pas_plus_que_le_reste_a_recouvrer():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    with pytest.raises(ReglementInvalide):
        services.confirmer_versement(
            facture, finances(), montant=Decimal("1180001"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
        )

    assert services.soldes_par_compte()["total"] == Decimal("0")


def test_seule_la_finance_confirme_un_versement():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    with pytest.raises(ActionFactureNonAutorisee):
        services.confirmer_versement(
            facture, UserFactory(role=Role.DIRECTION), montant=Decimal("1000"),
            mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT,
        )


# --- écrans ---


def _url(facture):
    return reverse("finance:versement_confirmer", args=[facture.pk])


def test_la_tresorerie_liste_les_versements_a_confirmer_avec_le_bouton_pour_la_finance(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    contenu = client.get(reverse("finance:tresorerie")).content.decode()

    assert "Versements à confirmer" in contenu
    assert facture.numero in contenu
    assert _url(facture) in contenu and "Confirmer le versement" in contenu


def test_la_direction_voit_les_versements_attendus_sans_pouvoir_les_confirmer(client):
    _connecte(client, Role.DIRECTION)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("finance:tresorerie"))

    assert facture.numero in reponse.content.decode()
    assert _url(facture) not in reponse.content.decode()
    assert client.get(_url(facture)).status_code == 403


def test_le_solde_previsionnel_ajoute_les_versements_attendus_au_solde_reel(client):
    _connecte(client, Role.FINANCES)
    emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("finance:tresorerie"))

    assert reponse.context["soldes"]["total"] == Decimal("0")  # rien n'est encaissé : le solde réel ne bouge pas
    assert reponse.context["solde_previsionnel"] == Decimal("1180000")


def test_l_ecran_de_confirmation_propose_le_reste_a_recouvrer(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(_url(facture))

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["montant"] == Decimal("1180000")
    assert facture.numero in reponse.content.decode()


def test_confirmer_le_versement_ajoute_l_entree_et_solde_la_facture(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "1180000", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.VIREMENT, "reference": "VIR-9"},
        follow=True,
    )

    facture.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("finance:tresorerie")
    assert facture.statut == StatutFacture.PAYEE
    assert any("confirmé" in m and "compte Banque" in m for m in _messages(reponse))
    assert reponse.context["soldes"]["BANQUE"] == Decimal("1180000")
    assert reponse.context["versements"]["nombre"] == 0  # plus rien à attendre pour cette facture


def test_un_versement_partiel_laisse_le_solde_dans_les_versements_attendus(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "400000", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.ESPECES},
        follow=True,
    )

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert reponse.context["versements"]["total"] == Decimal("780000")
    assert reponse.context["soldes"]["CAISSE"] == Decimal("400000")


def test_un_montant_trop_eleve_reste_sur_le_formulaire_sans_rien_enregistrer(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "9999999", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.VIREMENT},
    )

    assert reponse.status_code == 200
    assert "dépasse le reste à recouvrer" in reponse.content.decode()
    assert services.soldes_par_compte()["total"] == Decimal("0")


def test_une_facture_deja_soldee_renvoie_a_la_tresorerie(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
    )

    reponse = client.get(_url(facture), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("finance:tresorerie")
    assert any("n'attend plus de versement" in m for m in _messages(reponse))


def test_une_facture_inconnue_est_introuvable(client):
    _connecte(client, Role.FINANCES)

    assert client.get(reverse("finance:versement_confirmer", args=[99999])).status_code == 404


def test_la_notification_de_validation_mene_a_l_ecran_de_confirmation(client):
    """Bout en bout : validation par la DIRECTION -> bouton dans la notification de la FINANCES -> confirmation."""
    finance = _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    page = client.get(reverse("notifications:liste")).content.decode()
    assert "Confirmer le versement" in page

    notification = finance.notifications.get(titre__contains="versement à confirmer")
    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse.status_code == 302 and reponse.url == _url(facture)
