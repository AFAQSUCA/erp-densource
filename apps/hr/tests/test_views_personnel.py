"""Écrans du personnel : liste, fiche, recrutement, modification, jours exceptionnels."""

from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import Chauffeur
from apps.hr import services
from apps.hr.models import AttributionConge, Departement, Personnel

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "nom": "Bamba",
        "prenom": "Issa",
        "poste": "Mécanicien",
        "departement": Departement.PARC_AUTO,
        "type_contrat": "CDI",
        "date_embauche": "2026-09-01",
        "salaire_base": "300000",
        "superieur": "",
        "utilisateur": "",
    }
    donnees.update(surcharges)
    return donnees


def _donnees_modification(**surcharges):
    donnees = _donnees(**surcharges)
    del donnees["date_embauche"]
    return donnees


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.RH])
def test_le_personnel_est_consultable_par_admin_direction_et_rh(client, role):
    _connecte(client, role)
    employe = PersonnelFactory()

    assert client.get(reverse("hr:personnel_liste")).status_code == 200
    assert client.get(reverse("hr:personnel_detail", args=[employe.pk])).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.PARCAUTO, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_le_personnel_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)
    employe = PersonnelFactory()

    assert client.get(reverse("hr:personnel_liste")).status_code == 403
    assert client.get(reverse("hr:personnel_detail", args=[employe.pk])).status_code == 403
    assert client.get(reverse("hr:personnel_nouveau")).status_code == 403


def test_la_direction_lit_le_personnel_sans_pouvoir_le_modifier(client):
    _connecte(client, Role.DIRECTION)
    employe = PersonnelFactory()

    assert client.get(reverse("hr:personnel_nouveau")).status_code == 403
    assert client.get(reverse("hr:personnel_modifier", args=[employe.pk])).status_code == 403
    assert client.post(reverse("hr:personnel_attribution", args=[employe.pk]), {}).status_code == 403
    assert client.get(reverse("hr:personnel_importer")).status_code == 403
    texte = client.get(reverse("hr:personnel_detail", args=[employe.pk])).content.decode()
    assert "Modifier" not in texte and "Accorder" not in texte


# --- liste ---


def test_la_liste_filtre_par_departement_et_par_texte(client):
    _connecte(client, Role.RH)
    PersonnelFactory(nom="Bamba", departement=Departement.PARC_AUTO)
    PersonnelFactory(nom="Coulibaly", departement=Departement.COMMERCIAL)

    parc = client.get(reverse("hr:personnel_liste"), {"departement": "PARC_AUTO"})
    texte = client.get(reverse("hr:personnel_liste"), {"q": "couli"})

    assert [p.nom for p in parc.context["personnel"]] == ["Bamba"]
    assert [p.nom for p in texte.context["personnel"]] == ["Coulibaly"]


def test_la_liste_du_personnel_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    _connecte(client, Role.RH)
    chef = PersonnelFactory()
    for _ in range(12):
        PersonnelFactory(superieur=chef)

    with django_assert_max_num_queries(10):
        assert client.get(reverse("hr:personnel_liste")).status_code == 200


def test_la_liste_vide_explique_quoi_faire(client):
    _connecte(client, Role.RH)

    assert "Enregistrez un premier recrutement" in client.get(reverse("hr:personnel_liste")).content.decode()


# --- fiche ---


