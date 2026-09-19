"""Carburant — cahier-des-charges.md:147-157."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.exceptions import (
    HorsChronologie,
    KilometrageInvalide,
    SaisieInvalide,
    SaisieSuspecte,
    TicketDejaEnregistre,
)
from apps.fuel.models import NiveauAlerte, Plein

pytestmark = pytest.mark.django_db

_tickets = itertools.count(1)
KM_INITIAL = 1000
DISTANCE = 400  # chaque plein de la série couvre 400 km : litres = conso x 4


def _plein(vehicule, chauffeur, *, km, litres, jour, confirmer=True, **surcharges):
    donnees = dict(
        vehicule=vehicule,
        chauffeur=chauffeur,
        date_plein=date(2026, 9, 1) + timedelta(days=jour),
        station="Total",
        quantite_litres=Decimal(str(litres)),
        prix_unitaire=Decimal("655"),
        km_compteur=km,
        numero_ticket=f"T-{next(_tickets)}",
        confirmer_alerte_saisie=confirmer,
    )
    donnees.update(surcharges)
    return services.enregistrer_plein(**donnees)


def _serie(vehicule, chauffeur, consommations):
    """Premier plein (sans conso) puis un plein par valeur de ``consommations``."""
    _plein(vehicule, chauffeur, km=KM_INITIAL, litres=100, jour=0)
    for rang, conso in enumerate(consommations, start=1):
        _plein(
            vehicule,
            chauffeur,
            km=KM_INITIAL + rang * DISTANCE,
            litres=Decimal(str(conso)) * 4,
            jour=rang,
        )
    return KM_INITIAL + len(consommations) * DISTANCE


def _suivant(vehicule, chauffeur, consommations, conso, confirmer=True):
    """Ajoute un plein de consommation ``conso`` après la série."""
    dernier_km = _serie(vehicule, chauffeur, consommations)
    return _plein(
        vehicule,
        chauffeur,
        km=dernier_km + DISTANCE,
        litres=Decimal(str(conso)) * 4,
        jour=len(consommations) + 1,
        confirmer=confirmer,
    )


@pytest.fixture
def camion():
    return VehiculeFactory()


@pytest.fixture
def chauffeur():
    return ChauffeurFactory()


# --- formule ---


def test_formule_litres_sur_distance_fois_100():
    assert services.calculer_consommation(Decimal("120"), 400) == Decimal("30.00")


def test_la_consommation_est_arrondie_au_centieme():
    assert services.calculer_consommation(Decimal("100"), 300) == Decimal("33.33")


def test_premier_plein_sans_consommation_ni_alerte(camion, chauffeur):
    plein = _plein(camion, chauffeur, km=KM_INITIAL, litres=100, jour=0)

    assert plein.consommation is None
    assert plein.km_precedent is None and plein.distance_km is None
    assert plein.niveau_alerte == NiveauAlerte.AUCUNE
    assert not plein.anomalie and not plein.alerte_saisie


def test_deuxieme_plein_calcule_la_consommation_sans_comparaison(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)

    plein = _plein(camion, chauffeur, km=1400, litres=120, jour=1)

    assert plein.km_precedent == 1000
    assert plein.distance_km == 400
    assert plein.consommation == Decimal("30.00")
    assert plein.moyenne_reference is None and plein.ecart_pct is None
    assert plein.niveau_alerte == NiveauAlerte.AUCUNE


# --- alertes : seuils stricts, moyenne de référence 30 L/100 km ---


@pytest.mark.parametrize(
    ("conso", "niveau", "saisie", "anomalie"),
    [
        ("30", NiveauAlerte.AUCUNE, False, False),  # écart 0 %
        ("24", NiveauAlerte.AUCUNE, False, False),  # -20 %
        ("36", NiveauAlerte.AUCUNE, False, False),  # +20 % exactement : pas > 20
        ("36.04", NiveauAlerte.JAUNE, False, False),  # juste au-dessus
        ("37", NiveauAlerte.JAUNE, False, False),  # +23,33 %
        ("42", NiveauAlerte.JAUNE, False, False),  # +40 % exactement : pas > 40
        ("42.04", NiveauAlerte.ROUGE, False, False),
        ("44", NiveauAlerte.ROUGE, False, False),  # +46,67 %
        ("45", NiveauAlerte.ROUGE, False, False),  # 45 exactement : pas > 45
        ("45.01", NiveauAlerte.ROUGE, False, True),  # anomalie haute
        ("48", NiveauAlerte.ROUGE, False, True),  # +60 % exactement : pas > 60
        ("48.04", NiveauAlerte.ROUGE, True, True),  # +60,13 %
        ("50", NiveauAlerte.ROUGE, True, True),  # +66,67 %
        ("20", NiveauAlerte.AUCUNE, False, False),  # 20 exactement : pas < 20
        ("19.99", NiveauAlerte.AUCUNE, False, True),  # anomalie basse
        ("12", NiveauAlerte.AUCUNE, False, True),  # -60 % exactement : pas > 60
        ("11.96", NiveauAlerte.AUCUNE, True, True),  # -60,13 %
    ],
)
def test_alertes_selon_l_ecart_a_la_moyenne(camion, chauffeur, conso, niveau, saisie, anomalie):
    plein = _suivant(camion, chauffeur, ["30"], conso)

    assert plein.moyenne_reference == Decimal("30.00")
    assert plein.niveau_alerte == niveau
    assert plein.alerte_saisie is saisie
    assert plein.anomalie is anomalie


def test_l_ecart_est_enregistre_en_pourcentage(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "37")

    assert plein.ecart_pct == Decimal("23.33")


def test_une_consommation_inferieure_a_la_moyenne_ne_declenche_pas_de_surconsommation(
    camion, chauffeur
):
    plein = _suivant(camion, chauffeur, ["30"], "22")  # -26,67 %

    assert plein.niveau_alerte == NiveauAlerte.AUCUNE
    assert plein.ecart_pct == Decimal("-26.67")


# --- moyenne de référence ---


def test_la_reference_est_la_moyenne_des_3_derniers_pleins_seulement(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["20", "30", "40", "30"], "30")

    # 3 derniers avant celui-ci : 30, 40, 30 ; le plein à 20 est exclu.
    assert plein.moyenne_reference == Decimal("33.33")


def test_la_reference_utilise_les_pleins_disponibles_s_il_y_en_a_moins_de_3(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["20", "30"], "40")

    assert plein.moyenne_reference == Decimal("25.00")
    assert plein.ecart_pct == Decimal("60.00")
    assert plein.niveau_alerte == NiveauAlerte.ROUGE
    assert plein.alerte_saisie is False  # 60 % exactement


def test_la_reference_ignore_les_pleins_des_autres_camions(camion, chauffeur):
    _serie(VehiculeFactory(), chauffeur, ["50", "50"])

    plein = _suivant(camion, chauffeur, ["30"], "30")

    assert plein.moyenne_reference == Decimal("30.00")


# --- saisie suspecte (alerte de saisie, cahier-des-charges.md:155) ---


def test_saisie_suspecte_est_refusee_tant_qu_elle_n_est_pas_confirmee(camion, chauffeur):
    with pytest.raises(SaisieSuspecte) as erreur:
        _suivant(camion, chauffeur, ["30"], "50", confirmer=False)

    assert erreur.value.ecart_pct == Decimal("66.67")
    assert erreur.value.consommation == Decimal("50.00")
    assert erreur.value.moyenne == Decimal("30.00")
    assert Plein.objects.count() == 2  # premier plein + plein de la série


def test_saisie_suspecte_confirmee_est_enregistree_avec_son_alerte(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "50", confirmer=True)

    assert plein.alerte_saisie is True
    assert Plein.objects.count() == 3


def test_une_sous_consommation_suspecte_demande_aussi_confirmation(camion, chauffeur):
    with pytest.raises(SaisieSuspecte):
        _suivant(camion, chauffeur, ["30"], "10", confirmer=False)


def test_un_ecart_de_60_pourcent_pile_ne_demande_pas_confirmation(camion, chauffeur):
    plein = _suivant(camion, chauffeur, ["30"], "48", confirmer=False)

    assert plein.alerte_saisie is False


# --- contrôles de saisie ---


def test_km_inferieur_ou_egal_au_plein_precedent_refuse(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=0)

    for km in (2000, 1999):
        with pytest.raises(KilometrageInvalide):
            _plein(camion, chauffeur, km=km, litres=100, jour=1)

    assert Plein.objects.count() == 1


def test_date_anterieure_au_dernier_plein_refusee(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=5)

    with pytest.raises(HorsChronologie):
        _plein(camion, chauffeur, km=2500, litres=100, jour=4)


def test_deux_pleins_le_meme_jour_sont_acceptes_dans_l_ordre_des_km(camion, chauffeur):
    _plein(camion, chauffeur, km=2000, litres=100, jour=1)

    plein = _plein(camion, chauffeur, km=2300, litres=90, jour=1)

    assert plein.distance_km == 300


def test_le_chronometrage_est_propre_a_chaque_camion(camion, chauffeur):
    _plein(camion, chauffeur, km=5000, litres=100, jour=5)

    _plein(VehiculeFactory(), chauffeur, km=100, litres=100, jour=1)


@pytest.mark.parametrize("litres", ["0", "-10"])
def test_quantite_nulle_ou_negative_refusee(camion, chauffeur, litres):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=litres, jour=0)


def test_prix_nul_refuse(camion, chauffeur):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=100, jour=0, prix_unitaire=Decimal("0"))


@pytest.mark.parametrize("ticket", ["", "   "])
def test_numero_de_ticket_obligatoire(camion, chauffeur, ticket):
    with pytest.raises(SaisieInvalide):
        _plein(camion, chauffeur, km=1000, litres=100, jour=0, numero_ticket=ticket)


def test_ticket_deja_enregistre_refuse_comme_double_saisie(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0, numero_ticket="TKT-9")

    with pytest.raises(TicketDejaEnregistre):
        _plein(camion, chauffeur, km=1400, litres=100, jour=1, numero_ticket=" TKT-9 ")


# --- compteur du camion ---


def test_le_plein_releve_le_compteur_du_camion_s_il_est_superieur(chauffeur):
    camion = VehiculeFactory(kilometrage=120000)

    _plein(camion, chauffeur, km=120500, litres=100, jour=0)

    camion.refresh_from_db()
    assert camion.kilometrage == 120500


def test_le_plein_ne_fait_jamais_reculer_le_compteur(chauffeur):
    camion = VehiculeFactory(kilometrage=130000)

    _plein(camion, chauffeur, km=125000, litres=100, jour=0)

    camion.refresh_from_db()
    assert camion.kilometrage == 130000


# --- analyse par camion, par chauffeur, globale (cahier-des-charges.md:156) ---


def test_consommation_moyenne_ponderee_par_la_distance(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=100, jour=0)
    _plein(camion, chauffeur, km=1400, litres=120, jour=1)  # 400 km, 30 L/100
    _plein(camion, chauffeur, km=1500, litres=45, jour=2)  # 100 km, 45 L/100

    # (120 + 45) / (400 + 100) x 100 = 33,00 ; la moyenne simple donnerait 37,5.
    assert services.consommation_moyenne(vehicule=camion) == Decimal("33.00")


def test_consommation_moyenne_par_chauffeur(camion):
    econome, gourmand = ChauffeurFactory(), ChauffeurFactory()
    _plein(camion, econome, km=1000, litres=100, jour=0)
    _plein(camion, econome, km=1400, litres=100, jour=1)  # 25 L/100
    _plein(camion, gourmand, km=1800, litres=160, jour=2)  # 40 L/100

    assert services.consommation_moyenne(chauffeur=econome) == Decimal("25.00")
    assert services.consommation_moyenne(chauffeur=gourmand) == Decimal("40.00")


def test_consommation_moyenne_globale_de_la_flotte(chauffeur):
    premier, second = VehiculeFactory(), VehiculeFactory()
    _plein(premier, chauffeur, km=1000, litres=100, jour=0)
    _plein(premier, chauffeur, km=1400, litres=100, jour=1)  # 400 km, 100 L
    _plein(second, chauffeur, km=1000, litres=100, jour=0)
    _plein(second, chauffeur, km=1200, litres=100, jour=1)  # 200 km, 100 L

    assert services.consommation_moyenne() == Decimal("33.33")  # 200 L / 600 km


def test_consommation_moyenne_ignore_le_premier_plein_sans_distance(camion, chauffeur):
    _plein(camion, chauffeur, km=1000, litres=500, jour=0)  # sans conso : exclu
    _plein(camion, chauffeur, km=1400, litres=120, jour=1)

    assert services.consommation_moyenne(vehicule=camion) == Decimal("30.00")


def test_consommation_moyenne_est_none_sans_donnees(camion):
    assert services.consommation_moyenne(vehicule=camion) is None
    assert services.consommation_moyenne() is None


# --- pleins à surveiller ---


def test_pleins_a_surveiller_liste_alertes_anomalies_et_saisies_suspectes(camion, chauffeur):
    _serie(camion, chauffeur, ["30", "30"])
    normal = Plein.objects.get(km_compteur=KM_INITIAL + 2 * DISTANCE)
    jaune = _plein(camion, chauffeur, km=2200, litres=148, jour=9)  # 37 L/100
    anomalie = _plein(camion, chauffeur, km=2600, litres=72, jour=10)  # 18 L/100

    surveilles = list(services.pleins_a_surveiller())

    assert jaune in surveilles and anomalie in surveilles
    assert normal not in surveilles
