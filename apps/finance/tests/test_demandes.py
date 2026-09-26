"""Dépenses du parc auto pré-approuvées (R2) : enveloppes, demandes manuelles et dépassements,
ordres de décaissement et blocage à plus de 10 % de dépassement."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide, TransitionFactureInterdite
from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import demandes as services
from apps.finance.models import (
    DemandeDepense,
    OrdreDecaissement,
    OrigineDemande,
    StatutDemandeDepense,
    StatutOrdreDecaissement,
)
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.fuel.models import Plein

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 10)


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


def _direction():
    return UserFactory(role=Role.DIRECTION)


def _finances():
    return UserFactory(role=Role.FINANCES)


def _plein(*, camion=None, litres="100", prix="655", jour=JOUR, ticket="T-1"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour,
        station="Total", quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix),
        km_compteur=1000, numero_ticket=ticket,
    )


# --- enveloppes ---


def test_la_direction_definit_une_enveloppe():
    enveloppe = services.definir_enveloppe(
        _direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000")
    )

    assert enveloppe.montant_plafond == Decimal("300000")
    assert enveloppe.vehicule is None


def test_redefinir_la_meme_enveloppe_met_a_jour_le_plafond():
    direction = _direction()
    services.definir_enveloppe(direction, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000"))

    services.definir_enveloppe(direction, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("500000"))

    assert services.enveloppes_queryset().count() == 1
    assert services.enveloppes_queryset().first().montant_plafond == Decimal("500000")


def test_seule_la_direction_definit_une_enveloppe():
    for acteur in (_parcauto(), _finances(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.definir_enveloppe(acteur, categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("1"))


def test_enveloppe_refusee_hors_categorie_automatique():
    with pytest.raises(MontantInvalide):
        services.definir_enveloppe(_direction(), categorie=CategorieDepense.PEAGES, annee=2026, mois=9, montant_plafond=Decimal("1"))


# --- dépenses automatiques sans enveloppe : comportement inchangé ---


def test_sans_enveloppe_la_depense_automatique_reste_illimitee():
    plein = _plein(litres="500", prix="700")  # 350 000 FCFA, aucune enveloppe définie

    (depense,) = Depense.objects.filter(origine=OrigineDepense.PLEIN)
    assert depense.origine_id == plein.pk
    assert not DemandeDepense.objects.exists()


# --- dépassement d'enveloppe ---


def test_dans_l_enveloppe_aucune_demande_ne_s_ouvre():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("300000"))

    _plein(litres="100", prix="655", jour=JOUR)  # 65 500 FCFA, largement sous le plafond

    assert not DemandeDepense.objects.exists()


def test_le_depassement_ouvre_une_demande_mais_garde_la_depense():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))

    plein = _plein(litres="100", prix="655", jour=JOUR)  # 65 500 FCFA > 50 000

    assert Depense.objects.filter(origine_id=plein.pk).exists()  # l'argent est déjà sorti
    demande = DemandeDepense.objects.get()
    assert demande.origine == OrigineDemande.DEPASSEMENT_ENVELOPPE
    assert demande.statut == StatutDemandeDepense.SOUMISE
    assert demande.categorie == CategorieDepense.CARBURANT
    assert demande.montant_estime == Decimal("15500.00")


def test_une_demande_en_attente_bloque_le_plein_suivant():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")  # dépasse, ouvre une demande

    with pytest.raises(TransitionFactureInterdite, match="dépassée"):
        _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")

    # L'opération d'origine (le plein) est annulée avec la dépense refusée : rien n'est resté en base.
    assert not Plein.objects.filter(numero_ticket="T-2").exists()
    assert DemandeDepense.objects.count() == 1


def test_valider_la_demande_debloque_le_mecanisme():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")
    demande = DemandeDepense.objects.get()

    services.valider_demande(demande, _direction())
    _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")  # ne lève plus

    assert Depense.objects.filter(origine=OrigineDepense.PLEIN).count() == 2


def test_refuser_la_demande_debloque_aussi_le_mecanisme():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR, ticket="T-1")
    demande = DemandeDepense.objects.get()

    services.refuser_demande(demande, _direction(), motif="Consommation anormale à vérifier")
    _plein(litres="10", prix="655", jour=JOUR, ticket="T-2")

    assert Depense.objects.filter(origine=OrigineDepense.PLEIN).count() == 2


def test_une_demande_de_depassement_ne_genere_pas_d_ordre_de_decaissement():
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"))
    _plein(litres="100", prix="655", jour=JOUR)
    demande = DemandeDepense.objects.get()

    services.valider_demande(demande, _direction())

    assert not OrdreDecaissement.objects.exists()


def test_enveloppe_par_camion_prime_sur_l_enveloppe_globale():
    camion = VehiculeFactory()
    services.definir_enveloppe(_direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("1000000"))
    services.definir_enveloppe(
        _direction(), categorie=CategorieDepense.CARBURANT, annee=2026, mois=9, montant_plafond=Decimal("50000"), vehicule=camion
    )

    _plein(camion=camion, litres="100", prix="655", jour=JOUR)  # 65 500 > 50 000 (enveloppe du camion)

    demande = DemandeDepense.objects.get()
    assert demande.vehicule == camion


# --- demande manuelle (Parc Auto) ---


def test_soumettre_une_demande_manuelle():
    demande = services.soumettre_demande(
        _parcauto(), categorie=CategorieDepense.MAINTENANCE, montant_estime=Decimal("200000"),
        motif="Réparation boîte de vitesses chez un prestataire externe", fournisseur="Garage Koffi",
    )

    assert demande.origine == OrigineDemande.MANUELLE
    assert demande.statut == StatutDemandeDepense.SOUMISE
    assert demande.numero.startswith("DEM-2026-")


def test_seul_le_parc_auto_soumet_une_demande():
    with pytest.raises(ActionFactureNonAutorisee):
        services.soumettre_demande(_direction(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1"), motif="x")


@pytest.mark.parametrize("montant", [Decimal("0"), Decimal("-1")])
def test_montant_estime_invalide(montant):
    with pytest.raises(MontantInvalide):
        services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=montant, motif="x")


def test_motif_obligatoire():
    with pytest.raises(MontantInvalide, match="motif"):
        services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="   ")


def test_valider_une_demande_manuelle_genere_un_ordre():
    demande = services.soumettre_demande(
        _parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="Pièce rare"
    )

    services.valider_demande(demande, _direction())

    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.VALIDEE
    ordre = OrdreDecaissement.objects.get(demande=demande)
    assert ordre.montant_valide == Decimal("200000")
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER
    assert ordre.numero.startswith("ODC-2026-")


def test_valider_peut_ajuster_le_montant():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="x")

    services.valider_demande(demande, _direction(), montant_valide=Decimal("150000"))

    assert OrdreDecaissement.objects.get(demande=demande).montant_valide == Decimal("150000")


def test_seule_la_direction_valide_ou_refuse():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")
    for acteur in (_parcauto(), _finances(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.valider_demande(demande, acteur)
        with pytest.raises(ActionFactureNonAutorisee):
            services.refuser_demande(demande, acteur, motif="x")


def test_refuser_exige_un_motif():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")

    with pytest.raises(MontantInvalide, match="motif"):
        services.refuser_demande(demande, _direction(), motif="  ")


def test_une_demande_deja_traitee_ne_se_redecide_pas():
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal("1000"), motif="x")
    services.valider_demande(demande, _direction())

    with pytest.raises(TransitionFactureInterdite):
        services.valider_demande(demande, _direction())


# --- exécution et dépassement de 10 % ---


def _ordre_valide(montant_estime="200000", montant_valide=None):
    demande = services.soumettre_demande(_parcauto(), categorie=CategorieDepense.PIECES, montant_estime=Decimal(montant_estime), motif="x")
    services.valider_demande(demande, _direction(), montant_valide=montant_valide)
    return OrdreDecaissement.objects.get(demande=demande)


def test_executer_un_ordre_dans_la_tolerance_comptabilise_la_depense():
    ordre = _ordre_valide("200000")

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.VIREMENT, montant_reel=Decimal("205000"), reference="FAC-1")

    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE
    depense = Depense.objects.get(origine=OrigineDepense.ORDRE_DECAISSEMENT, origine_id=ordre.pk)
    assert depense.montant == Decimal("205000.00") and depense.mode == ModePaiement.VIREMENT
    assert ordre.depense_id == depense.pk


def test_seule_la_finance_execute():
    ordre = _ordre_valide()
    for acteur in (_parcauto(), _direction(), UserFactory(role=Role.ADMIN)):
        with pytest.raises(ActionFactureNonAutorisee):
            services.executer_ordre(ordre, acteur, mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("1000"))


def test_un_depassement_de_plus_de_10_pourcent_bloque_l_execution():
    ordre = _ordre_valide("200000")

    with pytest.raises(MontantInvalide, match="dépasse"):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))

    ordre.refresh_from_db()
    # L'état bloqué est bien enregistré (pas annulé avec l'erreur) : la finance ne peut plus rejouer.
    assert ordre.statut == StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION
    assert ordre.montant_reel == Decimal("230000")
    assert not Depense.objects.filter(origine=OrigineDepense.ORDRE_DECAISSEMENT).exists()


def test_exactement_10_pourcent_de_plus_passe():
    ordre = _ordre_valide("200000")

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("220000"))

    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_revalider_permet_de_reexecuter():
    ordre = _ordre_valide("200000")
    with pytest.raises(MontantInvalide):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()

    services.revalider_ordre(ordre, _direction(), montant_valide=Decimal("230000"))
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER

    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_seule_la_direction_revalide():
    ordre = _ordre_valide("200000")
    with pytest.raises(MontantInvalide):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("230000"))
    ordre.refresh_from_db()

    with pytest.raises(ActionFactureNonAutorisee):
        services.revalider_ordre(ordre, _finances(), montant_valide=Decimal("230000"))


def test_un_ordre_deja_execute_ne_se_reexecute_pas():
    ordre = _ordre_valide("200000")
    services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("200000"))
    ordre.refresh_from_db()

    with pytest.raises(TransitionFactureInterdite):
        services.executer_ordre(ordre, _finances(), mode_paiement=ModePaiement.ESPECES, montant_reel=Decimal("200000"))
