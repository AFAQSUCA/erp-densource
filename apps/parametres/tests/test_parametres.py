"""Paramètres de l'application (audit M1-09, M1-10) : lecture, modification, droits, contrôles, écran."""

from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.parametres import services
from apps.parametres.models import Parametres

pytestmark = pytest.mark.django_db


def _formulaire(**surcharges):
    defauts = Parametres()
    donnees = {champ: str(getattr(defauts, champ)) for champ in services.CHAMPS}
    donnees.update({cle: str(valeur) for cle, valeur in surcharges.items()})
    return donnees


# --- lecture ---


def test_sans_enregistrement_les_valeurs_du_cahier_des_charges_s_appliquent_sans_rien_ecrire():
    p = services.parametres()

    assert (p.delai_alerte_jours, p.seuil_conso_jaune_pct, p.seuil_conso_rouge_pct, p.seuil_conso_saisie_pct) == (
        30, Decimal("20"), Decimal("40"), Decimal("60")
    )
    assert (p.conso_min_l100, p.conso_max_l100, p.ecart_km_max) == (Decimal("20"), Decimal("45"), 5000)
    assert (p.tva_defaut, p.delai_paiement_defaut_jours) == (Decimal("18.00"), 30)
    assert (p.delai_validation_n1_heures, p.delai_validation_n2_heures, p.droit_annuel_jours) == (48, 24, 26)
    assert not Parametres.objects.exists()


def test_delai_alerte_prend_la_valeur_fournie_sinon_le_parametre():
    services.modifier_parametres(UserFactory(role=Role.ADMIN), delai_alerte_jours=45)

    assert services.delai_alerte() == 45
    assert services.delai_alerte(10) == 10


# --- modification ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_l_admin_et_la_direction_modifient(role):
    acteur = UserFactory(role=role)

    services.modifier_parametres(acteur, delai_alerte_jours=60, tva_defaut=Decimal("9"))

    p = services.parametres()
    assert (p.delai_alerte_jours, p.tva_defaut, p.modifie_par) == (60, Decimal("9.00"), acteur)
    assert p.droit_annuel_jours == 26  # un champ absent garde sa valeur


def test_un_superutilisateur_agit_en_admin():
    services.modifier_parametres(UserFactory(role=Role.CHAUFFEUR, is_superuser=True), ecart_km_max=8000)

    assert services.parametres().ecart_km_max == 8000


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_autres_roles_ne_modifient_pas(role):
    with pytest.raises(services.ModificationNonAutorisee):
        services.modifier_parametres(UserFactory(role=role), delai_alerte_jours=60)
    assert not Parametres.objects.exists()


def test_les_modifications_successives_gardent_une_seule_ligne():
    admin = UserFactory(role=Role.ADMIN)
    services.modifier_parametres(admin, delai_alerte_jours=40)
    services.modifier_parametres(admin, delai_alerte_jours=50)

    assert Parametres.objects.count() == 1 and services.parametres().delai_alerte_jours == 50


def test_une_seconde_ligne_est_refusee_par_la_base():
    services.modifier_parametres(UserFactory(role=Role.ADMIN), delai_alerte_jours=40)

    with pytest.raises(IntegrityError):
        Parametres.objects.create(pk=2)


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("delai_alerte_jours", 0),
        ("delai_alerte_jours", 366),
        ("tva_defaut", Decimal("0")),
        ("tva_defaut", Decimal("101")),
        ("ecart_km_max", 50),
        ("droit_annuel_jours", 61),
        ("delai_validation_n1_heures", 0),
        ("conso_min_l100", Decimal("0")),
    ],
)
def test_une_valeur_hors_bornes_est_refusee(champ, valeur):
    with pytest.raises(services.ParametresInvalides) as erreur:
        services.modifier_parametres(UserFactory(role=Role.ADMIN), **{champ: valeur})

    assert champ in erreur.value.erreurs
    assert not Parametres.objects.exists()


