"""Écrans de la saisie manuelle d'opérations diverses (Phase 4) et des exercices comptables
(Phase 5)."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounting import services
from apps.accounting.models import (
    Compte,
    EcritureComptable,
    Journal,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)

from .factories import CompteFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _brouillon(**kwargs):
    return services.creer_ecriture_manuelle(
        UserFactory(role=Role.FINANCES), date_ecriture=date(2026, 9, 5), libelle="Test OD", **kwargs
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_liste_est_accessible_aux_roles_de_consultation(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 403


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_seuls_les_roles_de_saisie_creent_une_ecriture(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecriture_manuelle_nouvelle")).status_code == 403


def test_creer_une_ecriture_manuelle_via_l_ecran(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:ecriture_manuelle_nouvelle"),
        {"date_ecriture": "2026-09-05", "libelle": "Régularisation caisse"},
    )

    ecriture = EcritureComptable.objects.get()
    assert reponse.status_code == 302
    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.libelle == "Régularisation caisse"


def test_ajouter_puis_supprimer_une_ligne_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()

    client.post(
        reverse("accounting:ligne_ajouter", args=[ecriture.pk]),
        {"compte": charge.numero, "sens": SensEcriture.DEBIT, "montant": "5000", "libelle": ""},
    )
    assert ecriture.lignes.count() == 1
    ligne = ecriture.lignes.first()

    reponse = client.post(reverse("accounting:ligne_supprimer", args=[ecriture.pk, ligne.pk]))

    assert reponse.status_code == 302
    assert ecriture.lignes.count() == 0


def test_la_fiche_propose_la_validation_a_la_direction_une_fois_equilibree(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) in page

    _connecte(client, Role.FINANCES)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) not in page


def test_valider_via_l_ecran_est_reserve_a_la_direction(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.FINANCES)
    assert client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk])).status_code == 403

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]))
    assert reponse.status_code == 302
    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE


def test_abandonner_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    ecriture = _brouillon()

    reponse = client.post(reverse("accounting:ecriture_manuelle_abandonner", args=[ecriture.pk]))

    assert reponse.status_code == 302
    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()


# --- exercices comptables (Phase 5) ---


def test_la_liste_des_exercices_est_accessible_en_consultation(client):
    services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:exercices"))

    assert reponse.status_code == 200
    assert "2026" in reponse.content.decode()


def test_seule_la_direction_voit_le_bouton_cloturer(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    url_cloturer = reverse("accounting:exercice_cloturer", args=[exercice.pk])

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("accounting:exercices")).content.decode()
    assert url_cloturer in page

    _connecte(client, Role.FINANCES)
    page = client.get(reverse("accounting:exercices")).content.decode()
    assert url_cloturer not in page


def test_cloturer_via_l_ecran_est_reserve_a_la_direction(client):
    exercice = services.exercice_pour(date(2024, 6, 5))

    _connecte(client, Role.FINANCES)
    assert client.post(reverse("accounting:exercice_cloturer", args=[exercice.pk])).status_code == 403

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("accounting:exercice_cloturer", args=[exercice.pk]))
    assert reponse.status_code == 302
    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE


# --- plan comptable (Lot F, autonomie comptable) ---


def test_le_plan_comptable_est_accessible_en_consultation(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:plan_comptable"))

    assert reponse.status_code == 200
    assert reponse.context["peut_gerer"] is True


def test_le_bouton_nouveau_compte_apparait_pour_un_role_autorise(client):
    _connecte(client, Role.RH)  # RH a la même largeur que Finances (CONSULTATION et GESTION)
    page = client.get(reverse("accounting:plan_comptable")).content.decode()
    assert reverse("accounting:compte_nouveau") in page


def test_creer_un_compte_via_l_ecran(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_nouveau"),
        {"numero": "999999", "libelle": "Compte de test", "nature": "CHARGE"},
    )

    assert reponse.status_code == 302
    assert Compte.objects.filter(numero="999999", libelle="Compte de test").exists()


def test_creer_un_compte_avec_un_numero_deja_pris_affiche_une_erreur(client):
    CompteFactory(numero="999999")
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_nouveau"),
        {"numero": "999999", "libelle": "Doublon", "nature": "CHARGE"},
    )

    assert reponse.status_code == 200
    assert "existe déjà" in reponse.content.decode()


def test_modifier_un_compte_via_l_ecran(client):
    compte = CompteFactory(libelle="Ancien", actif=True)
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_modifier", args=[compte.pk]), {"libelle": "Nouveau"}
    )

    assert reponse.status_code == 302
    compte.refresh_from_db()
    assert compte.libelle == "Nouveau"
    assert compte.actif is False  # case à cocher absente du POST = décochée


def test_gestion_du_plan_comptable_est_interdite_aux_autres_roles(client):
    compte = CompteFactory()
    _connecte(client, Role.CHAUFFEUR)

    assert client.get(reverse("accounting:plan_comptable")).status_code == 403
    assert client.get(reverse("accounting:compte_nouveau")).status_code == 403
    assert client.get(reverse("accounting:compte_modifier", args=[compte.pk])).status_code == 403


# --- rapports comptables (Phase 6) ---


def _passer_ecriture_od(charge, tresorerie, *, date_ecriture, montant="5000"):
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date_ecriture, libelle="Test",
        lignes=[
            services.LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            services.LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


@pytest.mark.parametrize(
    "nom_url",
    ["accounting:grand_livre", "accounting:balance", "accounting:bilan", "accounting:compte_resultat"],
)
@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_les_rapports_sont_accessibles_aux_roles_de_consultation(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.parametrize(
    "nom_url",
    ["accounting:grand_livre", "accounting:balance", "accounting:bilan", "accounting:compte_resultat"],
)
@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_les_rapports_sont_interdits_aux_autres_roles(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 403


def test_grand_livre_sans_compte_selectionne_n_affiche_aucune_ligne(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre"))

    assert reponse.context["lignes"] is None


def test_grand_livre_avec_compte_selectionne_affiche_les_lignes(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre"), {"compte": charge.numero})

    lignes = reponse.context["lignes"]
    assert len(lignes) == 1
    assert lignes[0]["solde_cumule"] == Decimal("5000")


def test_balance_totalise_debit_et_credit(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5), montant="7000")
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:balance"))

    assert reponse.context["totaux"] == {"debit": Decimal("7000"), "credit": Decimal("7000")}


def test_bilan_sans_aucun_exercice_n_affiche_pas_de_rapport(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"))

    assert reponse.context["exercice"] is None
    assert reponse.context["rapport"] is None


def test_bilan_choisit_l_exercice_le_plus_recent_par_defaut(client):
    services.exercice_pour(date(2025, 6, 1))
    exercice_2026 = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"))

    assert reponse.context["exercice"] == exercice_2026
    assert reponse.context["rapport"] is not None


def test_bilan_change_d_exercice_via_le_parametre(client):
    exercice_2025 = services.exercice_pour(date(2025, 6, 1))
    services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"), {"exercice": 2025})

    assert reponse.context["exercice"] == exercice_2025


def test_compte_de_resultat_choisit_l_exercice_le_plus_recent_par_defaut(client):
    services.exercice_pour(date(2025, 6, 1))
    exercice_2026 = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat"))

    assert reponse.context["exercice"] == exercice_2026
    assert reponse.context["rapport"] is not None


def test_compte_de_resultat_sans_aucun_exercice_n_affiche_pas_de_rapport(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat"))

    assert reponse.context["exercice"] is None
    assert reponse.context["rapport"] is None


# --- versions imprimables des rapports (Phase 6 bis) ---


@pytest.mark.parametrize(
    "nom_url",
    [
        "accounting:grand_livre_imprimer",
        "accounting:balance_imprimer",
        "accounting:bilan_imprimer",
        "accounting:compte_resultat_imprimer",
        "accounting:declaration_tva_imprimer",
    ],
)
@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_les_versions_imprimables_sont_accessibles_aux_roles_de_consultation(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.parametrize(
    "nom_url",
    [
        "accounting:grand_livre_imprimer",
        "accounting:balance_imprimer",
        "accounting:bilan_imprimer",
        "accounting:compte_resultat_imprimer",
        "accounting:declaration_tva_imprimer",
    ],
)
def test_les_versions_imprimables_sont_interdites_aux_autres_roles(client, nom_url):
    _connecte(client, Role.CHAUFFEUR)

    assert client.get(reverse(nom_url)).status_code == 403


def test_grand_livre_imprimer_affiche_les_lignes_du_compte(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre_imprimer"), {"compte": charge.numero})

    assert reponse.status_code == 200
    assert reponse.context["lignes"] is not None
    assert len(reponse.context["lignes"]) == 1
    contenu = reponse.content.decode()
    assert "Généré le" in contenu  # pied de rapport commun (apps/core/rapports.py)


def test_balance_imprimer_affiche_les_totaux(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5), montant="7000")
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:balance_imprimer"))

    assert reponse.context["totaux"] == {"debit": Decimal("7000"), "credit": Decimal("7000")}


def test_bilan_imprimer_reprend_l_exercice_le_plus_recent(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan_imprimer"))

    assert reponse.context["exercice"] == exercice
    assert reponse.context["rapport_bilan"] is not None


def test_compte_resultat_imprimer_reprend_l_exercice_le_plus_recent(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat_imprimer"))

    assert reponse.context["exercice"] == exercice
    assert reponse.context["rapport_resultat"] is not None


# --- déclaration TVA (Phase 6 ter) ---


def test_declaration_tva_par_defaut_porte_sur_le_mois_en_cours(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:declaration_tva"))

    assert reponse.status_code == 200
    rapport = reponse.context["rapport"]
    assert rapport["debut"].day == 1
    assert rapport["fin"].month == rapport["debut"].month


def test_declaration_tva_accepte_une_periode_choisie(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(
        reverse("accounting:declaration_tva"), {"debut": "2026-01-01", "fin": "2026-03-31"}
    )

    rapport = reponse.context["rapport"]
    assert (rapport["debut"], rapport["fin"]) == (date(2026, 1, 1), date(2026, 3, 31))


def test_declaration_tva_imprimer_affiche_les_totaux(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(
        reverse("accounting:declaration_tva_imprimer"), {"debut": "2026-01-01", "fin": "2026-03-31"}
    )

    assert reponse.status_code == 200
    rapport = reponse.context["rapport_tva"]
    assert (rapport["debut"], rapport["fin"]) == (date(2026, 1, 1), date(2026, 3, 31))
    contenu = reponse.content.decode()
    assert "Généré le" in contenu
