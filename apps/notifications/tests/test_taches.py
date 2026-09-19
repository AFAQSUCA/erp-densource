"""Tâches quotidiennes : alertes d'échéances, rappels de validation, statuts des congés."""

import re
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import TypeDocument
from apps.fleet.tests.factories import DocumentReglementaireFactory, VehiculeFactory
from apps.hr import services as hr
from apps.hr.models import StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.notifications import taches
from apps.notifications.models import NiveauNotification, Notification

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 9, 1)
MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


# --- documents des camions ---


def test_un_document_qui_expire_dans_30_jours_previent_le_parc_auto():
    parc, rh = UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.RH)
    camion = VehiculeFactory(immatriculation="1234 AB 01")
    DocumentReglementaireFactory(
        vehicule=camion, type_document=TypeDocument.ASSURANCE,
        date_expiration=AUJOURD_HUI + timedelta(days=30),
    )

    assert taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI) == 1

    (notification,) = _de(parc)
    assert notification.titre == "Assurance de 1234 AB 01 : expire dans 30 jours (01/10/2026)"
    assert notification.niveau == NiveauNotification.ATTENTION
    assert notification.url == reverse("fleet:detail", args=[camion.pk])
    assert _de(rh) == []


def test_un_document_au_dela_de_30_jours_ne_declenche_rien():
    UserFactory(role=Role.PARCAUTO)
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=31))

    assert taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI) == 0


def test_un_document_expire_est_urgent_et_l_alerte_n_est_pas_renvoyee_chaque_jour():
    parc = UserFactory(role=Role.PARCAUTO)
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI - timedelta(days=3))

    assert taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI) == 1
    assert taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI) == 0
    assert taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI + timedelta(days=1)) == 0

    (notification,) = _de(parc)
    assert "expiré depuis le 29/08/2026" in notification.titre
    assert notification.niveau == NiveauNotification.URGENT


def test_le_passage_de_a_renouveler_a_expire_envoie_une_seconde_alerte():
    parc = UserFactory(role=Role.PARCAUTO)
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=10))

    taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI)
    taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI + timedelta(days=11))

    assert [n.niveau for n in _de(parc)] == [NiveauNotification.ATTENTION, NiveauNotification.URGENT]


def test_un_document_renouvele_puis_a_nouveau_proche_reenvoie_une_alerte():
    parc = UserFactory(role=Role.PARCAUTO)
    document = DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=10))
    taches.alerter_documents_vehicules(aujourd_hui=AUJOURD_HUI)

    document.date_expiration = AUJOURD_HUI + timedelta(days=365)
    document.save()
    nouvelle_annee = AUJOURD_HUI + timedelta(days=340)
    taches.alerter_documents_vehicules(aujourd_hui=nouvelle_annee)

    assert len(_de(parc)) == 2


# --- permis et visites des chauffeurs ---


def test_permis_et_visite_a_renouveler_previennent_la_rh_et_la_direction():
    rh, direction, parc = (UserFactory(role=r) for r in (Role.RH, Role.DIRECTION, Role.PARCAUTO))
    chauffeur = ChauffeurFactory(
        date_expiration_permis=AUJOURD_HUI + timedelta(days=12),
        date_expiration_visite_medicale=AUJOURD_HUI + timedelta(days=200),
    )

    assert taches.alerter_echeances_chauffeurs(aujourd_hui=AUJOURD_HUI) == 2  # 1 alerte x 2 comptes

    for compte in (rh, direction):
        (notification,) = _de(compte)
        assert notification.titre.startswith("Permis de ")
        assert "expire dans 12 jours" in notification.titre
        assert notification.url == reverse("drivers:detail", args=[chauffeur.pk])
    assert _de(parc) == []