def test_la_fiche_affiche_salaire_droits_et_conges(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory(salaire_base=1250000)

    reponse = client.get(reverse("hr:personnel_detail", args=[employe.pk]))

    assert "1\xa0250\xa0000 FCFA" in reponse.content.decode().replace(" ", "\xa0")
    assert reponse.context["droits"]["disponible"] == 12
    assert "Aucun congé demandé" in reponse.content.decode()


def test_la_fiche_signale_l_absence_de_compte_et_liste_l_equipe(client):
    _connecte(client, Role.RH)
    chef = PersonnelFactory(nom="Diallo")
    PersonnelFactory(nom="Sanogo", superieur=chef)

    texte = client.get(reverse("hr:personnel_detail", args=[chef.pk])).content.decode()

    assert "pas d'accès aux congés" in texte
    assert "Sanogo" in texte


def test_les_champs_saisis_sont_echappes(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory(nom="<b>Piège</b>")

    texte = client.get(reverse("hr:personnel_detail", args=[employe.pk])).content.decode()

    assert "<b>Piège</b>" not in texte
    assert "&lt;b&gt;Piège&lt;/b&gt;" in texte


# --- recrutement ---


def test_la_rh_recrute_un_employe(client):
    _connecte(client, Role.RH)
    chef = PersonnelFactory()

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(superieur=chef.pk), follow=True)

    employe = Personnel.objects.get(nom="Bamba", prenom="Issa")
    assert employe.superieur == chef and employe.type_contrat == "CDI"
    assert employe.matricule.startswith("PERS-")
    assert reponse.redirect_chain[-1][0] == reverse("hr:personnel_detail", args=[employe.pk])
    assert any("Issa Bamba" in m and employe.matricule in m for m in _messages(reponse))


def test_recruter_un_chauffeur_cree_sa_fiche_et_le_dit(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(poste="Chauffeur"), follow=True)

    assert Chauffeur.objects.filter(personnel__nom="Bamba").exists()
    assert any("fiche chauffeur" in m for m in _messages(reponse))


def test_un_recrutement_incomplet_reste_sur_le_formulaire(client):
    _connecte(client, Role.RH)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(nom="", salaire_base="-5"))

    assert reponse.status_code == 200
    assert not Personnel.objects.exists()


# --- poste : liste déroulante + « Autre » ---


def test_le_poste_est_une_liste_deroulante(client):
    _connecte(client, Role.RH)

    reponse = client.get(reverse("hr:personnel_nouveau"))

    valeurs = dict(reponse.context["form"].fields["poste"].choices)
    assert "Chauffeur" in valeurs and "AUTRE" in valeurs


def test_choisir_autre_sans_le_preciser_est_refuse(client):
    _connecte(client, Role.RH)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(poste="AUTRE", poste_autre=""))

    assert reponse.status_code == 200
    assert not Personnel.objects.exists()
    assert "Précisez le poste" in reponse.content.decode()


def test_choisir_autre_avec_un_intitule_l_enregistre_tel_quel(client):
    _connecte(client, Role.RH)

    client.post(
        reverse("hr:personnel_nouveau"), _donnees(poste="AUTRE", poste_autre="Dispatcheur logistique")
    )

    employe = Personnel.objects.get(nom="Bamba")
    assert employe.poste == "Dispatcheur logistique"


def test_un_poste_hors_liste_est_prerempli_en_autre_a_la_modification(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory(poste="Chef d'atelier")

    reponse = client.get(reverse("hr:personnel_modifier", args=[employe.pk]))

    initial = reponse.context["form"].initial
    assert (initial["poste"], initial["poste_autre"]) == ("AUTRE", "Chef d'atelier")


def test_le_formulaire_ne_propose_que_les_comptes_libres(client):
    _connecte(client, Role.RH)
    libre = UserFactory(role=Role.FINANCES, username="libre")
    pris = UserFactory(role=Role.FINANCES, username="pris")
    PersonnelFactory(utilisateur=pris)

    reponse = client.get(reverse("hr:personnel_nouveau"))
    propositions = set(reponse.context["form"].fields["utilisateur"].queryset)

    assert libre in propositions and pris not in propositions


def test_recruter_avec_un_compte_deja_rattache_est_refuse(client):
    _connecte(client, Role.RH)
    pris = UserFactory(role=Role.FINANCES)
    PersonnelFactory(utilisateur=pris)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(utilisateur=pris.pk))

    assert reponse.status_code == 200
    assert not Personnel.objects.filter(nom="Bamba").exists()


def test_le_recrutement_exige_le_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.RH))

    assert client.post(reverse("hr:personnel_nouveau"), _donnees()).status_code == 403


# --- modification ---


