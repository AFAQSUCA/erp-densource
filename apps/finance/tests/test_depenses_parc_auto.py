"""Les dépenses du parc auto (plein, achat de pièces, main-d'œuvre d'OR) sont comptabilisées toutes seules :
page Dépenses, trésorerie et charges donnent le même total."""

import importlib
from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps as registre
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.forms import DepenseForm
from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.fuel.models import Plein
from apps.fuel.tests.factories import PleinFactory
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = timezone.localdate()


def _plein(litres="100", prix="655", jour=None, ticket="T-1", camion=None, km=1000):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour or AUJOURD_HUI,
        station="Total", quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km,
        numero_ticket=ticket,
    )


def _auto(origine):
    return Depense.objects.filter(origine=origine)


# --- plein ---


def test_un_plein_devient_une_depense_carburant_en_especes():
    plein = _plein("110", "655", jour=date(2026, 9, 3), ticket="TK-9")

    (depense,) = _auto(OrigineDepense.PLEIN)

    assert depense.origine_id == plein.pk
    assert depense.categorie == CategorieDepense.CARBURANT
    assert depense.montant == Decimal("72050.00")
    assert depense.date_depense == date(2026, 9, 3)
    assert depense.mode == ModePaiement.ESPECES and depense.reference == "TK-9"
    assert plein.vehicule.immatriculation in depense.libelle and "110 L" in depense.libelle
    assert depense.est_automatique and depense.saisi_par is None


def test_le_plein_sort_de_la_caisse_dans_la_tresorerie():
    avant = services.soldes_par_compte()

    _plein("100", "600")

    apres = services.soldes_par_compte()
    assert apres["CAISSE"] - avant["CAISSE"] == Decimal("-60000")
    assert apres["total"] - avant["total"] == Decimal("-60000")
    ligne = next(m for m in services.mouvements() if m["origine"] == "DEPENSE")
    assert (ligne["sens"], ligne["montant"], ligne["compte"]) == ("SORTIE", Decimal("60000.00"), "CAISSE")


def test_rejouer_la_meme_source_ne_cree_pas_de_doublon():
    plein = _plein()
    kwargs = dict(
        origine=OrigineDepense.PLEIN, origine_id=plein.pk, categorie=CategorieDepense.CARBURANT,
        date_depense=AUJOURD_HUI, libelle="x", montant=Decimal("1"),
    )

    premiere = billing.comptabiliser_depense_automatique(**kwargs)
    seconde = billing.comptabiliser_depense_automatique(**kwargs)

    assert premiere.pk == seconde.pk and _auto(OrigineDepense.PLEIN).count() == 1


def test_un_plein_refuse_ne_laisse_aucune_depense():
    _plein(ticket="DOUBLON")

    with pytest.raises(Exception):
        _plein(ticket="DOUBLON")

    assert Depense.objects.count() == 1


def test_une_depense_qui_ne_peut_pas_etre_ecrite_annule_le_plein(monkeypatch):
    def echec(**kwargs):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(billing, "comptabiliser_depense_automatique", echec)

    with pytest.raises(RuntimeError):
        _plein()

    assert Plein.objects.count() == 0  # pas de sortie d'argent non comptée


# --- pièces et main-d'œuvre ---


def test_un_achat_de_pieces_devient_une_depense_pieces():
    article = ArticleFactory(reference="PN-1", designation="Pneu", quantite=0)

    mouvement = stock.enregistrer_entree(article, quantite=4, prix_unitaire=Decimal("125000"))

    (depense,) = _auto(OrigineDepense.ACHAT_STOCK)
    assert depense.origine_id == mouvement.pk and depense.categorie == CategorieDepense.PIECES
    assert depense.montant == Decimal("500000.00") and depense.date_depense == AUJOURD_HUI
    assert "Pneu" in depense.libelle and "PN-1" in depense.libelle and "× 4" in depense.libelle


def test_sortir_des_pieces_pour_un_or_ne_recompte_pas_la_piece():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins")
    article = ArticleFactory(reference="P-2", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))

    stock.sortir_pour_or(article, quantite=3, ordre=ordre)
    stock.ajuster_stock(article, variation=-1, motif="Casse")

    assert Depense.objects.count() == 1  # l'achat seul
    assert services.charges(AUJOURD_HUI, AUJOURD_HUI)["pieces"] == Decimal("50000")


def test_la_main_d_oeuvre_d_un_or_cloture_devient_une_depense_maintenance():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.EXTERNE, motif="Boîte")

    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    (depense,) = _auto(OrigineDepense.MAIN_OEUVRE_OR)
    assert depense.origine_id == ordre.pk and depense.categorie == CategorieDepense.MAINTENANCE
    assert depense.montant == Decimal("45000.00") and depense.reference == ordre.numero
    assert ordre.numero in depense.libelle


def test_un_or_sans_main_d_oeuvre_ne_cree_pas_de_depense():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.PREVENTIF, lieu=LieuReparation.INTERNE, motif="Vidange")

    garage.cloturer_or(ordre)

    assert Depense.objects.count() == 0


# --- cohérence page Dépenses / trésorerie / charges ---


