"""Services clients : fiche, TVA, portefeuille, historique commercial."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services
from apps.customers.exceptions import ClientError
from apps.customers.models import Client, Interaction, MotifExoneration, TypeInteraction

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def _champs(**surcharges):
    champs = dict(
        raison_sociale="Cimaf CI",
        ncc_nif="CI-1234567A",
        contact_principal="Awa Coulibaly",
        telephone="+2250700000000",
        adresse="Abidjan, Plateau",
    )
    champs.update(surcharges)
    return champs


# --- création et modification ---


def test_creer_client_applique_la_tva_par_defaut_de_18_pourcent():
    client = services.creer_client(**_champs())

    assert client.taux_tva == Decimal("18.00")
    assert client.motif_exoneration == "" and client.charge_clientele is None


def test_creer_client_exonere_exige_un_motif():
    with pytest.raises(ClientError, match="motif d'exonération"):
        services.creer_client(**_champs(taux_tva=Decimal("0")))

    client = services.creer_client(
        **_champs(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.ONG)
    )
    assert client.motif_exoneration == MotifExoneration.ONG


def test_le_motif_est_efface_quand_la_tva_redevient_positive():
    client = services.creer_client(
        **_champs(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.EXPORT)
    )

    services.modifier_client(client, taux_tva=Decimal("18"))

    client.refresh_from_db()
    assert client.motif_exoneration == ""


@pytest.mark.parametrize("taux", [Decimal("-1"), Decimal("100.01")])
def test_le_taux_de_tva_doit_etre_entre_0_et_100(taux):
    with pytest.raises(ClientError, match="entre 0 et 100"):
        services.creer_client(**_champs(taux_tva=taux, motif_exoneration="AUTRE"))


def test_le_ncc_nif_est_unique_meme_parmi_les_clients_supprimes():
    ancien = ClientFactory(ncc_nif="CI-1234567A")

    with pytest.raises(ClientError, match="déjà utilisé"):
        services.creer_client(**_champs())
    ancien.delete()
    with pytest.raises(ClientError, match="déjà utilisé"):
        services.creer_client(**_champs())


def test_le_charge_clientele_doit_avoir_le_bon_role_et_etre_actif():
    with pytest.raises(ClientError, match="chargé clientèle"):
        services.creer_client(**_champs(charge_clientele=UserFactory(role=Role.FINANCES)))
    with pytest.raises(ClientError, match="chargé clientèle"):
        services.creer_client(
            **_champs(charge_clientele=UserFactory(role=Role.CHARGE_CLIENTELE, is_active=False))
        )

    charge = UserFactory(role=Role.CHARGE_CLIENTELE)
    assert services.creer_client(**_champs(charge_clientele=charge)).charge_clientele == charge


def test_modifier_client_ne_change_que_les_champs_fournis_et_garde_son_propre_nif():
    client = ClientFactory(ncc_nif="CI-0000001A", telephone="0100000000")

    services.modifier_client(client, raison_sociale="Nouveau nom", ncc_nif="CI-0000001A")

    client.refresh_from_db()
    assert client.raison_sociale == "Nouveau nom" and client.telephone == "0100000000"


def test_modifier_client_refuse_le_nif_d_un_autre_client():
    ClientFactory(ncc_nif="CI-0000002A")
    client = ClientFactory()

    with pytest.raises(ClientError, match="déjà utilisé"):
        services.modifier_client(client, ncc_nif="CI-0000002A")


# --- recherche ---


def test_rechercher_clients_par_texte_portefeuille_et_exoneration():
    charge = UserFactory(role=Role.CHARGE_CLIENTELE)
    a = ClientFactory(raison_sociale="Cimaf", charge_clientele=charge, contact_principal="Koffi")
    b = ClientFactory(raison_sociale="Solibra", taux_tva=Decimal("0"), motif_exoneration="ONG")

    assert list(services.rechercher_clients(recherche="cim")) == [a]
    assert list(services.rechercher_clients(recherche="koffi")) == [a]
    assert list(services.rechercher_clients(charge_clientele=charge)) == [a]
    assert list(services.rechercher_clients(exonere=True)) == [b]
    assert services.rechercher_clients().count() == 2


def test_la_liste_compte_interactions_et_reclamations_sans_doublons():
    client = ClientFactory()
    auteur = UserFactory(role=Role.CHARGE_CLIENTELE)
    for type_interaction in (TypeInteraction.APPEL, TypeInteraction.RECLAMATION, TypeInteraction.RECLAMATION):
        services.enregistrer_interaction(client, auteur, type_interaction=type_interaction, resume="x")
    supprimee = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.RECLAMATION, resume="à ignorer"
    )
    supprimee.delete()

    ligne = services.clients_queryset().get(pk=client.pk)

    assert (ligne.nb_interactions, ligne.nb_reclamations) == (3, 2)
    assert ligne.derniere_interaction is not None


def test_un_client_sans_interaction_a_des_compteurs_a_zero():
    ligne = services.clients_queryset().get(pk=ClientFactory().pk)

    assert (ligne.nb_interactions, ligne.nb_reclamations, ligne.derniere_interaction) == (0, 0, None)


def test_charges_clientele_ne_liste_que_les_comptes_actifs_de_ce_role():
    bon = UserFactory(role=Role.CHARGE_CLIENTELE)
    UserFactory(role=Role.CHARGE_CLIENTELE, is_active=False)
    UserFactory(role=Role.RH)

    assert list(services.charges_clientele()) == [bon]


# --- interactions ---


def test_enregistrer_interaction_par_defaut_a_l_instant_present():
    client, auteur = ClientFactory(), UserFactory(role=Role.CHARGE_CLIENTELE)

    interaction = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.DEMANDE_DEVIS, resume="Devis Abidjan-Bouaké"
    )

    assert interaction.auteur == auteur and interaction.client == client
    assert abs(timezone.now() - interaction.date_interaction) < timedelta(seconds=5)


def test_le_resume_d_une_interaction_est_obligatoire():
    with pytest.raises(ClientError, match="résumé"):
        services.enregistrer_interaction(
            ClientFactory(), UserFactory(), type_interaction=TypeInteraction.APPEL, resume="   "
        )
    assert not Interaction.objects.exists()


def test_une_interaction_ne_peut_pas_etre_datee_dans_le_futur():
    with pytest.raises(ClientError, match="futur"):
        services.enregistrer_interaction(
            ClientFactory(), UserFactory(), type_interaction=TypeInteraction.APPEL, resume="x",
            date_interaction=timezone.now() + timedelta(days=1),
        )


def test_les_interactions_sont_triees_de_la_plus_recente_a_la_plus_ancienne():
    client, auteur = ClientFactory(), UserFactory()
    ancienne = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.MAIL, resume="a",
        date_interaction=timezone.now() - timedelta(days=3),
    )
    recente = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.APPEL, resume="b"
    )

    assert list(services.interactions_du_client(client)) == [recente, ancienne]


def test_clients_pour_selection_est_trie_par_raison_sociale():
    ClientFactory(raison_sociale="Zeta")
    ClientFactory(raison_sociale="Alpha")

    assert [c.raison_sociale for c in services.clients_pour_selection()] == ["Alpha", "Zeta"]
    assert Client.objects.count() == 2
