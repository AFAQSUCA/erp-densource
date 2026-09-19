"""Fiche chauffeur : recherche, échéances, modification, statut manuel."""

from datetime import date

import pytest

from apps.audit.models import AuditLog
from apps.drivers import services
from apps.drivers.exceptions import CategorieInvalide, StatutNonModifiable
from apps.drivers.models import StatutChauffeur

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db

AUJOURDHUI = date(2026, 9, 20)


# --- recherche ---


def test_rechercher_par_statut():
    libre = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.SUSPENDU)

    assert list(services.rechercher_chauffeurs(statut=StatutChauffeur.DISPONIBLE)) == [libre]


def test_rechercher_par_nom_prenom_matricule_ou_permis():
    cible = ChauffeurFactory(
        personnel__nom="Diomandé",
        personnel__prenom="Seydou",
        personnel__matricule="CH-042",
        numero_permis="PC-998877",
    )
    ChauffeurFactory()

    for terme in ("diomand", "seydou", "ch-042", "998877"):
        assert list(services.rechercher_chauffeurs(recherche=terme)) == [cible], terme


def test_rechercher_ignore_un_statut_inconnu_et_les_espaces():
    ChauffeurFactory()

    assert services.rechercher_chauffeurs(statut="???", recherche="   ").count() == 1


def test_rechercher_trie_par_nom_puis_prenom():
    b = ChauffeurFactory(personnel__nom="Bamba", personnel__prenom="Issa")
    a2 = ChauffeurFactory(personnel__nom="Adou", personnel__prenom="Zoé")
    a1 = ChauffeurFactory(personnel__nom="Adou", personnel__prenom="Awa")

    assert list(services.rechercher_chauffeurs()) == [a1, a2, b]


def test_rechercher_les_chauffeurs_a_renouveler():
    from datetime import timedelta

    from django.utils import timezone

    aujourdhui = timezone.localdate()
    lointain = aujourdhui + timedelta(days=1800)
    proche = ChauffeurFactory(
        date_expiration_permis=lointain, date_expiration_visite_medicale=aujourdhui
    )
    ChauffeurFactory(date_expiration_permis=lointain)

    resultat = services.rechercher_chauffeurs(a_renouveler=True)

    assert list(resultat) == [proche]


def test_chauffeurs_avec_echeance_proche_retourne_les_identifiants():
    proche = ChauffeurFactory(date_expiration_permis=date(2026, 10, 10))
    ChauffeurFactory(date_expiration_permis=date(2027, 6, 1))

    assert services.chauffeurs_avec_echeance_proche(aujourd_hui=AUJOURDHUI) == {proche.pk}


# --- échéances ---


def test_etat_echeances_couvre_permis_et_visite_medicale():
    fiche = ChauffeurFactory(
        date_expiration_permis=date(2026, 9, 1),
        date_expiration_visite_medicale=date(2026, 10, 1),
    )

    permis, visite = services.etat_echeances(fiche, aujourd_hui=AUJOURDHUI)

    assert (permis["libelle"], permis["etat"], permis["jours_restants"]) == (
        "Permis de conduire",
        "EXPIRE",
        -19,
    )
    assert (visite["libelle"], visite["etat"], visite["jours_restants"]) == (
        "Visite médicale",
        "A_RENOUVELER",
        11,
    )


def test_etat_echeances_signale_les_dates_non_renseignees():
    fiche = ChauffeurFactory()

    assert [e["etat"] for e in services.etat_echeances(fiche, aujourd_hui=AUJOURDHUI)] == [
        "MANQUANT",
        "MANQUANT",
    ]


# --- modification de la fiche ---


def test_modifier_chauffeur_enregistre_les_informations():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(
        fiche,
        telephone=" +2250700112233 ",
        contact_urgence="Awa Traoré - 0701020304",
        numero_permis="PC-123456",
        categories_permis=["E", "C"],
        date_expiration_permis=date(2029, 3, 1),
        date_expiration_visite_medicale=date(2027, 3, 1),
    )

    fiche.refresh_from_db()
    assert fiche.telephone == "+2250700112233"
    assert fiche.contact_urgence == "Awa Traoré - 0701020304"
    assert fiche.numero_permis == "PC-123456"
    assert fiche.categories_permis == ["C", "E"]  # triées
    assert fiche.date_expiration_permis == date(2029, 3, 1)


def test_modifier_chauffeur_retire_les_doublons_de_categories():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(fiche, categories_permis=["C", "C", "E"])

    fiche.refresh_from_db()
    assert fiche.categories_permis == ["C", "E"]


def test_modifier_chauffeur_refuse_une_categorie_inconnue_et_ne_change_rien():
    fiche = ChauffeurFactory(telephone="0700000000")

    with pytest.raises(CategorieInvalide, match="Z"):
        services.modifier_chauffeur(fiche, telephone="0799999999", categories_permis=["C", "Z"])

    fiche.refresh_from_db()
    assert fiche.telephone == "0700000000"


def test_modifier_chauffeur_peut_vider_les_champs_facultatifs():
    fiche = ChauffeurFactory(
        telephone="0700000000",
        numero_permis="X",
        categories_permis=["C"],
        date_expiration_permis=date(2029, 1, 1),
    )

    services.modifier_chauffeur(fiche)

    fiche.refresh_from_db()
    assert (fiche.telephone, fiche.numero_permis, fiche.categories_permis) == ("", "", [])
    assert fiche.date_expiration_permis is None


def test_modifier_chauffeur_ne_touche_ni_au_statut_ni_a_l_identite():
    fiche = ChauffeurFactory(statut=StatutChauffeur.SUSPENDU, personnel__nom="Kouyaté")

    services.modifier_chauffeur(fiche, telephone="0700000000")

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU
    assert fiche.personnel.nom == "Kouyaté"


def test_la_modification_de_la_fiche_est_auditee():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(fiche, numero_permis="PC-1")

    entree = AuditLog.objects.filter(
        entite="Chauffeur", entite_id=fiche.pk, action="UPDATE"
    ).latest("date_heure")
    assert entree.nouvelle_valeur["numero_permis"] == "PC-1"


# --- statut manuel ---


@pytest.mark.parametrize(
    ("depart", "arrivee"),
    [
        (StatutChauffeur.DISPONIBLE, StatutChauffeur.SUSPENDU),
        (StatutChauffeur.DISPONIBLE, StatutChauffeur.INACTIF),
        (StatutChauffeur.SUSPENDU, StatutChauffeur.DISPONIBLE),
        (StatutChauffeur.INACTIF, StatutChauffeur.DISPONIBLE),
        (StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF),
    ],
)
def test_changer_statut_manuel_entre_statuts_manuels(depart, arrivee):
    fiche = ChauffeurFactory(statut=depart)

    services.changer_statut_manuel(fiche, arrivee)

    fiche.refresh_from_db()
    assert fiche.statut == arrivee


@pytest.mark.parametrize("verrouille", [StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE])
def test_un_chauffeur_en_mission_ou_en_conge_ne_se_modifie_pas_a_la_main(verrouille):
    fiche = ChauffeurFactory(statut=verrouille)

    with pytest.raises(StatutNonModifiable, match="missions et les congés"):
        services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)

    fiche.refresh_from_db()
    assert fiche.statut == verrouille


@pytest.mark.parametrize("cible", [StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE, "VOLANT"])
def test_on_ne_pose_pas_a_la_main_les_statuts_geres_par_les_workflows(cible):
    fiche = ChauffeurFactory()

    with pytest.raises(StatutNonModifiable, match="Disponible, Suspendu et Inactif"):
        services.changer_statut_manuel(fiche, cible)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE
