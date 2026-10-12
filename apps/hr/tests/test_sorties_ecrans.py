"""Écrans de la sortie du personnel (audit M1-22) : fiche, liste, formulaires."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import sorties
from apps.hr.forms import PersonnelForm
from apps.hr.models import MotifSortie, SortiePersonnel

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _sortir(employe, *, jours=0):
    return sorties.enregistrer_sortie(
        employe, UserFactory(role=Role.RH), date_sortie=timezone.localdate() + timedelta(days=jours),
        motif=MotifSortie.DEMISSION,
    )[0]


def _donnees(**surcharges):
    donnees = {"date_sortie": timezone.localdate().isoformat(), "motif": "LICENCIEMENT", "commentaire": ""}
    donnees.update(surcharges)
    return donnees


# --- fiche ---


def test_la_fiche_propose_d_enregistrer_une_sortie_a_la_rh(client):
    client.force_login(UserFactory(role=Role.RH))
    employe = PersonnelFactory()

    page = client.get(reverse("hr:personnel_detail", args=[employe.pk])).content.decode()

    assert "Enregistrer une sortie" in page and reverse("hr:personnel_sortie", args=[employe.pk]) in page


def test_personne_ne_voit_le_formulaire_de_sa_propre_sortie(client):
    compte = UserFactory(role=Role.RH)
    employe = PersonnelFactory(utilisateur=compte)
    client.force_login(compte)

    page = client.get(reverse("hr:personnel_detail", args=[employe.pk])).content.decode()

    assert "Enregistrer une sortie" not in page


def test_enregistrer_une_sortie_du_jour_l_applique_et_resume_ses_effets(client):
    client.force_login(UserFactory(role=Role.RH))
    compte = UserFactory(role=Role.PARCAUTO, username="issa")
    chef = PersonnelFactory(prenom="Awa", nom="Kone")
    employe = PersonnelFactory(utilisateur=compte, superieur=chef)
    PersonnelFactory(superieur=employe)

    reponse = client.post(reverse("hr:personnel_sortie", args=[employe.pk]), _donnees(), follow=True)

    message = _messages(reponse)[0]
    assert message.startswith("Sortie de Jean Kouassi appliquée : compte issa désactivé")
    assert "1 personne(s) de son équipe rattachée(s) à Awa Kone" in message
    page = reponse.content.decode()
    assert "Sorti(e) le" in page and "Annuler la sortie" in page


def test_une_sortie_a_venir_annonce_sa_date(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    employe = PersonnelFactory()
    date_sortie = timezone.localdate() + timedelta(days=30)

    reponse = client.post(
        reverse("hr:personnel_sortie", args=[employe.pk]), _donnees(date_sortie=date_sortie.isoformat()), follow=True
    )

    assert f"enregistrée pour le {date_sortie:%d/%m/%Y}" in _messages(reponse)[0]
    assert f"Départ prévu le {date_sortie:%d/%m/%Y}" in reponse.content.decode()


def test_un_formulaire_incomplet_ou_refuse_affiche_l_erreur(client):
    client.force_login(UserFactory(role=Role.RH))
    employe = PersonnelFactory()

    sans_motif = client.post(reverse("hr:personnel_sortie", args=[employe.pk]), _donnees(motif=""), follow=True)
    autre = client.post(reverse("hr:personnel_sortie", args=[employe.pk]), _donnees(motif="AUTRE"), follow=True)

    assert _messages(sans_motif) and "Précisez" in _messages(autre)[0]
    assert not SortiePersonnel.objects.exists()


@pytest.mark.parametrize("role", [Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE])
def test_les_autres_roles_ne_peuvent_pas_poster_une_sortie(client, role):
    client.force_login(UserFactory(role=role))
    employe = PersonnelFactory()

    assert client.post(reverse("hr:personnel_sortie", args=[employe.pk]), _donnees()).status_code == 403
    sortie = _sortir(employe)
    assert client.post(reverse("hr:personnel_sortie_annuler", args=[sortie.pk]), {"motif": "x"}).status_code == 403


def test_annuler_une_sortie_depuis_la_fiche(client):
    client.force_login(UserFactory(role=Role.RH))
    employe = PersonnelFactory()
    sortie = _sortir(employe)

    reponse = client.post(
        reverse("hr:personnel_sortie_annuler", args=[sortie.pk]), {"motif": "Erreur de saisie"}, follow=True
    )

    assert "Sortie annulée" in _messages(reponse)[0] and "se réactivent à la main" in _messages(reponse)[0]
    page = reponse.content.decode()
    assert "Sorties annulées" in page and "Erreur de saisie" in page and "Enregistrer une sortie" in page


def test_une_annulation_sans_motif_ou_en_double_est_refusee(client):
    client.force_login(UserFactory(role=Role.RH))
    sortie = _sortir(PersonnelFactory())
    url = reverse("hr:personnel_sortie_annuler", args=[sortie.pk])

    assert _messages(client.post(url, {"motif": ""}, follow=True))
    client.post(url, {"motif": "Erreur"})
    assert any("déjà annulée" in m for m in _messages(client.post(url, {"motif": "Encore"}, follow=True)))


def test_la_fiche_signale_une_sortie_retenue_par_une_mission(client):
    client.force_login(UserFactory(role=Role.RH))
    employe = PersonnelFactory()
    sortie = _sortir(employe, jours=5)
    SortiePersonnel.objects.filter(pk=sortie.pk).update(date_sortie=timezone.localdate() - timedelta(days=1))

    page = client.get(reverse("hr:personnel_detail", args=[employe.pk])).content.decode()

    assert "une mission est en cours" in page


# --- liste ---


def test_la_liste_montre_les_presents_par_defaut_et_les_sortis_sur_demande(client):
    client.force_login(UserFactory(role=Role.RH))
    present = PersonnelFactory(nom="Present")
    partant = PersonnelFactory(nom="Partant")
    sorti = PersonnelFactory(nom="Sorti")
    _sortir(partant, jours=10)
    _sortir(sorti)
    url = reverse("hr:personnel_liste")

    defaut = {e.pk for e in client.get(url).context["personnel"]}
    sortis = {e.pk for e in client.get(url, {"presence": "sortis"}).context["personnel"]}
    tous = client.get(url, {"presence": "tous"})

    assert defaut == {present.pk, partant.pk} and sortis == {sorti.pk}
    assert len(tous.context["personnel"]) == 3
    page = tous.content.decode()
    assert "Sorti(e) le" in page and "Départ le" in page


def test_l_impression_rappelle_la_presence_choisie(client):
    client.force_login(UserFactory(role=Role.RH))

    page = client.get(reverse("hr:personnel_imprimer"), {"presence": "sortis"}).content.decode()

    assert "sortis" in page


def test_un_supérieur_sorti_n_est_plus_propose_sauf_s_il_est_deja_le_superieur():
    ancien_chef = PersonnelFactory()
    employe = PersonnelFactory(superieur=ancien_chef)
    autre = PersonnelFactory()
    _sortir(ancien_chef)

    pour_un_nouveau = PersonnelForm().fields["superieur"].queryset
    pour_l_employe = PersonnelForm(personnel=employe).fields["superieur"].queryset

    assert ancien_chef not in pour_un_nouveau and autre in pour_un_nouveau
    assert ancien_chef in pour_l_employe
