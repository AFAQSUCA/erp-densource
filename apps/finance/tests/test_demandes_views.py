"""Écrans des dépenses du parc auto pré-approuvées (R2) : accès, soumission, décision, exécution."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.finance import demandes as services
from apps.finance.models import StatutDemandeDepense, StatutOrdreDecaissement
from apps.fleet.tests.factories import VehiculeFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _demande_manuelle(**surcharges):
    donnees = dict(
        categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="Pièce rare",
    )
    donnees.update(surcharges)
    return services.soumettre_demande(UserFactory(role=Role.PARCAUTO), **donnees)


@pytest.mark.parametrize(
    "role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.RH]
)
def test_les_demandes_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    demande = _demande_manuelle()

    for url in (reverse("finance:demandes"), reverse("finance:demande", args=[demande.pk])):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_demandes_sont_interdites_aux_autres_roles(client, role):
    _connecte(client, role)
    demande = _demande_manuelle()

    assert client.get(reverse("finance:demandes")).status_code == 403
    assert client.get(reverse("finance:demande", args=[demande.pk])).status_code == 403


def test_seul_le_parc_auto_voit_le_bouton_nouvelle_demande(client):
    _connecte(client, Role.PARCAUTO)
    assert "Nouvelle demande" in client.get(reverse("finance:demandes")).content.decode()

    _connecte(client, Role.FINANCES)
    assert "Nouvelle demande" not in client.get(reverse("finance:demandes")).content.decode()


def test_le_parc_auto_soumet_une_demande(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(
        reverse("finance:demande_nouvelle"),
        {"categorie": CategorieDepense.MAINTENANCE, "montant_estime": "150000", "motif": "Réparation externe"},
    )

    assert reponse.status_code == 302
    assert services.demandes_queryset().count() == 1


def test_la_direction_valide_une_demande_qui_genere_un_ordre(client):
    demande = _demande_manuelle()
    _connecte(client, Role.DIRECTION)

    reponse = client.post(
        reverse("finance:demande_decider", args=[demande.pk]), {"decision": "VALIDER", "montant_valide": ""}
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.VALIDEE
    assert demande.ordre_decaissement.statut == StatutOrdreDecaissement.A_EXECUTER


def test_la_direction_refuse_une_demande_avec_motif(client):
    demande = _demande_manuelle()
    _connecte(client, Role.DIRECTION)

    reponse = client.post(
        reverse("finance:demande_decider", args=[demande.pk]),
        {"decision": "REFUSER", "motif_refus": "Budget insuffisant ce mois-ci"},
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.REFUSEE


def test_la_finance_execute_un_ordre(client):
    demande = _demande_manuelle()
    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))
    ordre = demande.ordre_decaissement
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("finance:ordre_executer", args=[ordre.pk]),
        {"mode_paiement": ModePaiement.ESPECES, "montant_reel": "205000", "reference": "FAC-1"},
    )

    assert reponse.status_code == 302
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_un_depassement_via_l_ecran_bloque_puis_se_revalide(client):
    demande = _demande_manuelle(montant_estime=Decimal("200000"))
    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))
    ordre = demande.ordre_decaissement
    _connecte(client, Role.FINANCES)

    client.post(
        reverse("finance:ordre_executer", args=[ordre.pk]),
        {"mode_paiement": ModePaiement.ESPECES, "montant_reel": "300000"},
    )
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("finance:ordre_revalider", args=[ordre.pk]), {"montant_valide": "300000"})
    assert reponse.status_code == 302
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER


def test_la_direction_definit_une_enveloppe_via_l_ecran(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("finance:enveloppe_nouvelle"),
        {
            "categorie": CategorieDepense.CARBURANT, "vehicule": camion.pk,
            "annee": "2026", "mois": "9", "montant_plafond": "300000",
        },
    )

    assert reponse.status_code == 302
    assert services.enveloppes_queryset().count() == 1


def test_le_parc_auto_ne_voit_pas_l_ecran_des_enveloppes(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("finance:enveloppes")).status_code == 403
