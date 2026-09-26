"""Devis (R5) : préparation par le chargé clientèle, validation finance/direction, cycle client.

Séparation des tâches (avenant-separation-des-taches.md) : celui qui fixe le prix (chargé
clientèle) n'est jamais celui qui le valide (finance, et direction au-delà du seuil).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.billing import services
from apps.billing.exceptions import (
    ActionFactureNonAutorisee,
    MontantInvalide,
    TransitionFactureInterdite,
)
from apps.billing.models import STATUTS_PROFORMA_MODIFIABLES, Proforma, SEUIL_VALIDATION_DIRECTION, StatutProforma
from apps.customers.tests.factories import ClientFactory

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


# --- préparation ---


def test_seuls_charge_clientele_et_admin_preparent_un_devis():
    for role in (Role.DIRECTION, Role.RH, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR):
        with pytest.raises(ActionFactureNonAutorisee):
            proforma_brouillon(acteur=UserFactory(role=role))
    assert proforma_brouillon(acteur=UserFactory(role=Role.ADMIN)).pk
    superutilisateur = UserFactory(role="", is_superuser=True)
    assert proforma_brouillon(acteur=superutilisateur).pk


def test_le_brouillon_reprend_le_client_et_sa_tva():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    proforma = proforma_brouillon(client=client, prix="500000")

    assert proforma.statut == StatutProforma.BROUILLON and proforma.numero == ""
    assert proforma.client == client
    assert proforma.taux_tva == 0 and proforma.motif_exoneration == "EXPORT"
    assert proforma.montant_ht == Decimal("500000")
    assert proforma.montant_tva == 0 and proforma.montant_ttc == Decimal("500000")


def test_la_tva_du_client_par_defaut_se_calcule():
    proforma = proforma_brouillon(prix="300000")  # TVA client par défaut 18 %

    assert (proforma.montant_ht, proforma.montant_tva, proforma.montant_ttc) == (
        Decimal("300000"), Decimal("54000"), Decimal("354000"),
    )


@pytest.mark.parametrize("poids", [Decimal("0"), Decimal("-1")])
def test_poids_positif_obligatoire(poids):
    with pytest.raises(MontantInvalide, match="poids"):
        proforma_brouillon(poids_t=poids)


def test_prix_negatif_refuse():
    with pytest.raises(MontantInvalide, match="négatif"):
        proforma_brouillon(prix="-1")


# --- modification ---


def test_modification_recalcule_les_montants():
    proforma = proforma_brouillon(prix="300000")

    services.modifier_proforma(
        proforma, charge_clientele(),
        lieu_chargement="San-Pédro", lieu_livraison="Yamoussoukro", nature_marchandise="Bois",
        poids_t=Decimal("15"), prix_convenu=Decimal("400000"),
        taux_tva=Decimal("10"), motif_exoneration="",
    )

    proforma.refresh_from_db()
    assert proforma.lieu_chargement == "San-Pédro" and proforma.lieu_livraison == "Yamoussoukro"
    assert (proforma.montant_ht, proforma.montant_tva, proforma.montant_ttc) == (
        Decimal("400000"), Decimal("40000"), Decimal("440000"),
    )


def test_modification_impossible_une_fois_soumis():
    proforma = proforma_soumise()

    with pytest.raises(TransitionFactureInterdite):
        services.modifier_proforma(
            proforma, charge_clientele(),
            lieu_chargement="X", lieu_livraison="Y", nature_marchandise="Z",
            poids_t=Decimal("1"), prix_convenu=Decimal("1"), taux_tva=Decimal("18"),
        )


def test_modification_tva_zero_exige_un_motif():
    proforma = proforma_brouillon()

    with pytest.raises(MontantInvalide, match="motif d'exonération"):
        services.modifier_proforma(
            proforma, charge_clientele(),
            lieu_chargement=proforma.lieu_chargement, lieu_livraison=proforma.lieu_livraison,
            nature_marchandise=proforma.nature_marchandise, poids_t=proforma.poids_t,
            prix_convenu=proforma.prix_convenu, taux_tva=Decimal("0"),
        )


def test_contre_proposee_reste_modifiable():
    assert StatutProforma.CONTRE_PROPOSEE in STATUTS_PROFORMA_MODIFIABLES


# --- abandon ---


def test_abandonner_un_brouillon_le_supprime_logiquement():
    proforma = proforma_brouillon()

    services.abandonner_proforma(proforma, charge_clientele())

    assert not Proforma.objects.filter(pk=proforma.pk).exists()
    assert Proforma.all_objects.get(pk=proforma.pk).is_deleted


def test_abandonner_refuse_une_fois_soumis():
    proforma = proforma_soumise()

    with pytest.raises(TransitionFactureInterdite):
        services.abandonner_proforma(proforma, charge_clientele())


# --- soumission ---


def test_soumettre_depuis_brouillon():
    proforma = proforma_brouillon()

    services.soumettre_proforma(proforma, charge_clientele())

    assert proforma.statut == StatutProforma.SOUMISE


def test_soumettre_un_devis_a_zero_franc_refuse():
    proforma = proforma_brouillon(prix="0")

    with pytest.raises(MontantInvalide, match="0 FCFA"):
        services.soumettre_proforma(proforma, charge_clientele())


def test_resoumission_efface_le_motif_de_contre_proposition():
    proforma = proforma_soumise()
    services.contre_proposer_proforma(proforma, finances(), motif="Prix trop bas")
    assert proforma.motif_contre_proposition

    services.soumettre_proforma(proforma, charge_clientele())

    assert proforma.statut == StatutProforma.SOUMISE and proforma.motif_contre_proposition == ""


# --- validation finance / direction ---


def test_seule_la_finance_valide_en_premier_lieu():
    proforma = proforma_soumise()
    for acteur in (charge_clientele(), direction(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider_proforma(proforma, acteur)


def test_validation_sous_le_seuil_emet_directement():
    proforma = proforma_soumise(prix="300000")  # TTC 354 000 < seuil

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    assert proforma.statut == StatutProforma.VALIDEE
    assert proforma.numero.startswith(f"PRO-{JOUR.year}-")
    assert proforma.valide_par_finances is not None and proforma.date_validation_finances is not None
    assert proforma.valide_par_direction is None


def test_validation_au_dela_du_seuil_transmet_a_la_direction():
    prix_ht = SEUIL_VALIDATION_DIRECTION  # TTC = 1,18x le seuil HT, donc > seuil après TVA
    proforma = proforma_soumise(prix=str(prix_ht))

    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    assert proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION
    assert proforma.numero == ""
    assert proforma.valide_par_finances is not None


def test_seule_la_direction_valide_au_dela_du_seuil():
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))
    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    for acteur in (charge_clientele(), finances(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider_proforma_direction(proforma, acteur)

    services.valider_proforma_direction(proforma, direction(), aujourd_hui=JOUR)
    assert proforma.statut == StatutProforma.VALIDEE
    assert proforma.numero.startswith(f"PRO-{JOUR.year}-")
    assert proforma.valide_par_direction is not None


def test_validation_direction_impossible_hors_attente_direction():
    proforma = proforma_soumise()  # sous le seuil : jamais passé par EN_ATTENTE_DIRECTION

    with pytest.raises(TransitionFactureInterdite):
        services.valider_proforma_direction(proforma, direction())


def test_numeros_incrementent_par_annee():
    p1 = proforma_soumise()
    p2 = proforma_soumise()
    services.valider_proforma(p1, finances(), aujourd_hui=JOUR)
    services.valider_proforma(p2, finances(), aujourd_hui=JOUR)

    n1, n2 = int(p1.numero.rsplit("-", 1)[1]), int(p2.numero.rsplit("-", 1)[1])
    assert n2 == n1 + 1


# --- contre-proposition ---


def test_finance_contre_propose_un_devis_soumis():
    proforma = proforma_soumise()

    services.contre_proposer_proforma(proforma, finances(), motif="Le tarif au km est trop bas.")

    assert proforma.statut == StatutProforma.CONTRE_PROPOSEE
    assert proforma.motif_contre_proposition == "Le tarif au km est trop bas."


def test_direction_contre_propose_un_devis_en_attente():
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))
    services.valider_proforma(proforma, finances(), aujourd_hui=JOUR)

    services.contre_proposer_proforma(proforma, direction(), motif="Trop risqué pour ce client.")

    assert proforma.statut == StatutProforma.CONTRE_PROPOSEE


def test_contre_proposition_refusee_hors_etats_valides():
    proforma = proforma_brouillon()

    with pytest.raises(TransitionFactureInterdite):
        services.contre_proposer_proforma(proforma, finances(), motif="x")


def test_contre_proposition_le_mauvais_role_est_refuse():
    proforma = proforma_soumise()

    with pytest.raises(ActionFactureNonAutorisee):
        services.contre_proposer_proforma(proforma, direction(), motif="x")


def test_motif_de_contre_proposition_obligatoire():
    proforma = proforma_soumise()

    with pytest.raises(MontantInvalide, match="motif"):
        services.contre_proposer_proforma(proforma, finances(), motif="   ")


# --- envoi et décision du client ---


def test_envoyer_au_client_depuis_valide_seulement():
    proforma = proforma_soumise()

    with pytest.raises(TransitionFactureInterdite):
        services.envoyer_proforma_au_client(proforma, charge_clientele())


def test_envoi_fixe_la_validite_a_30_jours():
    proforma = proforma_validee(aujourd_hui=JOUR)

    services.envoyer_proforma_au_client(proforma, charge_clientele(), aujourd_hui=JOUR)

    assert proforma.statut == StatutProforma.ENVOYEE_CLIENT
    assert proforma.date_envoi == JOUR
    assert proforma.date_validite == JOUR + timedelta(days=30)


def test_decision_client_acceptee():
    proforma = proforma_envoyee(aujourd_hui=JOUR)

    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)

    assert proforma.statut == StatutProforma.ACCEPTEE


def test_decision_client_refusee_exige_un_motif():
    proforma = proforma_envoyee(aujourd_hui=JOUR)

    with pytest.raises(MontantInvalide, match="motif"):
        services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=False)

    services.enregistrer_decision_client(
        proforma, charge_clientele(), acceptee=False, motif="Trop cher"
    )
    assert proforma.statut == StatutProforma.REFUSEE and proforma.motif_refus_client == "Trop cher"


def test_decision_client_impossible_avant_envoi():
    proforma = proforma_validee(aujourd_hui=JOUR)

    with pytest.raises(TransitionFactureInterdite):
        services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)


# --- expiration (tâche quotidienne) ---


def test_expirer_proformas_au_dela_de_30_jours():
    proforma = proforma_envoyee(aujourd_hui=JOUR)

    nombre = services.expirer_proformas(aujourd_hui=JOUR + timedelta(days=31))

    proforma.refresh_from_db()
    assert nombre == 1 and proforma.statut == StatutProforma.EXPIREE


def test_expirer_proformas_ignore_celles_encore_valides():
    proforma_envoyee(aujourd_hui=JOUR)

    assert services.expirer_proformas(aujourd_hui=JOUR + timedelta(days=10)) == 0


def test_expirer_proformas_ignore_les_autres_statuts():
    proforma_validee(aujourd_hui=JOUR)  # jamais envoyée, pas de date de validité

    assert services.expirer_proformas(aujourd_hui=JOUR + timedelta(days=60)) == 0


# --- consultation ---


def test_rechercher_proformas_par_statut_et_client():
    client = ClientFactory()
    cible = proforma_brouillon(client=client)
    proforma_soumise()

    resultat = services.rechercher_proformas(statut=StatutProforma.BROUILLON, client=client)

    assert set(resultat) == {cible}


def test_historique_proforma_trace_creation_et_modifications():
    proforma = proforma_brouillon(prix="300000")
    services.modifier_proforma(
        proforma, charge_clientele(),
        lieu_chargement=proforma.lieu_chargement, lieu_livraison=proforma.lieu_livraison,
        nature_marchandise=proforma.nature_marchandise, poids_t=proforma.poids_t,
        prix_convenu=Decimal("350000"), taux_tva=proforma.taux_tva,
    )

    historique = list(services.historique_proforma(proforma))

    assert any(h.action == "CREATE" for h in historique)
    assert any(h.action == "UPDATE" and "prix_convenu" in h.nouvelle_valeur for h in historique)
    assert all(isinstance(h, AuditLog) and h.entite == "Proforma" for h in historique)
