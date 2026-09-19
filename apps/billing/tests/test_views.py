"""Écrans de facturation : accès, cycle de vie, règlements, dépenses, version imprimable."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import Depense, Facture, ModePaiement, Reglement, StatutFacture
from apps.customers.tests.factories import ClientFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .helpers import JOUR, a_valider, brouillon, direction, emise, finances, mission_livree

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _texte(reponse):
    return reponse.content.decode().replace("\xa0", " ").replace(" ", " ")


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES])
def test_la_facturation_est_accessible_a_admin_direction_et_finances(client, role):
    _connecte(client, role)
    facture = brouillon()

    for url in (
        reverse("billing:factures"),
        reverse("billing:facture", args=[facture.pk]),
        reverse("billing:imprimer", args=[facture.pk]),
        reverse("billing:depenses"),
    ):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize(
    "role", [Role.RH, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_la_facturation_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)
    facture = brouillon()

    for url in (
        reverse("billing:factures"),
        reverse("billing:facture", args=[facture.pk]),
        reverse("billing:imprimer", args=[facture.pk]),
        reverse("billing:nouvelle"),
        reverse("billing:depenses"),
        reverse("billing:depense_nouvelle"),
    ):
        assert client.get(url).status_code == 403, url


def test_la_direction_lit_sans_pouvoir_preparer(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("billing:nouvelle")).status_code == 403
    assert client.get(reverse("billing:depense_nouvelle")).status_code == 403
    texte = client.get(reverse("billing:factures")).content.decode()
    assert "Nouvelle facture" not in texte


def test_la_facturation_exige_la_connexion(client):
    assert client.get(reverse("billing:factures")).status_code == 302


# --- liste ---


def test_la_liste_affiche_factures_creances_et_echeances(client):
    _connecte(client, Role.FINANCES)
    echue = emise(aujourd_hui=date(2026, 7, 1))  # échéance 31/07 : échue
    en_cours = emise(aujourd_hui=timezone.localdate())
    brouillon()

    reponse = client.get(reverse("billing:factures"))
    texte = _texte(reponse)

    assert len(reponse.context["factures"]) == 3
    assert reponse.context["creances"]["nombre"] == 2 and reponse.context["creances"]["nombre_echues"] == 1
    assert echue.numero in texte and en_cours.numero in texte and "Brouillon" in texte
    assert "Échue" in texte
    assert "2 360 000" in texte  # 2 x 1 180 000 de créances


def test_la_liste_se_filtre_par_texte_statut_client_et_echeance(client):
    _connecte(client, Role.FINANCES)
    cimaf = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    facture_cimaf = emise(client=cimaf, aujourd_hui=date(2026, 7, 1))
    emise(aujourd_hui=timezone.localdate())
    url = reverse("billing:factures")

    def numeros(**params):
        return [f.pk for f in client.get(url, params).context["factures"]]

    assert numeros(q="CIMAF") == [facture_cimaf.pk]
    assert numeros(client=cimaf.pk) == [facture_cimaf.pk]
    assert numeros(echues="on") == [facture_cimaf.pk]
    assert len(numeros(statut="EMISE")) == 2
    assert len(numeros(statut="PAYEE")) == 0
    assert len(numeros(statut="N_IMPORTE_QUOI", client="abc")) == 2  # invalides ignorés


def test_le_bouton_nouvelle_facture_indique_les_missions_a_facturer(client):
    _connecte(client, Role.FINANCES)
    mission_livree()
    mission_livree()

    assert "2 missions à facturer" in client.get(reverse("billing:factures")).content.decode()


def test_la_liste_est_paginee_tolerante_et_a_requetes_constantes(client, django_assert_max_num_queries):
    _connecte(client, Role.FINANCES)
    for _ in range(22):
        brouillon()

    with django_assert_max_num_queries(12):
        premiere = client.get(reverse("billing:factures"))
    inconnue = client.get(reverse("billing:factures"), {"page": 99})

    assert len(premiere.context["factures"]) == 20
    assert inconnue.status_code == 200 and inconnue.context["page_obj"].number == 2


def test_liste_vide(client):
    _connecte(client, Role.FINANCES)

    assert "Une facture se prépare depuis une mission livrée" in client.get(reverse("billing:factures")).content.decode()


# --- création ---


def test_finances_cree_un_brouillon_depuis_une_mission_livree(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree(prix="800000")

    reponse = client.post(reverse("billing:nouvelle"), {"mission": mission.pk}, follow=True)

    facture = Facture.objects.get(mission=mission)
    assert facture.statut == StatutFacture.BROUILLON and facture.montant_ttc == Decimal("944000")
    assert reponse.redirect_chain[-1][0] == reverse("billing:facture", args=[facture.pk])
    assert any("Brouillon créé" in m for m in _messages(reponse))


def test_le_formulaire_ne_propose_que_les_missions_facturables(client):
    _connecte(client, Role.FINANCES)
    livree = mission_livree()
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    propositions = set(client.get(reverse("billing:nouvelle")).context["form"].fields["mission"].queryset)

    assert livree in propositions and planifiee not in propositions


def test_une_mission_non_facturable_postee_a_la_main_est_refusee(client):
    _connecte(client, Role.FINANCES)
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    reponse = client.post(reverse("billing:nouvelle"), {"mission": planifiee.pk})

    assert reponse.status_code == 200 and not Facture.objects.exists()


def test_la_mission_est_preselectionnee_depuis_l_adresse(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree()

    reponse = client.get(reverse("billing:nouvelle"), {"mission": mission.pk})

    assert reponse.context["form"].initial["mission"] == str(mission.pk)


def test_le_formulaire_de_creation_exige_le_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))

    assert http.post(reverse("billing:nouvelle"), {"mission": mission_livree().pk}).status_code == 403


# --- fiche et actions ---


def test_la_fiche_d_un_brouillon_propose_les_actions_de_finances(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    texte = client.get(reverse("billing:facture", args=[facture.pk])).content.decode()

    for libelle in ("Ajouter une ligne", "Mettre à jour", "Soumettre à la direction", "Abandonner le brouillon"):
        assert libelle in texte
    assert "Valider et émettre" not in texte


def test_la_direction_valide_ce_qui_est_a_valider_et_pas_finances_ni_admin(client):
    facture = a_valider()
    url = reverse("billing:facture", args=[facture.pk])

    _connecte(client, Role.DIRECTION)
    assert "Valider et émettre" in client.get(url).content.decode()
    for role in (Role.FINANCES, Role.ADMIN):
        _connecte(client, role)
        assert "Valider et émettre" not in client.get(url).content.decode()
    client.force_login(UserFactory(role="", is_superuser=True, is_staff=True))
    assert "Valider et émettre" not in client.get(url).content.decode()


def test_cycle_complet_soumettre_valider_regler(client):
    finance, chef = UserFactory(role=Role.FINANCES), UserFactory(role=Role.DIRECTION)
    facture = brouillon(prix="1000000")

    client.force_login(finance)
    reponse = client.post(reverse("billing:soumettre", args=[facture.pk]), follow=True)
    assert any("envoyée à la direction" in m for m in _messages(reponse))

    client.force_login(chef)
    reponse = client.post(reverse("billing:valider", args=[facture.pk]), follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE and facture.numero.startswith("FACT-")
    assert any(f"Facture {facture.numero} validée" in m for m in _messages(reponse))

    client.force_login(finance)
    reponse = client.post(
        reverse("billing:reglement_ajouter", args=[facture.pk]),
        {"date_reglement": timezone.localdate().isoformat(), "montant": "500000", "mode": "WAVE", "reference": "TX-1"},
        follow=True,
    )
    assert any("Reste à recouvrer : 680 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))
    reponse = client.post(
        reverse("billing:reglement_ajouter", args=[facture.pk]),
        {"date_reglement": timezone.localdate().isoformat(), "montant": "680000", "mode": "VIREMENT"},
        follow=True,
    )
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE
    assert any("Facture soldée" in m for m in _messages(reponse))


def test_finances_ne_peut_pas_valider_meme_en_postant_directement(client):
    facture = a_valider()
    _connecte(client, Role.FINANCES)

    assert client.post(reverse("billing:valider", args=[facture.pk])).status_code == 403
    assert client.post(reverse("billing:refuser", args=[facture.pk]), {"motif": "x"}).status_code == 403
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER


def test_la_direction_ne_peut_pas_soumettre_ni_regler(client):
    facture = emise()
    _connecte(client, Role.DIRECTION)

    assert client.post(reverse("billing:soumettre", args=[facture.pk])).status_code == 403
    assert client.post(reverse("billing:reglement_ajouter", args=[facture.pk]), {}).status_code == 403


def test_le_refus_exige_un_motif_puis_renvoie_en_brouillon(client):
    facture = a_valider()
    _connecte(client, Role.DIRECTION)
    url = reverse("billing:refuser", args=[facture.pk])

    reponse = client.post(url, {"motif": " "}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and _messages(reponse)

    reponse = client.post(url, {"motif": "Prix à revoir"}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.BROUILLON
    _connecte(client, Role.FINANCES)
    assert "Prix à revoir" in client.get(reverse("billing:facture", args=[facture.pk])).content.decode()


def test_abandonner_un_brouillon_retourne_a_la_liste_et_libere_la_mission(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    reponse = client.post(reverse("billing:abandonner", args=[facture.pk]), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("billing:factures")
    assert not Facture.objects.filter(pk=facture.pk).exists()
    assert any("Brouillon abandonné" in m for m in _messages(reponse))


def test_ajouter_puis_supprimer_une_ligne(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon(prix="1000000")

    client.post(
        reverse("billing:ligne_ajouter", args=[facture.pk]),
        {"designation": "Péages refacturés", "quantite": "1", "prix_unitaire_ht": "25000"},
    )
    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1025000")
    ligne = facture.lignes.get(designation="Péages refacturés")

    reponse = client.post(
        reverse("billing:ligne_supprimer", args=[facture.pk, ligne.pk]), follow=True
    )

    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1000000")
    assert any("Ligne supprimée" in m for m in _messages(reponse))


def test_une_ligne_invalide_donne_un_message_sans_rien_ajouter(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    reponse = client.post(
        reverse("billing:ligne_ajouter", args=[facture.pk]),
        {"designation": "", "quantite": "0", "prix_unitaire_ht": "-1"}, follow=True,
    )

    assert facture.lignes.count() == 1 and _messages(reponse)


def test_supprimer_la_ligne_d_une_autre_facture_est_refuse(client):
    _connecte(client, Role.FINANCES)
    facture, autre = brouillon(), brouillon()

    reponse = client.post(
        reverse("billing:ligne_supprimer", args=[facture.pk, autre.lignes.first().pk])
    )

    assert reponse.status_code == 404


def test_modifier_les_conditions_de_tva_et_de_delai(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon(prix="1000000")
    url = reverse("billing:conditions", args=[facture.pk])

    client.post(url, {"taux_tva": "0", "motif_exoneration": "", "delai_paiement_jours": "30"}, follow=True)
    facture.refresh_from_db()
    assert facture.taux_tva == Decimal("18")  # refusé : motif obligatoire

    client.post(url, {"taux_tva": "0", "motif_exoneration": "ONG", "delai_paiement_jours": "60"})
    facture.refresh_from_db()
    assert (facture.taux_tva, facture.motif_exoneration, facture.delai_paiement_jours) == (0, "ONG", 60)
    assert facture.montant_ttc == facture.montant_ht


def test_les_reglements_incoherents_donnent_un_message_d_erreur(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    url = reverse("billing:reglement_ajouter", args=[facture.pk])
    aujourd_hui = timezone.localdate().isoformat()

    trop = client.post(url, {"date_reglement": aujourd_hui, "montant": "9999999", "mode": "VIREMENT"}, follow=True)
    futur = client.post(url, {"date_reglement": "2999-01-01", "montant": "1000", "mode": "VIREMENT"}, follow=True)
    mode = client.post(url, {"date_reglement": aujourd_hui, "montant": "1000", "mode": "TROC"}, follow=True)

    assert any("dépasse le reste à recouvrer" in m for m in _messages(trop))
    assert any("futur" in m for m in _messages(futur))
    assert _messages(mode)
    assert Reglement.objects.count() == 0


def test_annuler_un_reglement_avec_motif(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement = services.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.CHEQUE, date_reglement=JOUR
    )
    url = reverse("billing:reglement_annuler", args=[facture.pk, reglement.pk])

    client.post(url, {"motif": " "}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE  # motif vide : rien ne change

    reponse = client.post(url, {"motif": "Chèque impayé"}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert any("Règlement annulé" in m for m in _messages(reponse))


def test_les_actions_n_acceptent_que_post_et_exigent_le_csrf():
    facture = a_valider()
    http = Client(enforce_csrf_checks=True)
    for nom, role in (
        ("valider", Role.DIRECTION), ("refuser", Role.DIRECTION),
        ("soumettre", Role.FINANCES), ("abandonner", Role.FINANCES),
    ):
        http.force_login(UserFactory(role=role))
        url = reverse(f"billing:{nom}", args=[facture.pk])
        assert http.get(url).status_code == 405, nom
        assert http.post(url, {"motif": "x"}).status_code == 403, nom
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER


def test_une_facture_inexistante_donne_404(client):
    _connecte(client, Role.FINANCES)

    assert client.get(reverse("billing:facture", args=[999])).status_code == 404
    assert client.post(reverse("billing:soumettre", args=[999])).status_code == 404


def test_la_fiche_affiche_le_recouvrement_et_l_alerte_d_echeance(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))
    services.enregistrer_reglement(
        facture, finances(), montant=Decimal("180000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 7, 5)
    )

    reponse = client.get(reverse("billing:facture", args=[facture.pk]))
    texte = _texte(reponse)

    assert reponse.context["echue"] is True
    assert "Reste à recouvrer" in texte and "1 000 000 FCFA" in texte
    assert "Échéance dépassée depuis le 31/07/2026" in texte
    assert "Espèces" in texte


def test_les_textes_saisis_sont_echappes_dans_les_pages_de_facturation(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree(client=ClientFactory(raison_sociale="<script>alert(1)</script>"))
    facture = services.creer_facture(mission, finances())
    services.ajouter_ligne(
        facture, finances(), designation="<img src=x onerror=alert(2)>", quantite=Decimal(1), prix_unitaire_ht=Decimal(10)
    )

    for url in (reverse("billing:facture", args=[facture.pk]), reverse("billing:factures"),
                reverse("billing:imprimer", args=[facture.pk])):
        texte = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte, url


# --- version imprimable ---


def test_l_impression_d_un_brouillon_est_marquee_non_validee(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    texte = client.get(reverse("billing:imprimer", args=[facture.pk])).content.decode()

    assert "PROJET DE FACTURE" in texte and "NON VALIDÉE" in texte


def test_l_impression_d_une_facture_emise_montre_numero_totaux_et_emetteur(client, settings):
    settings.ENTREPRISE_NOM = "DEN Source Group"
    settings.ENTREPRISE_ADRESSE = "Abidjan, Zone 4"
    settings.ENTREPRISE_NCC = "1234567 A"
    _connecte(client, Role.DIRECTION)
    facture = emise(prix="1000000")
    services.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )

    texte = _texte(client.get(reverse("billing:imprimer", args=[facture.pk])))

    assert f"FACTURE {facture.numero}" in texte and "NON VALIDÉE" not in texte
    assert "Total HT" in texte and "1 000 000 FCFA" in texte and "1 180 000 FCFA" in texte
    assert "Reste à payer" in texte and "680 000 FCFA" in texte
    assert "DEN Source Group" in texte and "Abidjan, Zone 4" in texte and "NCC 1234567 A" in texte


# --- dépenses ---


def _donnees_depense(**surcharges):
    donnees = {
        "categorie": "PEAGES", "date_depense": timezone.localdate().isoformat(),
        "libelle": "Péage Yamoussoukro", "montant": "5000", "mode": "ESPECES",
        "reference": "TK-12", "mission": "",
    }
    donnees.update(surcharges)
    return donnees


def test_finances_enregistre_une_depense(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree()

    reponse = client.post(
        reverse("billing:depense_nouvelle"), _donnees_depense(mission=mission.pk), follow=True
    )

    depense = Depense.objects.get()
    assert depense.mission == mission and depense.montant == Decimal("5000")
    assert reponse.redirect_chain[-1][0] == reverse("billing:depenses")
    assert any("5 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))


@pytest.mark.parametrize(
    "surcharges",
    [{"montant": "0"}, {"libelle": ""}, {"date_depense": "2999-01-01"}, {"categorie": "CASINO"}, {"mode": "TROC"}],
)
def test_depense_invalide_reste_sur_le_formulaire(client, surcharges):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("billing:depense_nouvelle"), _donnees_depense(**surcharges))

    assert reponse.status_code == 200 and not Depense.objects.exists()


def test_la_liste_des_depenses_totalise_le_mois_par_categorie_et_filtre(client):
    compte = _connecte(client, Role.FINANCES)
    aujourd_hui = timezone.localdate()
    services.enregistrer_depense(
        compte, categorie="PEAGES", date_depense=aujourd_hui, libelle="Péage Bouaké",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )
    services.enregistrer_depense(
        compte, categorie="ENTRETIEN", date_depense=aujourd_hui, libelle="Graissage",
        montant=Decimal("20000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("billing:depenses"))
    par_categorie = {c["code"]: c["total"] for c in reponse.context["par_categorie"]}

    assert par_categorie["PEAGES"] == 5000 and par_categorie["ENTRETIEN"] == 20000
    assert reponse.context["total_mois"] == Decimal("25000")
    assert [d.libelle for d in client.get(reverse("billing:depenses"), {"categorie": "PEAGES"}).context["depenses"]] == ["Péage Bouaké"]
    assert len(client.get(reverse("billing:depenses"), {"q": "GRAISSAGE"}).context["depenses"]) == 1


def test_une_periode_de_depenses_a_l_envers_est_signalee_et_ignoree(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_depense(
        compte, categorie="PEAGES", date_depense=timezone.localdate(), libelle="Péage",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("billing:depenses"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"})

    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["depenses"]) == 1


def test_la_creation_de_depense_exige_le_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))

    assert http.post(reverse("billing:depense_nouvelle"), _donnees_depense()).status_code == 403
    assert not Depense.objects.exists()


def test_une_facture_a_valider_n_est_pas_presentee_comme_un_brouillon(client):
    _connecte(client, Role.DIRECTION)
    facture = a_valider()

    liste = client.get(reverse("billing:factures")).content.decode()
    fiche = client.get(reverse("billing:facture", args=[facture.pk])).content.decode()

    assert "Sans numéro" in liste
    assert "Facture à valider" in fiche and "Brouillon de facture" not in fiche