@pytest.mark.parametrize(
    ("valeurs", "champ_en_erreur"),
    [
        ({"seuil_conso_jaune_pct": Decimal("40"), "seuil_conso_rouge_pct": Decimal("40")}, "seuil_conso_rouge_pct"),
        ({"seuil_conso_rouge_pct": Decimal("70")}, "seuil_conso_saisie_pct"),
        ({"conso_min_l100": Decimal("50")}, "conso_max_l100"),
    ],
)
def test_des_seuils_incoherents_sont_refuses(valeurs, champ_en_erreur):
    with pytest.raises(services.ParametresInvalides) as erreur:
        services.modifier_parametres(UserFactory(role=Role.ADMIN), **valeurs)

    assert champ_en_erreur in erreur.value.erreurs


def test_un_champ_inconnu_est_refuse():
    with pytest.raises(services.ParametresError, match="inconnu"):
        services.modifier_parametres(UserFactory(role=Role.ADMIN), modifie_par=None)


def test_chaque_modification_est_tracee_avec_l_ancienne_et_la_nouvelle_valeur(client):
    admin = UserFactory(role=Role.ADMIN)
    client.force_login(admin)  # l'auteur d'une entrée d'audit est celui de la requête
    client.post(reverse("parametres:modifier"), _formulaire(delai_alerte_jours=40))
    client.post(reverse("parametres:modifier"), _formulaire(delai_alerte_jours=50))

    entree = AuditLog.objects.filter(module="PARAMETRES", action=ActionChoices.UPDATE).latest("pk")
    assert entree.ancienne_valeur["delai_alerte_jours"] == 40
    assert entree.nouvelle_valeur["delai_alerte_jours"] == 50
    assert entree.utilisateur == admin


# --- écran ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_l_ecran_affiche_les_valeurs_en_vigueur_et_celles_du_cahier_des_charges(client, role):
    client.force_login(UserFactory(role=role))

    page = client.get(reverse("parametres:modifier")).content.decode()

    assert "Paramètres" in page and 'name="delai_alerte_jours"' in page and 'value="30"' in page
    assert 'name="seuil_conso_jaune_pct" value="20"' in page  # point décimal : un champ numérique refuse la virgule
    assert 'name="tva_defaut" value="18.00"' in page
    assert "Cahier des charges : 45" in page
    assert "les valeurs du cahier des charges s'appliquent" in page


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_l_ecran_est_refuse_aux_autres_roles(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("parametres:modifier")).status_code == 403
    assert client.post(reverse("parametres:modifier"), _formulaire(delai_alerte_jours=60)).status_code == 403
    assert not Parametres.objects.exists()


def test_enregistrer_l_ecran_applique_les_valeurs(client):
    client.force_login(UserFactory(role=Role.DIRECTION))

    reponse = client.post(reverse("parametres:modifier"), _formulaire(delai_alerte_jours=45), follow=True)

    assert services.parametres().delai_alerte_jours == 45
    assert "Paramètres enregistrés" in reponse.content.decode()
    assert "Dernière modification le" in reponse.content.decode()


def test_l_ecran_affiche_l_incoherence_sous_le_champ(client):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.post(reverse("parametres:modifier"), _formulaire(conso_min_l100="50"))

    assert reponse.status_code == 200
    assert "La consommation maximale doit être supérieure" in reponse.content.decode()
    assert not Parametres.objects.exists()


def test_l_ecran_refuse_une_valeur_hors_bornes(client):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.post(reverse("parametres:modifier"), _formulaire(delai_alerte_jours="0"))

    assert reponse.status_code == 200 and reponse.context["form"].errors["delai_alerte_jours"]
    assert not Parametres.objects.exists()


def test_le_menu_propose_les_parametres_a_l_admin_et_a_la_direction_seulement(client):
    for role, visible in ((Role.ADMIN, True), (Role.DIRECTION, True), (Role.RH, False), (Role.FINANCES, False)):
        client.force_login(UserFactory(role=role))
        assert (reverse("parametres:modifier") in client.get(reverse("home")).content.decode()) is visible