def test_les_deux_documents_d_un_chauffeur_donnent_deux_alertes_sans_doublon():
    rh = UserFactory(role=Role.RH)
    ChauffeurFactory(
        date_expiration_permis=AUJOURD_HUI - timedelta(days=1),
        date_expiration_visite_medicale=AUJOURD_HUI + timedelta(days=5),
    )

    taches.alerter_echeances_chauffeurs(aujourd_hui=AUJOURD_HUI)
    taches.alerter_echeances_chauffeurs(aujourd_hui=AUJOURD_HUI)

    titres = sorted(n.titre.split(" de ")[0] for n in _de(rh))
    assert titres == ["Permis", "Visite médicale"]


def test_un_chauffeur_inactif_n_est_pas_signale():
    UserFactory(role=Role.RH)
    ChauffeurFactory(
        statut=StatutChauffeur.INACTIF, date_expiration_permis=AUJOURD_HUI - timedelta(days=30)
    )

    assert taches.alerter_echeances_chauffeurs(aujourd_hui=AUJOURD_HUI) == 0


# --- validations en retard ---


def _demande():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    employe = PersonnelFactory(superieur=superieur, utilisateur=UserFactory())
    conge = hr.demander_conge(
        employe, date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), motif="x",
        maintenant=MAINTENANT,
    )
    return conge, compte_sup


def test_le_validateur_n1_est_relance_une_fois_apres_48_h():
    conge, compte_sup = _demande()
    avant_le_delai = MAINTENANT + timedelta(hours=47)
    apres_le_delai = MAINTENANT + timedelta(hours=49)

    assert taches.relancer_validations_en_retard(maintenant=avant_le_delai) == 0
    assert taches.relancer_validations_en_retard(maintenant=apres_le_delai) == 1
    assert taches.relancer_validations_en_retard(maintenant=apres_le_delai) == 0

    relance = [n for n in _de(compte_sup) if n.titre.startswith("Validation N1 en retard")]
    assert len(relance) == 1 and relance[0].niveau == NiveauNotification.URGENT
    assert relance[0].url == reverse("hr:conges_detail", args=[conge.pk])


def test_la_rh_est_relancee_apres_24_h_en_n2():
    conge, compte_sup = _demande()
    compte_rh = UserFactory(role=Role.RH)
    hr.valider_n1(conge, compte_sup, maintenant=MAINTENANT)

    assert taches.relancer_validations_en_retard(maintenant=MAINTENANT + timedelta(hours=23)) == 0
    assert taches.relancer_validations_en_retard(maintenant=MAINTENANT + timedelta(hours=25)) == 1

    assert any(n.titre.startswith("Validation N2 en retard") for n in _de(compte_rh))


def test_un_conge_deja_decide_n_est_plus_relance():
    conge, compte_sup = _demande()
    hr.refuser(conge, compte_sup, commentaire="Non")

    assert taches.relancer_validations_en_retard(maintenant=MAINTENANT + timedelta(days=10)) == 0


# --- exécution complète ---


def test_executer_taches_quotidiennes_regroupe_alertes_et_statuts_de_conges():
    UserFactory(role=Role.PARCAUTO)
    UserFactory(role=Role.RH)
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=5))
    conge, compte_sup = _demande()
    hr.valider_n1(conge, compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, UserFactory(role=Role.RH))

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=date(2026, 10, 6))

    assert resultat["documents_vehicules"] == 2  # le supérieur de la demande est aussi PARCAUTO
    assert resultat["conges_demarres"] == 1 and resultat["conges_termines"] == 0
    conge.refresh_from_db()
    assert conge.statut == StatutConge.EN_COURS


def test_la_commande_affiche_les_compteurs_et_est_rejouable():
    UserFactory(role=Role.PARCAUTO)
    DocumentReglementaireFactory(date_expiration=date.today() + timedelta(days=2))

    premiere, seconde = StringIO(), StringIO()
    call_command("taches_quotidiennes", stdout=premiere)
    call_command("taches_quotidiennes", stdout=seconde)

    assert re.search(r"documents vehicules\s+1", premiere.getvalue())
    assert re.search(r"documents vehicules\s+0", seconde.getvalue())
