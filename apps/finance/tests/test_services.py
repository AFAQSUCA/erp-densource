"""Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import JOUR, direction, emise, finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

SEPT = (date(2026, 9, 1), date(2026, 9, 30))


def _manuel(sens=SensMouvement.ENTREE, montant="100000", *, mode=ModePaiement.VIREMENT, jour=JOUR,
            libelle="Apport", acteur=None):
    return services.enregistrer_mouvement(
        acteur or finances(), sens=sens, date_mouvement=jour, libelle=libelle,
        montant=Decimal(montant), mode=mode,
    )


def _reglement(facture, montant, mode=ModePaiement.VIREMENT, jour=JOUR):
    return billing.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def _depense(montant, mode=ModePaiement.ESPECES, jour=JOUR, categorie="PEAGES"):
    return billing.enregistrer_depense(
        finances(), categorie=categorie, date_depense=jour, libelle="Péage", montant=Decimal(montant), mode=mode
    )


# --- mouvements manuels ---


def test_un_mouvement_manuel_s_enregistre_et_s_annule_avec_un_motif():
    mouvement = _manuel()

    services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert MouvementManuel.all_objects.get(pk=mouvement.pk).motif_annulation == "Doublon"


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        ("  ", "10", JOUR, "libellé"),
        ("x", "0", JOUR, "strictement positif"),
        ("x", "10", date(2999, 1, 1), "futur"),
    ],
)
def test_mouvements_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        _manuel(libelle=libelle, montant=montant, jour=jour)


def test_les_mouvements_sont_reserves_a_finances_et_admin():
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=direction())
    mouvement = _manuel()
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_mouvement(mouvement, direction(), motif="x")
    with pytest.raises(MontantInvalide, match="motif"):
        services.annuler_mouvement(mouvement, finances(), motif=" ")


# --- journal et soldes ---


def test_le_solde_reunit_reglements_depenses_et_mouvements_par_compte():
    facture = emise(prix="1000000")  # TTC 1 180 000
    _reglement(facture, "500000", ModePaiement.VIREMENT)
    _reglement(facture, "100000", ModePaiement.WAVE)
    _depense("20000", ModePaiement.ESPECES)
    _manuel(SensMouvement.ENTREE, "50000", mode=ModePaiement.ESPECES, libelle="Solde de caisse")
    _manuel(SensMouvement.SORTIE, "5000", mode=ModePaiement.VIREMENT, libelle="Frais bancaires")

    soldes = services.soldes_par_compte()

    assert soldes["BANQUE"] == Decimal("495000")  # 500 000 - 5 000
    assert soldes["CAISSE"] == Decimal("30000")  # 50 000 - 20 000
    assert soldes["MOBILE_MONEY"] == Decimal("100000")
    assert soldes["total"] == Decimal("625000")


def test_un_reglement_annule_ne_compte_plus():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "300000")
    billing.annuler_reglement(reglement, finances(), motif="Erreur")

    assert services.soldes_par_compte()["total"] == 0
    assert services.mouvements() == []


def test_le_journal_est_trie_et_decrit_chaque_origine():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", jour=date(2026, 9, 3))
    _depense("5000", jour=date(2026, 9, 5))
    _manuel(jour=date(2026, 9, 4), libelle="Apport")

    journal = services.mouvements()

    assert [(m["origine"], m["sens"]) for m in journal] == [
        ("DEPENSE", "SORTIE"), ("MANUEL", "ENTREE"), ("REGLEMENT", "ENTREE"),
    ]
    assert journal[2]["libelle"].startswith(f"Règlement {facture.numero} · ")
    assert journal[2]["compte"] == "BANQUE" and journal[0]["compte"] == "CAISSE"


def test_le_journal_se_filtre_par_periode_sens_et_compte():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.WAVE, date(2026, 9, 3))
    _depense("5000", ModePaiement.ESPECES, date(2026, 9, 10))
    _manuel(SensMouvement.SORTIE, "1000", mode=ModePaiement.VIREMENT, jour=date(2026, 9, 15), libelle="Frais")

    assert len(services.mouvements(date_debut=date(2026, 9, 5))) == 2
    assert len(services.mouvements(date_fin=date(2026, 9, 5))) == 1
    assert [m["origine"] for m in services.mouvements(sens="ENTREE")] == ["REGLEMENT"]
    assert sorted(m["origine"] for m in services.mouvements(sens="SORTIE")) == ["DEPENSE", "MANUEL"]
    assert [m["origine"] for m in services.mouvements(compte="MOBILE_MONEY")] == ["REGLEMENT"]
    assert services.mouvements(compte="CAISSE")[0]["origine"] == "DEPENSE"


def test_synthese_de_periode_entrees_sorties_variation():
    facture = emise(prix="1000000")
    _reglement(facture, "400000", jour=date(2026, 9, 3))
    _manuel(SensMouvement.ENTREE, "100000", jour=date(2026, 9, 4))
    _depense("30000", jour=date(2026, 9, 6))
    _manuel(SensMouvement.SORTIE, "20000", jour=date(2026, 9, 7), libelle="Frais")
    _depense("999", jour=date(2026, 8, 6))  # hors période

    assert services.synthese_periode(*SEPT) == {
        "entrees": Decimal("500000"), "sorties": Decimal("50000"), "variation": Decimal("450000"),
    }


def test_sans_mouvement_tout_est_a_zero():
    assert services.soldes_par_compte()["total"] == 0
    assert services.synthese_periode(*SEPT)["variation"] == 0


# --- charges et indicateurs ---


def _or_cloture(jour_cloture, main_oeuvre="30000", pieces=2):
    ordre = garage.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )
    article = ArticleFactory(reference=f"P-{ordre.pk}", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))
    stock.sortir_pour_or(article, quantite=pieces, ordre=ordre)
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal(main_oeuvre))
    type(ordre).objects.filter(pk=ordre.pk).update(
        date_cloture=timezone.now().replace(year=jour_cloture.year, month=jour_cloture.month, day=jour_cloture.day)
    )
    return ordre


def _plein(litres, prix, jour, camion=None, km=1000, ticket="T"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour, station="T",
        quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km, numero_ticket=ticket,
    )


def test_le_cout_du_carburant_est_litres_fois_prix_sur_la_periode():
    _plein("100", "655", date(2026, 9, 3), ticket="A")
    _plein("50", "660", date(2026, 9, 8), ticket="B")
    _plein("999", "700", date(2026, 8, 30), ticket="C")  # hors période

    assert fuel.cout_carburant(*SEPT) == Decimal("98500")  # 65 500 + 33 000


def test_le_cout_des_or_clotures_compte_main_d_oeuvre_et_pieces_de_la_periode():
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # 30 000 + 2 x 5 000
    _or_cloture(date(2026, 8, 10), main_oeuvre="99999", pieces=1)  # hors période

    assert stock.cout_des_or_clotures(*SEPT) == Decimal("40000")


def test_charges_regroupe_depenses_carburant_et_maintenance():
    _depense("20000", jour=date(2026, 9, 2))
    _plein("100", "655", date(2026, 9, 3))
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)

    charges = services.charges(*SEPT)

    assert charges == {
        "depenses": Decimal("20000"),
        "carburant": Decimal("65500"),
        "maintenance": Decimal("40000"),
        "total": Decimal("125500"),
    }


def test_indicateurs_du_mois():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    emise(prix="500000", aujourd_hui=date(2026, 9, 12))  # créance non échue au 20/09
    _reglement(facture, "600000", jour=date(2026, 9, 15))
    _depense("100000", jour=date(2026, 9, 5))

    kpi = services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))

    assert kpi["chiffre_affaires"] == Decimal("1500000")  # HT
    assert kpi["encaisse"] == Decimal("600000")
    assert kpi["charges"]["total"] == Decimal("100000")
    assert kpi["marge_nette"] == Decimal("1400000")
    assert kpi["creances"]["total"] == Decimal("1180000") - Decimal("600000") + Decimal("590000")
    assert kpi["creances"]["nombre_echues"] == 0
    assert kpi["tresorerie"] == Decimal("500000")  # 600 000 encaissés - 100 000 dépensés


def test_la_marge_peut_etre_negative():
    _depense("300000", jour=date(2026, 9, 5))

    assert services.indicateurs(*SEPT)["marge_nette"] == Decimal("-300000")


def test_un_utilisateur_de_role_rh_ne_saisit_rien():
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=UserFactory(role=Role.RH))