def test_depenses_tresorerie_et_charges_donnent_le_meme_total():
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=AUJOURD_HUI, libelle="Péage", montant=Decimal("10000"),
        mode=ModePaiement.WAVE,
    )
    _plein("100", "600")
    stock.enregistrer_entree(ArticleFactory(quantite=0), quantite=2, prix_unitaire=Decimal("7000"))
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="x")
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("20000"))

    charges = services.charges(AUJOURD_HUI, AUJOURD_HUI)
    sorties = services.synthese_periode(AUJOURD_HUI, AUJOURD_HUI)["sorties"]

    assert charges["total"] == sorties == billing.total_depenses(AUJOURD_HUI, AUJOURD_HUI) == Decimal("104000")
    assert (charges["carburant"], charges["pieces"], charges["main_oeuvre"], charges["depenses"]) == (
        Decimal("60000"), Decimal("14000"), Decimal("20000"), Decimal("10000"),
    )


# --- saisie manuelle et correction du mode ---


@pytest.mark.parametrize("categorie", [CategorieDepense.CARBURANT, CategorieDepense.PIECES, CategorieDepense.MAINTENANCE])
def test_on_ne_saisit_pas_a_la_main_ce_qui_se_comptabilise_tout_seul(categorie):
    with pytest.raises(MontantInvalide, match="tout seuls"):
        billing.enregistrer_depense(
            finances(), categorie=categorie, date_depense=AUJOURD_HUI, libelle="x", montant=Decimal("1"),
            mode=ModePaiement.ESPECES,
        )


def test_le_formulaire_de_saisie_ne_propose_pas_les_categories_automatiques():
    codes = [code for code, _ in DepenseForm().fields["categorie"].choices]

    assert "PEAGES" in codes and "CARBURANT" not in codes and "PIECES" not in codes and "MAINTENANCE" not in codes


def test_la_finance_corrige_le_mode_et_le_compte_debite_change():
    _plein("100", "600")
    depense = _auto(OrigineDepense.PLEIN).get()

    billing.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    soldes = services.soldes_par_compte()
    assert soldes["BANQUE"] == Decimal("-60000") and soldes["CAISSE"] == Decimal("0")


def test_seule_la_finance_corrige_et_seulement_les_depenses_automatiques():
    _plein()
    automatique = _auto(OrigineDepense.PLEIN).get()
    manuelle = billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=AUJOURD_HUI, libelle="Péage", montant=Decimal("5000"),
        mode=ModePaiement.ESPECES,
    )

    with pytest.raises(ActionFactureNonAutorisee):
        billing.changer_mode_depense(automatique, UserFactory(role=Role.DIRECTION), mode=ModePaiement.WAVE)
    with pytest.raises(ActionFactureNonAutorisee):
        billing.changer_mode_depense(manuelle, finances(), mode=ModePaiement.WAVE)
    with pytest.raises(MontantInvalide):
        billing.changer_mode_depense(automatique, finances(), mode="BITCOIN")


def test_ecran_depenses_montre_les_lignes_automatiques_et_le_changement_de_mode(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    _plein("100", "600")
    depense = _auto(OrigineDepense.PLEIN).get()

    page = client.get(reverse("billing:depenses")).content.decode()
    assert "Automatique" in page and reverse("billing:depense_mode", args=[depense.pk]) in page

    reponse = client.post(reverse("billing:depense_mode", args=[depense.pk]), {"mode": "WAVE"}, follow=True)

    depense.refresh_from_db()
    assert depense.mode == ModePaiement.WAVE
    assert any("Wave" in str(m) for m in reponse.context["messages"])


def test_la_direction_voit_les_lignes_sans_pouvoir_changer_le_mode(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    _plein()
    depense = _auto(OrigineDepense.PLEIN).get()

    page = client.get(reverse("billing:depenses")).content.decode()

    assert "Automatique" in page and reverse("billing:depense_mode", args=[depense.pk]) not in page
    assert client.post(reverse("billing:depense_mode", args=[depense.pk]), {"mode": "WAVE"}).status_code == 403


# --- reprise de l'existant (migration billing.0003) ---


def test_la_reprise_de_l_existant_cree_les_depenses_manquantes_une_seule_fois():
    migration = importlib.import_module("apps.billing.migrations.0003_reprise_depenses_parc_auto")
    PleinFactory(date_plein=date(2026, 8, 3), quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"), numero_ticket="OLD-1")
    article = ArticleFactory(quantite=0)
    Depense.objects.all().delete()  # l'état d'avant : des pleins et des achats sans dépense
    stock.enregistrer_entree(article, quantite=3, prix_unitaire=Decimal("1000"))
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="x")
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("8000"))
    Depense.objects.all().delete()

    migration.reprendre(registre, None)
    migration.reprendre(registre, None)  # rejouable

    assert Depense.objects.count() == 3
    plein = _auto(OrigineDepense.PLEIN).get()
    assert plein.montant == Decimal("60000.00") and plein.date_depense == date(2026, 8, 3) and plein.reference == "OLD-1"
    assert _auto(OrigineDepense.ACHAT_STOCK).get().montant == Decimal("3000.00")
    assert _auto(OrigineDepense.MAIN_OEUVRE_OR).get().montant == Decimal("8000.00")
    assert set(Depense.objects.values_list("mode", flat=True)) == {ModePaiement.ESPECES}