def test_la_rh_modifie_la_fiche(client):
    _connecte(client, Role.RH)
    chef = PersonnelFactory()
    employe = PersonnelFactory(matricule="MAT-6001")
    compte = UserFactory(role=Role.FINANCES)

    reponse = client.post(
        reverse("hr:personnel_modifier", args=[employe.pk]),
        _donnees_modification(
            poste="AUTRE", poste_autre="Chef comptable", superieur=chef.pk, utilisateur=compte.pk
        ),
        follow=True,
    )

    employe.refresh_from_db()
    assert (employe.poste, employe.superieur, employe.utilisateur) == ("Chef comptable", chef, compte)
    assert (employe.matricule, employe.date_embauche) == ("MAT-6001", date(2024, 1, 15))
    assert any("mise à jour" in m for m in _messages(reponse))


def test_le_formulaire_de_modification_est_prerempli_sans_matricule(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory(nom="Kone", poste="Comptable")

    reponse = client.get(reverse("hr:personnel_modifier", args=[employe.pk]))

    assert reponse.context["form"].initial["nom"] == "Kone"
    assert "matricule" not in reponse.context["form"].fields
    assert "MAT" in reponse.content.decode()  # rappelé dans le texte d'aide


def test_le_formulaire_de_modification_n_offre_pas_l_employe_comme_son_propre_superieur(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory()

    reponse = client.get(reverse("hr:personnel_modifier", args=[employe.pk]))

    assert employe not in reponse.context["form"].fields["superieur"].queryset


def test_une_boucle_hierarchique_est_refusee_a_la_modification(client):
    _connecte(client, Role.RH)
    chef = PersonnelFactory()
    bas = PersonnelFactory(superieur=chef)

    reponse = client.post(
        reverse("hr:personnel_modifier", args=[chef.pk]), _donnees_modification(superieur=bas.pk)
    )

    assert "boucle" in reponse.content.decode()
    chef.refresh_from_db()
    assert chef.superieur is None


# --- jours exceptionnels ---


def test_la_rh_accorde_des_jours_exceptionnels(client):
    compte_rh = _connecte(client, Role.RH)
    PersonnelFactory(utilisateur=compte_rh)
    employe = PersonnelFactory()

    reponse = client.post(
        reverse("hr:personnel_attribution", args=[employe.pk]),
        {"annee": 2026, "jours": 3, "motif": "Naissance"},
        follow=True,
    )

    attribution = AttributionConge.objects.get(employe=employe)
    assert (attribution.jours, attribution.accorde_par) == (3, compte_rh)
    assert services.droits_conges(employe, 2026)["disponible"] == 15
    assert any("3 jour(s) exceptionnel(s)" in m for m in _messages(reponse))
    assert "Naissance" in reponse.content.decode()


def test_l_attribution_exige_un_motif_et_des_jours_positifs(client):
    _connecte(client, Role.RH)
    employe = PersonnelFactory()

    reponse = client.post(
        reverse("hr:personnel_attribution", args=[employe.pk]),
        {"annee": 2026, "jours": 0, "motif": ""},
        follow=True,
    )

    assert not AttributionConge.objects.exists()
    assert len(_messages(reponse)) >= 2


def test_l_admin_ne_peut_pas_accorder_de_jours_c_est_reserve_a_la_rh(client):
    _connecte(client, Role.ADMIN)
    employe = PersonnelFactory()

    reponse = client.post(
        reverse("hr:personnel_attribution", args=[employe.pk]),
        {"annee": 2026, "jours": 2, "motif": "Test"},
        follow=True,
    )

    assert not AttributionConge.objects.exists()
    assert any("réservée à la RH" in m for m in _messages(reponse))


def test_la_rh_ne_peut_pas_s_accorder_de_jours(client):
    compte_rh = _connecte(client, Role.RH)
    fiche = PersonnelFactory(utilisateur=compte_rh)

    client.post(
        reverse("hr:personnel_attribution", args=[fiche.pk]),
        {"annee": 2026, "jours": 2, "motif": "Pour moi"},
    )

    assert not AttributionConge.objects.exists()
    texte = client.get(reverse("hr:personnel_detail", args=[fiche.pk])).content.decode()
    assert "Accorder des jours exceptionnels" not in texte
