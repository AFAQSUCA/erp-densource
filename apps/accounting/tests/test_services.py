"""Moteur d'écritures : équilibre, idempotence, comptes inconnus/inactifs ; saisie manuelle
d'opérations diverses (Phase 4) ; exercice comptable et clôture (Phase 5) ; rapports (Phase 6)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import services
from apps.accounting.exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteDejaExistant,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from apps.accounting.models import (
    Compte,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

from .factories import CompteFactory

pytestmark = pytest.mark.django_db

JOUR = date(2026, 9, 1)


def _lignes_equilibrees(charge, tresorerie, montant="1000"):
    montant = Decimal(montant)
    return [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=montant),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=montant),
    ]


def test_passer_ecriture_equilibree_cree_lignes():
    charge, tresorerie = CompteFactory(), CompteFactory()

    ecriture = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=JOUR,
        libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ecriture.numero.startswith("OD-2026-")
    assert ecriture.lignes.count() == 2
    assert {l.compte_id for l in ecriture.lignes.all()} == {charge.pk, tresorerie.pk}


def test_passer_ecriture_desequilibree_leve_erreur_et_ne_cree_rien():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("900")),
    ]

    with pytest.raises(EcritureNonEquilibree, match="1000.*900|900.*1000"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )

    assert LigneEcriture.objects.count() == 0


def test_passer_ecriture_refuse_un_montant_negatif_ou_nul():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = [
        LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")),
        LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("0")),
    ]

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test", lignes=lignes
        )


def test_passer_ecriture_refuse_moins_de_deux_lignes():
    charge = CompteFactory()

    with pytest.raises(EcritureNonEquilibree):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000"))],
        )


def test_passer_ecriture_refuse_un_compte_inconnu():
    tresorerie = CompteFactory()

    with pytest.raises(CompteInconnu, match="999999"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=[
                LigneSaisie(compte="999999", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
                LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            ],
        )


def test_passer_ecriture_refuse_un_compte_inactif():
    charge, tresorerie = CompteFactory(actif=False), CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES,
            date_ecriture=JOUR,
            libelle="Test",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_passer_ecriture_idempotente_par_origine():
    charge, tresorerie = CompteFactory(), CompteFactory()
    lignes = _lignes_equilibrees(charge, tresorerie)

    premiere = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=lignes, origine="TEST", origine_id=42,
    )
    seconde = services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Autre libellé",
        lignes=lignes, origine="TEST", origine_id=42,
    )

    assert premiere.pk == seconde.pk
    assert LigneEcriture.objects.count() == 2  # pas de doublon


def test_grand_livre_filtre_par_compte_et_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes_annee = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 12, 31))
    lignes_premier_semestre = services.grand_livre(charge, debut=date(2026, 1, 1), fin=date(2026, 3, 31))

    assert lignes_annee.count() == 2
    assert lignes_premier_semestre.count() == 1


def test_grand_livre_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    assert services.grand_livre(charge).count() == 0


# --- plan comptable (Lot F, autonomie comptable) ---


def test_creer_un_compte():
    compte = services.creer_compte(
        finances(), numero="999999", libelle="Compte de test", nature="CHARGE"
    )

    assert (compte.numero, compte.libelle, compte.nature, compte.actif) == ("999999", "Compte de test", "CHARGE", True)


def test_creer_un_compte_refuse_un_numero_vide():
    with pytest.raises(CompteInconnu, match="numéro"):
        services.creer_compte(finances(), numero="  ", libelle="x", nature="CHARGE")


def test_creer_un_compte_refuse_une_nature_inconnue():
    with pytest.raises(CompteInconnu, match="Nature"):
        services.creer_compte(finances(), numero="999999", libelle="x", nature="INCONNUE")


def test_creer_un_compte_refuse_un_numero_deja_pris():
    services.creer_compte(finances(), numero="999999", libelle="Premier", nature="CHARGE")

    with pytest.raises(CompteDejaExistant):
        services.creer_compte(finances(), numero="999999", libelle="Second", nature="PRODUIT")


def test_creer_un_compte_refuse_un_libelle_vide():
    with pytest.raises(CompteInconnu, match="libellé"):
        services.creer_compte(finances(), numero="999999", libelle="  ", nature="CHARGE")


def test_creer_un_compte_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_compte(
            UserFactory(role=Role.CHAUFFEUR), numero="999999", libelle="x", nature="CHARGE"
        )


def test_modifier_un_compte_corrige_le_libelle_et_le_statut():
    compte = CompteFactory(libelle="Ancien libellé", actif=True)

    services.modifier_compte(compte, finances(), libelle="Nouveau libellé", actif=False)

    compte.refresh_from_db()
    assert (compte.libelle, compte.actif) == ("Nouveau libellé", False)


def test_modifier_un_compte_refuse_un_libelle_vide():
    compte = CompteFactory()

    with pytest.raises(CompteInconnu, match="libellé"):
        services.modifier_compte(compte, finances(), libelle=" ", actif=True)


def test_modifier_un_compte_refuse_un_role_non_autorise():
    compte = CompteFactory()

    with pytest.raises(ActionComptableNonAutorisee):
        services.modifier_compte(compte, UserFactory(role=Role.CHAUFFEUR), libelle="x", actif=True)


def test_un_compte_desactive_est_refuse_dans_une_nouvelle_ecriture():
    compte = CompteFactory()
    services.modifier_compte(compte, finances(), libelle=compte.libelle, actif=False)
    autre = CompteFactory()

    with pytest.raises(CompteInconnu):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
            lignes=_lignes_equilibrees(compte, autre),
        )


# --- saisie manuelle d'opérations diverses (Phase 4) ---


def test_creer_une_ecriture_manuelle_ouvre_un_brouillon_sans_numero():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.numero == ""
    assert ecriture.lignes.count() == 0


def test_creer_une_ecriture_manuelle_refuse_un_role_non_autorise():
    with pytest.raises(ActionComptableNonAutorisee):
        services.creer_ecriture_manuelle(
            UserFactory(role=Role.CHARGE_CLIENTELE), date_ecriture=JOUR, libelle="Test"
        )


def test_ajouter_puis_supprimer_une_ligne_sur_un_brouillon():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    assert ecriture.lignes.count() == 1

    services.supprimer_ligne_manuelle(ligne, finances())
    assert ecriture.lignes.count() == 0


def test_valider_une_ecriture_manuelle_equilibree_attribue_un_numero():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    validee = services.valider_ecriture_manuelle(ecriture, direction())

    assert validee.statut == StatutEcriture.VALIDEE
    assert validee.numero.startswith("OD-2026-")
    assert validee.valide_par is not None


def test_valider_une_ecriture_desequilibree_est_refuse():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    with pytest.raises(EcritureNonEquilibree):
        services.valider_ecriture_manuelle(ecriture, direction())

    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.BROUILLON


def test_seule_la_direction_valide_une_ecriture_manuelle_strict():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )

    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.valider_ecriture_manuelle(ecriture, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_une_fois_validee_on_ne_peut_plus_ajouter_ni_supprimer_de_ligne():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    ligne = services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1")
        )
    with pytest.raises(EcritureVerrouillee):
        services.supprimer_ligne_manuelle(ligne, finances())


def test_abandonner_un_brouillon():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    services.abandonner_ecriture_manuelle(ecriture, finances())

    from apps.accounting.models import EcritureComptable

    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()
    assert EcritureComptable.all_objects.get(pk=ecriture.pk).is_deleted


def test_on_ne_peut_pas_abandonner_une_ecriture_deja_validee():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    services.valider_ecriture_manuelle(ecriture, direction())

    with pytest.raises(EcritureVerrouillee):
        services.abandonner_ecriture_manuelle(ecriture, finances())


def test_creer_une_ecriture_manuelle_refuse_un_libelle_vide():
    with pytest.raises(EcritureNonEquilibree):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="   ")


def test_ajouter_une_ligne_refuse_un_montant_negatif_ou_nul():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")

    with pytest.raises(EcritureNonEquilibree):
        services.ajouter_ligne_manuelle(
            ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("0")
        )


def test_valider_une_ecriture_avec_deux_lignes_desequilibrees_est_refuse():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("4000")
    )

    with pytest.raises(EcritureNonEquilibree, match="5000.*4000|4000.*5000"):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- exercice comptable et clôture (Phase 5) ---


def test_exercice_pour_cree_l_exercice_de_l_annee_s_il_n_existe_pas():
    exercice = services.exercice_pour(date(2026, 3, 15))

    assert exercice.annee == 2026
    assert exercice.date_debut == date(2026, 1, 1)
    assert exercice.date_fin == date(2026, 12, 31)
    assert exercice.statut == StatutExercice.OUVERT


def test_exercice_pour_est_idempotent():
    premier = services.exercice_pour(date(2026, 3, 15))
    second = services.exercice_pour(date(2026, 11, 1))

    assert premier.pk == second.pk
    assert ExerciceComptable.objects.count() == 1


def test_passer_une_ecriture_cree_son_exercice_au_passage():
    charge, tresorerie = CompteFactory(), CompteFactory()

    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2027, 5, 1), libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    assert ExerciceComptable.objects.filter(annee=2027, statut=StatutExercice.OUVERT).exists()


def test_cloturer_un_exercice_verrouille_les_nouvelles_ecritures():
    charge, tresorerie = CompteFactory(), CompteFactory()
    exercice = services.exercice_pour(JOUR)

    services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE
    assert exercice.cloture_par is not None
    with pytest.raises(ExerciceCloture, match="2026"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Trop tard",
            lignes=_lignes_equilibrees(charge, tresorerie),
        )


def test_cloturer_est_reserve_a_la_direction_strict():
    exercice = services.exercice_pour(JOUR)

    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, finances())
    with pytest.raises(ActionComptableNonAutorisee):
        services.cloturer_exercice(exercice, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_cloturer_un_exercice_deja_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.cloturer_exercice(exercice, direction())


def test_cloturer_refuse_s_il_reste_des_brouillons_dans_la_periode():
    exercice = services.exercice_pour(JOUR)
    services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Encore en brouillon")

    with pytest.raises(ClotureImpossible, match="1"):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT


def test_creer_une_ecriture_manuelle_dans_un_exercice_cloture_est_refuse():
    exercice = services.exercice_pour(JOUR)
    services.cloturer_exercice(exercice, direction())

    with pytest.raises(ExerciceCloture):
        services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Trop tard")


def test_valider_une_ecriture_manuelle_est_refuse_si_l_exercice_est_devenu_cloture():
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Test OD")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal("5000")
    )
    # Simule une clôture concurrente (impossible via l'écran, qui bloque tant qu'un brouillon
    # reste dans la période — ce test vérifie la seconde ligne de défense au moment de valider).
    ExerciceComptable.objects.filter(annee=JOUR.year).update(statut=StatutExercice.CLOTURE)

    with pytest.raises(ExerciceCloture):
        services.valider_ecriture_manuelle(ecriture, direction())


# --- rapports : grand livre, balance, bilan, compte de résultat (Phase 6) ---


def _compte(numero):
    return Compte.objects.get(numero=numero)


def test_grand_livre_avec_solde_calcule_le_solde_cumule():
    caisse = _compte("571000")
    autre = CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 10), libelle="Un",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=autre.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 20), libelle="Deux",
        lignes=[
            LigneSaisie(compte=autre.numero, sens=SensEcriture.DEBIT, montant=Decimal("400")),
            LigneSaisie(compte="571000", sens=SensEcriture.CREDIT, montant=Decimal("400")),
        ],
    )

    lignes = services.grand_livre_avec_solde(caisse)

    assert [l["solde_cumule"] for l in lignes] == [Decimal("1000"), Decimal("600")]


def test_balance_agrege_debit_credit_et_solde_par_compte():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Test",
        lignes=_lignes_equilibrees(charge, tresorerie, montant="7000"),
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert lignes[charge.numero]["total_debit"] == Decimal("7000")
    assert lignes[charge.numero]["solde_debiteur"] == Decimal("7000")
    assert lignes[charge.numero]["solde_crediteur"] == Decimal("0")
    assert lignes[tresorerie.numero]["total_credit"] == Decimal("7000")
    assert lignes[tresorerie.numero]["solde_crediteur"] == Decimal("7000")


def test_balance_filtre_par_periode():
    charge, tresorerie = CompteFactory(), CompteFactory()
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 1, 15), libelle="Janvier",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 6, 15), libelle="Juin",
        lignes=_lignes_equilibrees(charge, tresorerie),
    )

    lignes = {l["compte__numero"]: l for l in services.balance(debut=date(2026, 1, 1), fin=date(2026, 3, 31))}

    assert lignes[charge.numero]["total_debit"] == Decimal("1000")


def test_balance_exclut_les_brouillons_non_valides():
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    lignes = {l["compte__numero"]: l for l in services.balance()}

    assert charge.numero not in lignes


def test_declaration_tva_calcule_la_tva_nette():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Péage facturé",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("100")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("18")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("118")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("180")
    assert rapport["tva_deductible"] == Decimal("18")
    assert rapport["tva_nette"] == Decimal("162")


def test_declaration_tva_negative_est_un_credit_reportable():
    charge, tva_deductible, caisse = _compte("628100"), _compte("445200"), _compte("571000")
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Grosse dépense facturée",
        lignes=[
            LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("180")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("1180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_collectee"] == Decimal("0")
    assert rapport["tva_deductible"] == Decimal("180")
    assert rapport["tva_nette"] == Decimal("-180")


def test_declaration_tva_filtre_par_periode():
    clients, ventes, tva_collectee = _compte("411000"), _compte("706100"), _compte("443300")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2026, 1, 15), libelle="Vente janvier",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva_collectee.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )

    rapport = services.declaration_tva(debut=date(2026, 6, 1), fin=date(2026, 6, 30))

    assert rapport["tva_collectee"] == Decimal("0")


def test_declaration_tva_exclut_les_brouillons_non_valides():
    tva_deductible = _compte("445200")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=tva_deductible.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.declaration_tva(debut=date(2026, 9, 1), fin=date(2026, 9, 30))

    assert rapport["tva_deductible"] == Decimal("0")


def test_compte_de_resultat_calcule_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes, tva = _compte("411000"), _compte("706100"), _compte("443300")
    caisse, carburant = _compte("571000"), _compte("605100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1180")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
            LigneSaisie(compte=tva.numero, sens=SensEcriture.CREDIT, montant=Decimal("180")),
        ],
    )
    services.passer_ecriture(
        journal=Journal.CAISSE, date_ecriture=JOUR, libelle="Plein",
        lignes=[
            LigneSaisie(compte=carburant.numero, sens=SensEcriture.DEBIT, montant=Decimal("300")),
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.CREDIT, montant=Decimal("300")),
        ],
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_produits"] == Decimal("1000")  # la TVA collectée n'est pas un produit
    assert rapport["total_charges"] == Decimal("300")
    assert rapport["resultat_net"] == Decimal("700")


def test_compte_de_resultat_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    charge = CompteFactory()
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.compte_de_resultat(exercice)

    assert rapport["total_charges"] == Decimal("0")
    assert rapport["charges"] == []


def test_bilan_equilibre_avec_le_resultat_net():
    exercice = services.exercice_pour(JOUR)
    clients, ventes = _compte("411000"), _compte("706100")
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=JOUR, libelle="Vente",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("1000")
    assert rapport["total_passif"] == Decimal("0")
    assert rapport["resultat_net"] == Decimal("1000")
    assert rapport["total_passif_avec_resultat"] == rapport["total_actif"] == Decimal("1000")


def test_bilan_exclut_les_brouillons_non_valides():
    exercice = services.exercice_pour(JOUR)
    caisse = _compte("571000")
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=JOUR, libelle="Brouillon")
    services.ajouter_ligne_manuelle(
        ecriture, finances(), compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("5000")
    )

    rapport = services.bilan(exercice)

    assert rapport["total_actif"] == Decimal("0")
    assert rapport["actif"] == []


def test_bilan_est_cumulatif_mais_compte_de_resultat_reste_par_exercice():
    clients, ventes = _compte("411000"), _compte("706100")
    exercice_2025 = services.exercice_pour(date(2025, 6, 1))
    services.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2025, 6, 1), libelle="Vente 2025",
        lignes=[
            LigneSaisie(compte=clients.numero, sens=SensEcriture.DEBIT, montant=Decimal("500")),
            LigneSaisie(compte=ventes.numero, sens=SensEcriture.CREDIT, montant=Decimal("500")),
        ],
    )
    exercice_2026 = services.exercice_pour(JOUR)

    bilan_2026 = services.bilan(exercice_2026)
    resultat_2026 = services.compte_de_resultat(exercice_2026)

    assert bilan_2026["total_actif"] == Decimal("500")  # cumulatif : reprend 2025
    assert resultat_2026["total_produits"] == Decimal("0")  # la vente 2025 n'est pas dans 2026
    assert services.compte_de_resultat(exercice_2025)["total_produits"] == Decimal("500")


def test_bilan_classe_aussi_les_comptes_de_passif():
    exercice = services.exercice_pour(JOUR)
    caisse, capital = _compte("571000"), _compte("101000")
    services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=JOUR, libelle="Apport",
        lignes=[
            LigneSaisie(compte=caisse.numero, sens=SensEcriture.DEBIT, montant=Decimal("2000")),
            LigneSaisie(compte=capital.numero, sens=SensEcriture.CREDIT, montant=Decimal("2000")),
        ],
    )

    rapport = services.bilan(exercice)

    lignes_passif = {l["compte__numero"]: l for l in rapport["passif"]}
    assert lignes_passif[capital.numero]["montant"] == Decimal("2000")
    assert rapport["total_passif"] == Decimal("2000")
    assert rapport["total_actif"] == Decimal("2000")
