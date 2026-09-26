"""Écrans des devis (R5) : accès par rôle, cycle de vie, versions imprimable et modifiable."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import StatutProforma, SEUIL_VALIDATION_DIRECTION

from .helpers import (
    JOUR,
    charge_clientele,
    direction,
    finances,
    proforma_brouillon,
    proforma_envoyee,
    proforma_soumise,
    proforma_validee,
)

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _accepte(proforma):
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    return proforma


@pytest.mark.parametrize(
    "role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH, Role.CHARGE_CLIENTELE]
)
def test_les_devis_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    proforma = proforma_brouillon()

    for url in (
        reverse("billing:proformas"),
        reverse("billing:proforma", args=[proforma.pk]),
        reverse("billing:proforma_imprimer", args=[proforma.pk]),
    ):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_les_devis_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    proforma = proforma_brouillon()

    for url in (
        reverse("billing:proformas"),
        reverse("billing:proforma", args=[proforma.pk]),
        reverse("billing:proforma_nouveau"),
    ):
        assert client.get(url).status_code == 403, url


def test_la_rh_consulte_les_devis_sans_pouvoir_en_creer(client):
    """Retour réunion : la RH fait tout ce que fait la FINANCES (consultation), mais la
    préparation d'un devis reste réservée au chargé clientèle, à la DIRECTION et à l'ADMIN."""
    _connecte(client, Role.RH)
    proforma = proforma_brouillon()

    for url in (reverse("billing:proformas"), reverse("billing:proforma", args=[proforma.pk])):
        assert client.get(url).status_code == 200, url
    assert client.get(reverse("billing:proforma_nouveau")).status_code == 403


def test_seuls_charge_clientele_admin_et_direction_voient_le_bouton_nouveau_devis(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    assert "Nouveau devis" in client.get(reverse("billing:proformas")).content.decode()

    # Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie.
    _connecte(client, Role.DIRECTION)
    assert "Nouveau devis" in client.get(reverse("billing:proformas")).content.decode()

    _connecte(client, Role.FINANCES)
    assert "Nouveau devis" not in client.get(reverse("billing:proformas")).content.decode()


def test_creation_d_un_devis(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    from apps.customers.tests.factories import ClientFactory

    client_erp = ClientFactory()

    reponse = client.post(
        reverse("billing:proforma_nouveau"),
        {
            "client": client_erp.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Korhogo",
            "nature_marchandise": "Coton",
            "poids_t": "18",
            "prix_convenu": "450000",
        },
    )

    assert reponse.status_code == 302
    proforma = client_erp.proformas.get()
    assert proforma.statut == StatutProforma.BROUILLON


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda: proforma_brouillon(),
        lambda: proforma_soumise(),
        lambda: proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION)),
        lambda: proforma_validee(aujourd_hui=JOUR),
        lambda: proforma_envoyee(aujourd_hui=JOUR),
        lambda: _accepte(proforma_envoyee(aujourd_hui=JOUR)),
    ],
)
def test_la_fiche_devis_s_affiche_a_chaque_etape(client, fabrique):
    _connecte(client, Role.DIRECTION)
    proforma = fabrique()

    reponse = client.get(reverse("billing:proforma", args=[proforma.pk]))

    assert reponse.status_code == 200
    assert proforma.get_statut_display() in reponse.content.decode()


def test_la_fiche_devis_accepte_et_refuse(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.get(reverse("billing:proforma", args=[proforma.pk]))
    assert reponse.status_code == 200


def test_modification_par_le_chargé_clientele(client):
    proforma = proforma_brouillon(prix="300000")
    compte = _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(
        reverse("billing:proforma_modifier", args=[proforma.pk]),
        {
            "lieu_chargement": proforma.lieu_chargement,
            "lieu_livraison": proforma.lieu_livraison,
            "nature_marchandise": proforma.nature_marchandise,
            "poids_t": str(proforma.poids_t),
            "prix_convenu": "350000",
            "taux_tva": str(proforma.taux_tva),
            "motif_exoneration": "",
        },
    )

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.prix_convenu == Decimal("350000")


def test_cycle_complet_soumission_validation_envoi_decision(client):
    proforma = proforma_brouillon(prix="300000")

    _connecte(client, Role.CHARGE_CLIENTELE)
    reponse = client.post(reverse("billing:proforma_soumettre", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.SOUMISE

    _connecte(client, Role.FINANCES)
    reponse = client.post(reverse("billing:proforma_valider_finances", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.VALIDEE and proforma.numero

    _connecte(client, Role.CHARGE_CLIENTELE)
    reponse = client.post(reverse("billing:proforma_envoyer_client", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.ENVOYEE_CLIENT

    reponse = client.post(
        reverse("billing:proforma_decision_client", args=[proforma.pk]),
        {"decision": "ACCEPTEE", "motif": ""},
    )
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.ACCEPTEE


def test_devis_au_dela_du_seuil_transite_par_la_direction(client):
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))

    _connecte(client, Role.FINANCES)
    client.post(reverse("billing:proforma_valider_finances", args=[proforma.pk]))
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("billing:proforma_valider_direction", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.VALIDEE and proforma.numero


def test_contre_proposition_renvoie_au_chargé_clientele(client):
    proforma = proforma_soumise()
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("billing:proforma_contre_proposer", args=[proforma.pk]), {"motif": "Prix trop bas"}
    )

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.CONTRE_PROPOSEE


def test_creer_la_mission_depuis_un_devis_accepte(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(reverse("billing:proforma_creer_mission", args=[proforma.pk]))

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.CONVERTIE
    assert proforma.mission_creee.client == proforma.client


def test_creer_la_mission_est_interdit_aux_roles_hors_creation_mission(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("billing:proforma_creer_mission", args=[proforma.pk]))

    assert reponse.status_code == 403


def test_abandonner_un_devis(client):
    proforma = proforma_brouillon()
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(reverse("billing:proforma_abandonner", args=[proforma.pk]))

    assert reponse.status_code == 302
    from apps.billing.models import Proforma

    assert not Proforma.objects.filter(pk=proforma.pk).exists()
