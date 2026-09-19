"""Facturation : préparation, TVA à 3 niveaux, validation, numérotation, règlements."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.exceptions import (
    ActionFactureNonAutorisee,
    FactureNonFacturable,
    MontantInvalide,
    ReglementInvalide,
    TransitionFactureInterdite,
)
from apps.billing.models import Facture, LigneFacture, ModePaiement, Reglement, StatutFacture
from apps.customers.tests.factories import ClientFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .helpers import JOUR, a_valider, brouillon, direction, emise, finances, mission_livree

pytestmark = pytest.mark.django_db


# --- missions facturables ---


def test_seules_les_missions_livrees_ou_cloturees_sans_facture_sont_facturables():
    livree = mission_livree()
    cloturee = mission_livree(statut=StatutMission.CLOTUREE)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    deja = mission_livree()
    services.creer_facture(deja, finances())

    assert set(services.missions_facturables()) == {livree, cloturee}


def test_une_mission_non_livree_ne_peut_pas_etre_facturee():
    mission = MissionFactory(statut=StatutMission.PLANIFIEE)

    with pytest.raises(FactureNonFacturable, match="pas encore livrée"):
        services.creer_facture(mission, finances())


def test_une_mission_ne_peut_avoir_qu_une_facture():
    mission = mission_livree()
    services.creer_facture(mission, finances())

    with pytest.raises(FactureNonFacturable, match="déjà une facture"):
        services.creer_facture(mission, finances())


def test_seuls_finances_et_admin_preparent_une_facture():
    for role in (Role.DIRECTION, Role.RH, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR):
        with pytest.raises(ActionFactureNonAutorisee):
            services.creer_facture(mission_livree(), UserFactory(role=role))
    assert services.creer_facture(mission_livree(), UserFactory(role=Role.ADMIN)).pk
    superutilisateur = UserFactory(role="", is_superuser=True)
    assert services.creer_facture(mission_livree(), superutilisateur).pk


# --- contenu du brouillon et TVA à 3 niveaux ---


def test_le_brouillon_reprend_le_client_la_prestation_et_la_tva_du_client():
    client = ClientFactory(delai_paiement_jours=45)
    mission = mission_livree(prix="1000000", client=client, lieu_chargement="Abidjan", lieu_livraison="Bouaké")

    facture = services.creer_facture(mission, finances())

    assert facture.statut == StatutFacture.BROUILLON and facture.numero == ""
    assert facture.client == client and facture.mission == mission
    assert facture.delai_paiement_jours == 45
    (ligne,) = facture.lignes.all()
    assert "Abidjan → Bouaké" in ligne.designation and mission.numero in ligne.designation
    assert (facture.montant_ht, facture.montant_tva, facture.montant_ttc) == (
        Decimal("1000000"), Decimal("180000"), Decimal("1180000"),
    )


def test_niveau_client_la_tva_du_client_s_applique_a_la_facture():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration="EXPORT")

    facture = services.creer_facture(mission_livree(client=client), finances())

    assert facture.taux_tva == 0 and facture.motif_exoneration == "EXPORT"
    assert facture.montant_tva == 0 and facture.montant_ttc == facture.montant_ht


def test_niveau_facture_la_tva_se_modifie_sur_le_brouillon():
    facture = brouillon()

    services.modifier_conditions(
        facture, finances(), taux_tva=Decimal("10"), delai_paiement_jours=15
    )

    facture.refresh_from_db()
    assert (facture.taux_tva, facture.montant_tva, facture.montant_ttc) == (
        Decimal("10"), Decimal("100000"), Decimal("1100000"),
    )
    assert facture.delai_paiement_jours == 15


def test_tva_zero_exige_un_motif_et_le_motif_est_efface_si_la_tva_redevient_positive():
    facture = brouillon()
    acteur = finances()

    with pytest.raises(MontantInvalide, match="motif d'exonération"):
        services.modifier_conditions(facture, acteur, taux_tva=Decimal("0"), delai_paiement_jours=30)

    services.modifier_conditions(
        facture, acteur, taux_tva=Decimal("0"), motif_exoneration="ONG", delai_paiement_jours=30
    )
    assert facture.motif_exoneration == "ONG" and facture.montant_ttc == facture.montant_ht
    services.modifier_conditions(facture, acteur, taux_tva=Decimal("18"), delai_paiement_jours=30)
    assert facture.motif_exoneration == ""


@pytest.mark.parametrize("taux", [Decimal("-1"), Decimal("101")])
def test_taux_de_tva_hors_bornes(taux):
    with pytest.raises(MontantInvalide, match="entre 0 et 100"):
        services.modifier_conditions(brouillon(), finances(), taux_tva=taux, delai_paiement_jours=30)


@pytest.mark.parametrize("delai", [0, 366])
def test_delai_de_paiement_hors_bornes(delai):
    with pytest.raises(MontantInvalide, match="entre 1 et 365"):
        services.modifier_conditions(
            brouillon(), finances(), taux_tva=Decimal("18"), delai_paiement_jours=delai
        )


def test_la_tva_est_arrondie_au_franc():
    facture = brouillon(prix="1005")  # 18 % de 1005 = 180,9

    assert facture.montant_tva == Decimal("181") and facture.montant_ttc == Decimal("1186")


def test_ajouter_et_supprimer_des_lignes_recalcule_les_totaux():
    facture = brouillon(prix="1000000")
    acteur = finances()

    peage = services.ajouter_ligne(
        facture, acteur, designation="Péages refacturés", quantite=Decimal("2"), prix_unitaire_ht=Decimal("7500.50")
    )

    facture.refresh_from_db()
    assert peage.montant_ht == Decimal("15001")  # 2 x 7500,50 arrondi au franc
    assert facture.montant_ht == Decimal("1015001") and facture.montant_tva == Decimal("182700")
    services.supprimer_ligne(peage, acteur)
    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1000000")
    assert LigneFacture.objects.filter(facture=facture).count() == 1


@pytest.mark.parametrize(
    ("designation", "quantite", "prix", "message"),
    [
        ("  ", "1", "10", "désignation"),
        ("x", "0", "10", "quantité"),
        ("x", "-1", "10", "quantité"),
        ("x", "1", "-5", "prix"),
    ],
)
def test_lignes_invalides(designation, quantite, prix, message):
    with pytest.raises(MontantInvalide, match=message):
        services.ajouter_ligne(
            brouillon(), finances(), designation=designation,
            quantite=Decimal(quantite), prix_unitaire_ht=Decimal(prix),
        )


def test_seul_un_brouillon_se_modifie():
    facture = a_valider()
    acteur = finances()

    with pytest.raises(TransitionFactureInterdite):
        services.ajouter_ligne(facture, acteur, designation="x", quantite=Decimal(1), prix_unitaire_ht=Decimal(1))
    with pytest.raises(TransitionFactureInterdite):
        services.modifier_conditions(facture, acteur, taux_tva=Decimal("18"), delai_paiement_jours=30)
    with pytest.raises(TransitionFactureInterdite):
        services.supprimer_ligne(facture.lignes.first(), acteur)
    with pytest.raises(TransitionFactureInterdite):
        services.abandonner_brouillon(facture, acteur)


def test_les_modifications_sont_reservees_a_finances_et_admin():
    facture = brouillon()
    ligne = facture.lignes.first()

    for action in (
        lambda u: services.ajouter_ligne(facture, u, designation="x", quantite=Decimal(1), prix_unitaire_ht=Decimal(1)),
        lambda u: services.supprimer_ligne(ligne, u),
        lambda u: services.modifier_conditions(facture, u, taux_tva=Decimal("18"), delai_paiement_jours=30),
        lambda u: services.soumettre(facture, u),
        lambda u: services.abandonner_brouillon(facture, u),
    ):
        with pytest.raises(ActionFactureNonAutorisee):
            action(direction())


def test_abandonner_un_brouillon_libere_la_mission_sans_trou_de_numerotation():
    mission = mission_livree()
    facture = services.creer_facture(mission, finances())

    services.abandonner_brouillon(facture, finances())

    assert not Facture.objects.filter(pk=facture.pk).exists()
    assert mission in services.missions_facturables()
    nouvelle = services.creer_facture(mission, finances())
    assert nouvelle.pk != facture.pk


# --- validation par la direction ---


def test_soumettre_envoie_le_brouillon_a_la_direction():
    facture = brouillon()

    services.soumettre(facture, finances())

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and facture.numero == ""


def test_une_facture_a_zero_ne_peut_pas_etre_soumise():
    facture = brouillon(prix="0")

    with pytest.raises(MontantInvalide, match="0 FCFA"):
        services.soumettre(facture, finances())


def test_seule_la_direction_valide_et_attribue_le_numero_et_l_echeance():
    facture = a_valider()
    for role in (Role.FINANCES, Role.ADMIN, Role.RH):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider(facture, UserFactory(role=role))
    superadmin = UserFactory(role="", is_superuser=True)
    with pytest.raises(ActionFactureNonAutorisee):
        services.valider(facture, superadmin)  # un superutilisateur agit en ADMIN : pas de validation
    chef = direction()

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert facture.numero == "FACT-2026-0001"
    assert facture.date_emission == date(2026, 9, 1)
    assert facture.date_echeance == date(2026, 10, 1)  # + 30 jours (délai du client)
    assert facture.validee_par == chef and facture.date_validation is not None


def test_l_echeance_suit_le_delai_de_paiement_de_la_facture():
    facture = brouillon()
    services.modifier_conditions(facture, finances(), taux_tva=Decimal("18"), delai_paiement_jours=45)
    services.soumettre(facture, finances())

    services.valider(facture, direction(), aujourd_hui=date(2026, 9, 1))

    assert facture.date_echeance == date(2026, 10, 16)


def test_la_numerotation_est_sequentielle_par_annee_et_sans_trou():
    premiere = emise(aujourd_hui=date(2026, 12, 30))
    abandonnee = brouillon()
    services.abandonner_brouillon(abandonnee, finances())
    deuxieme = emise(aujourd_hui=date(2026, 12, 31))
    nouvelle_annee = emise(aujourd_hui=date(2027, 1, 2))

    assert [premiere.numero, deuxieme.numero, nouvelle_annee.numero] == [
        "FACT-2026-0001", "FACT-2026-0002", "FACT-2027-0001",
    ]


def test_on_ne_valide_qu_une_facture_a_valider():
    for facture in (brouillon(), emise()):
        with pytest.raises(TransitionFactureInterdite):
            services.valider(facture, direction())


def test_la_direction_refuse_avec_un_motif_et_la_facture_redevient_brouillon():
    facture = a_valider()

    with pytest.raises(MontantInvalide, match="motif"):
        services.refuser(facture, direction(), motif="  ")
    services.refuser(facture, direction(), motif="Prix à revoir")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.BROUILLON and facture.motif_refus == "Prix à revoir"
    services.soumettre(facture, finances())
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and facture.motif_refus == ""


def test_seule_la_direction_refuse():
    facture = a_valider()

    with pytest.raises(ActionFactureNonAutorisee):
        services.refuser(facture, finances(), motif="Non")


def test_les_contraintes_de_la_base_protegent_les_regles_essentielles():
    facture = brouillon()
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(taux_tva=0, motif_exoneration="")
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(montant_ttc=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.filter(pk=facture.pk).update(statut=StatutFacture.EMISE)  # sans numéro ni dates
    with pytest.raises(IntegrityError), transaction.atomic():
        Facture.objects.create(
            client=facture.client, mission=facture.mission, taux_tva=18, delai_paiement_jours=30
        )


# --- règlements ---


def _regler(facture, montant, *, mode=ModePaiement.VIREMENT, jour=JOUR, acteur=None, **kw):
    return services.enregistrer_reglement(
        facture, acteur or finances(), montant=Decimal(montant), mode=mode, date_reglement=jour, **kw
    )


def test_acompte_puis_solde_mettent_a_jour_le_statut_et_le_reste_a_recouvrer():
    facture = emise(prix="1000000")  # TTC 1 180 000

    _regler(facture, "500000", reference="VIR-1")
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert services.reste_a_recouvrer(facture) == Decimal("680000")
    assert services.montant_regle(facture) == Decimal("500000")

    _regler(facture, "680000", mode=ModePaiement.WAVE)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE
    assert services.reste_a_recouvrer(facture) == 0


def test_un_reglement_ne_peut_pas_depasser_le_reste_a_recouvrer():
    facture = emise(prix="1000000")
    _regler(facture, "1000000")

    with pytest.raises(ReglementInvalide, match="dépasse le reste à recouvrer"):
        _regler(facture, "200000")
    assert Reglement.objects.count() == 1


@pytest.mark.parametrize("montant", ["0", "-10"])
def test_un_montant_de_reglement_doit_etre_positif(montant):
    with pytest.raises(ReglementInvalide, match="strictement positif"):
        _regler(emise(), montant)


def test_pas_de_reglement_avant_l_emission_ni_dans_le_futur():
    facture = emise(aujourd_hui=JOUR)

    with pytest.raises(ReglementInvalide, match="précéder"):
        _regler(facture, "1000", jour=JOUR - timedelta(days=1))
    with pytest.raises(ReglementInvalide, match="futur"):
        _regler(facture, "1000", jour=timezone.localdate() + timedelta(days=1))


def test_pas_de_reglement_sur_un_brouillon_ni_une_facture_a_valider_ni_soldee():
    for facture in (brouillon(), a_valider()):
        with pytest.raises(ReglementInvalide, match="Impossible d'enregistrer"):
            _regler(facture, "1000")
    soldee = emise(prix="1000")
    _regler(soldee, "1180")
    with pytest.raises(ReglementInvalide):
        _regler(soldee, "1")


def test_les_reglements_sont_reserves_a_finances_et_admin():
    facture = emise()

    with pytest.raises(ActionFactureNonAutorisee):
        _regler(facture, "1000", acteur=direction())
    assert _regler(facture, "1000", acteur=UserFactory(role=Role.ADMIN)).pk


def test_annuler_un_reglement_restitue_le_reste_et_le_statut():
    facture = emise(prix="1000000")
    reglement = _regler(facture, "1180000")
    assert facture.statut == StatutFacture.PAYEE

    services.annuler_reglement(reglement, finances(), motif="Chèque sans provision")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert services.reste_a_recouvrer(facture) == Decimal("1180000")
    assert not Reglement.objects.filter(pk=reglement.pk).exists()
    ancien = Reglement.all_objects.get(pk=reglement.pk)
    assert ancien.is_deleted and ancien.motif_annulation == "Chèque sans provision"


def test_annuler_un_seul_de_deux_reglements_laisse_la_facture_partiellement_payee():
    facture = emise(prix="1000000")
    premier, _ = _regler(facture, "300000"), _regler(facture, "200000")

    services.annuler_reglement(premier, finances(), motif="Erreur de saisie")

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert services.reste_a_recouvrer(facture) == Decimal("980000")


def test_annulation_de_reglement_exige_un_motif_et_le_bon_role():
    reglement = _regler(emise(), "1000")

    with pytest.raises(ReglementInvalide, match="motif"):
        services.annuler_reglement(reglement, finances(), motif=" ")
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_reglement(reglement, direction(), motif="Test")


# --- lecture et recherche ---


def test_est_echue_seulement_si_emise_non_soldee_et_apres_l_echeance():
    facture = emise(aujourd_hui=JOUR)  # échéance 2026-10-01

    assert not services.est_echue(facture, date(2026, 10, 1))  # le jour même : pas encore
    assert services.est_echue(facture, date(2026, 10, 2))
    _regler(facture, "1180000")
    assert not services.est_echue(facture, date(2026, 12, 1))  # soldée
    assert not services.est_echue(brouillon(), date(2030, 1, 1))


def test_factures_echues_et_creances():
    payee, en_retard, a_jour = emise(aujourd_hui=JOUR), emise(aujourd_hui=JOUR), emise(aujourd_hui=date(2026, 9, 25))
    _regler(payee, "1180000")
    _regler(en_retard, "180000")
    brouillon()  # pas une créance

    situation = services.creances(date(2026, 10, 5))

    assert set(services.factures_echues(date(2026, 10, 5))) == {en_retard}
    assert situation == {
        "total": Decimal("2180000"),  # 1 000 000 restant + 1 180 000 non réglé (TTC)
        "nombre": 2,
        "echu": Decimal("1000000"),
        "nombre_echues": 1,
    }
    assert a_jour.numero  # émise mais pas échue


def test_rechercher_factures_par_texte_statut_client_et_echeance():
    client = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    a = emise(client=client)
    b = emise()
    brouillon()

    assert list(services.rechercher_factures(recherche="cimaf")) == [a]
    assert list(services.rechercher_factures(recherche=a.numero.lower())) == [a]
    assert list(services.rechercher_factures(recherche=b.mission.numero)) == [b]
    assert list(services.rechercher_factures(client=client)) == [a]
    assert services.rechercher_factures(statut=StatutFacture.EMISE).count() == 2
    assert services.rechercher_factures(statut="INCONNU").count() == 3  # ignoré
    assert services.rechercher_factures(echues=True, aujourd_hui=date(2026, 10, 2)).count() == 2
    assert services.rechercher_factures(echues=True, aujourd_hui=date(2026, 9, 2)).count() == 0


def test_le_reste_et_le_regle_sont_calcules_en_une_requete(django_assert_num_queries):
    facture = emise()
    _regler(facture, "100000")

    with django_assert_num_queries(1):
        ligne = list(services.factures_queryset())[0]
        assert (ligne.montant_regle, ligne.reste) == (Decimal("100000"), Decimal("1080000"))


def test_chiffre_d_affaires_et_encaissements_de_la_periode():
    emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    hors_periode = emise(prix="500000", aujourd_hui=date(2026, 8, 20))
    brouillon(prix="9000000")
    _regler(hors_periode, "100000", jour=date(2026, 8, 25))
    _regler(hors_periode, "200000", jour=date(2026, 9, 3))

    assert services.chiffre_affaires(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("1000000")
    assert services.encaissements(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("200000")
    assert services.chiffre_affaires(date(2026, 1, 1), date(2026, 1, 31)) == 0


# --- dépenses ---


def test_enregistrer_une_depense_et_totaux_par_categorie():
    acteur = finances()
    for categorie, montant in (("PEAGES", "15000"), ("PEAGES", "5000"), ("ENTRETIEN", "80000")):
        services.enregistrer_depense(
            acteur, categorie=categorie, date_depense=date(2026, 9, 5), libelle=f"{categorie} test",
            montant=Decimal(montant), mode=ModePaiement.ESPECES,
        )

    par_categorie = {c["code"]: c["total"] for c in services.depenses_par_categorie(date(2026, 9, 1), date(2026, 9, 30))}

    assert par_categorie == {"PEAGES": 20000, "ENTRETIEN": 80000, "FRAIS_ADMIN": 0, "AUTRE": 0}
    assert services.total_depenses(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("100000")
    assert services.total_depenses(date(2026, 10, 1), date(2026, 10, 31)) == 0


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        (" ", "1000", date(2026, 9, 1), "libellé"),
        ("x", "0", date(2026, 9, 1), "strictement positif"),
        ("x", "1000", date(2999, 1, 1), "futur"),
    ],
)
def test_depenses_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        services.enregistrer_depense(
            finances(), categorie="PEAGES", date_depense=jour, libelle=libelle,
            montant=Decimal(montant), mode=ModePaiement.ESPECES,
        )


def test_les_depenses_sont_reservees_a_finances_et_admin():
    with pytest.raises(ActionFactureNonAutorisee):
        services.enregistrer_depense(
            direction(), categorie="PEAGES", date_depense=date(2026, 9, 1), libelle="x",
            montant=Decimal("1"), mode=ModePaiement.ESPECES,
        )


def test_recherche_de_depenses_par_texte_categorie_et_periode():
    acteur = finances()
    mission = mission_livree()
    services.enregistrer_depense(acteur, categorie="PEAGES", date_depense=date(2026, 9, 5),
                                 libelle="Péage Yamoussoukro", montant=Decimal("5000"),
                                 mode=ModePaiement.ESPECES, mission=mission)
    services.enregistrer_depense(acteur, categorie="FRAIS_ADMIN", date_depense=date(2026, 8, 5),
                                 libelle="Timbres", montant=Decimal("1000"), mode=ModePaiement.ESPECES)

    assert services.rechercher_depenses(recherche="peage").count() == 1
    assert services.rechercher_depenses(recherche=mission.numero).count() == 1
    assert services.rechercher_depenses(categorie="FRAIS_ADMIN").count() == 1
    assert services.rechercher_depenses(date_debut=date(2026, 9, 1)).count() == 1
    assert services.rechercher_depenses(date_fin=date(2026, 8, 31)).count() == 1


# --- alerte de signal ---


def test_un_recepteur_en_erreur_ne_bloque_jamais_la_facturation(caplog):
    from apps.billing import signals

    def panne(sender, **kwargs):
        raise RuntimeError("panne")

    signals.facture_a_valider.connect(panne, weak=False)
    signals.facture_validee.connect(panne, weak=False)
    signals.facture_refusee.connect(panne, weak=False)
    try:
        facture = brouillon()
        services.soumettre(facture, finances())
        services.refuser(facture, direction(), motif="x")
        services.soumettre(facture, finances())
        services.valider(facture, direction(), aujourd_hui=JOUR)
    finally:
        for signal in (signals.facture_a_valider, signals.facture_validee, signals.facture_refusee):
            signal.disconnect(panne)

    assert facture.statut == StatutFacture.EMISE and "en erreur" in caplog.text
