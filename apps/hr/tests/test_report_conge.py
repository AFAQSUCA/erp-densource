"""Report du solde d'un congé en cours — avenant-separation-des-taches.md § R7 : l'employé écourte
son congé, la RH valide (sinon la demande n'a aucun effet)."""

from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee, CongeError, TransitionInterdite
from apps.hr.models import Conge, Departement, ReportConge, StatutConge, StatutReport

from .factories import PersonnelFactory
from .test_conges import _approuve, _demande, _rh

pytestmark = pytest.mark.django_db

DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 30)  # lundi-vendredi, 20 jours ouvrés


def _hierarchie(poste="Dispatcheur"):
    """Comme ``test_conges._hierarchie``, mais l'employé a aussi son propre compte : il faut pouvoir
    se connecter comme lui pour demander le report de son propre congé."""
    chef = PersonnelFactory(
        poste="Chef", departement=Departement.DIRECTION, utilisateur=UserFactory(role=Role.PARCAUTO)
    )
    employe = PersonnelFactory(
        poste=poste, departement=Departement.EXPLOITATION, superieur=chef,
        utilisateur=UserFactory(role=Role.PARCAUTO),
    )
    return employe, chef.utilisateur


def _en_cours(hierarchie=None, debut=DEBUT, fin=FIN):
    conge = _approuve(hierarchie, debut, fin)
    Conge.objects.filter(pk=conge.pk).update(statut=StatutConge.EN_COURS)
    conge.refresh_from_db()
    return conge


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


# --- peut_demander_report ---


def test_seul_l_employe_en_cours_peut_demander_un_report():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe, superieur = hierarchie

    assert services.peut_demander_report(conge, employe.utilisateur) is True
    assert services.peut_demander_report(conge, superieur) is False


def test_pas_de_report_avant_ou_apres_en_cours():
    hierarchie = _hierarchie()
    employe = hierarchie[0]
    approuve = _approuve(hierarchie)  # pas encore en cours

    assert services.peut_demander_report(approuve, employe.utilisateur) is False


# --- demander_report ---


def test_demander_un_report_calcule_les_jours_ouvres_restants():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)  # 05/10 (lun) au 30/10 (ven)
    employe = hierarchie[0]

    # reprise le 26/10 (lun) : jours restants du 27/10 (mar) au 30/10 (ven) = 4 jours ouvrés
    report = services.demander_report(
        conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="Fin des vacances"
    )

    assert report.statut == StatutReport.DEMANDE
    assert report.jours_restants == 4
    assert report.motif == "Fin des vacances"
    assert conge.jours == 20 and conge.date_fin == FIN  # rien ne change tant que ce n'est pas validé


def test_refuse_hors_employe_concerne():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    _, superieur = hierarchie

    with pytest.raises(ActionNonAutorisee):
        services.demander_report(conge, superieur, nouvelle_date_fin=date(2026, 10, 26), motif="x")


def test_refuse_si_le_conge_n_est_pas_en_cours():
    hierarchie = _hierarchie()
    conge = _approuve(hierarchie)
    employe = hierarchie[0]

    with pytest.raises(ActionNonAutorisee):
        services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")


@pytest.mark.parametrize(
    "nouvelle_date_fin",
    [
        date(2026, 10, 4),  # avant le début du congé
        date(2026, 10, 30),  # égale à la fin actuelle : rien à reporter
        date(2026, 11, 2),  # après la fin actuelle
    ],
)
def test_refuse_une_date_de_reprise_hors_de_la_periode(nouvelle_date_fin):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]

    with pytest.raises(CongeError, match="comprise entre"):
        services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=nouvelle_date_fin, motif="x")


def test_refuse_une_date_de_reprise_dans_le_passe():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie, debut=date(2026, 9, 21), fin=date(2026, 9, 25))  # 5 jours ouvrés
    employe = hierarchie[0]

    with pytest.raises(CongeError, match="passé"):
        services.demander_report(
            conge, employe.utilisateur, nouvelle_date_fin=date(2026, 9, 22), motif="x",
            aujourd_hui=date(2026, 9, 25),
        )


def test_refuse_sans_motif():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]

    with pytest.raises(CongeError, match="motif"):
        services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="   ")


def test_refuse_si_aucun_jour_ouvre_a_reporter():
    # congé jusqu'au dimanche 25/10 : reprendre le vendredi 23/10 ne laisse que le week-end (24-25)
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie, debut=date(2026, 10, 5), fin=date(2026, 10, 25))
    employe = hierarchie[0]

    with pytest.raises(CongeError, match="Aucun jour ouvré"):
        services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 23), motif="x")


def test_refuse_une_deuxieme_demande_pendant_qu_une_est_en_attente():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    with pytest.raises(CongeError, match="déjà en attente"):
        services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 27), motif="y")


# --- approuver_report ---


def test_approuver_raccourcit_le_conge_et_libere_le_solde():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    avant = services.droits_conges(employe, 2026)["disponible"]
    report = services.demander_report(
        conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="Fin des vacances"
    )

    services.approuver_report(report, _rh(), commentaire="Ok")

    conge.refresh_from_db()
    report.refresh_from_db()
    assert conge.date_fin == date(2026, 10, 26) and conge.jours == 16  # 20 - 4
    assert report.statut == StatutReport.APPROUVE
    assert services.droits_conges(employe, 2026)["disponible"] == avant + 4


def test_approuver_termine_le_conge_si_la_reprise_est_deja_passee():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie, debut=date(2026, 9, 1), fin=date(2026, 9, 30))  # 22 jours ouvrés
    employe = hierarchie[0]
    report = services.demander_report(
        conge, employe.utilisateur, nouvelle_date_fin=date(2026, 9, 21), motif="x", aujourd_hui=date(2026, 9, 21)
    )

    services.approuver_report(report, _rh(), aujourd_hui=date(2026, 9, 25))  # décidé quelques jours plus tard

    conge.refresh_from_db()
    assert conge.date_fin == date(2026, 9, 21) and conge.statut == StatutConge.TERMINE


def test_approuver_garde_en_cours_si_la_reprise_n_est_pas_encore_arrivee():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)  # 05/10 -> 30/10
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    services.approuver_report(report, _rh(), aujourd_hui=date(2026, 9, 25))

    conge.refresh_from_db()
    assert conge.date_fin == date(2026, 10, 26) and conge.statut == StatutConge.EN_COURS


def test_approuver_refuse_hors_rh():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe, superieur = hierarchie
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    with pytest.raises(ActionNonAutorisee):
        services.approuver_report(report, superieur)


def test_la_rh_ne_peut_pas_approuver_sa_propre_demande():
    compte_rh = _rh()
    superieur = PersonnelFactory(utilisateur=UserFactory(role=Role.PARCAUTO))
    fiche_rh = PersonnelFactory(utilisateur=compte_rh, superieur=superieur)
    conge = _en_cours((fiche_rh, superieur.utilisateur))
    report = services.demander_report(conge, compte_rh, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    with pytest.raises(ActionNonAutorisee):
        services.approuver_report(report, compte_rh)


def test_approuver_refuse_si_deja_decide():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")
    services.approuver_report(report, _rh())

    with pytest.raises(TransitionInterdite):
        services.approuver_report(report, _rh())


# --- refuser_report ---


def test_refuser_ne_change_rien_au_conge():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    services.refuser_report(report, _rh(), motif="Effectif insuffisant")

    conge.refresh_from_db()
    report.refresh_from_db()
    assert conge.jours == 20 and conge.date_fin == FIN
    assert report.statut == StatutReport.REFUSE and report.motif_decision == "Effectif insuffisant"


def test_refuser_exige_un_motif():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    with pytest.raises(CongeError, match="motif"):
        services.refuser_report(report, _rh(), motif="  ")


# --- report_en_attente / peut_decider_report ---


def test_report_en_attente_et_peut_decider():
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]

    assert services.report_en_attente(conge) is None

    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")

    assert services.report_en_attente(conge) == report
    assert services.peut_decider_report(report, _rh()) is True
    assert services.peut_decider_report(report, employe.utilisateur) is False

    services.refuser_report(report, _rh(), motif="x")
    assert services.report_en_attente(conge) is None


# --- écrans ---


def test_l_employe_demande_un_report_depuis_l_ecran(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    reponse = client.post(
        reverse("hr:conges_reporter", args=[conge.pk]),
        {"nouvelle_date_fin": "2026-10-26", "motif": "Fin des vacances"},
        follow=True,
    )

    assert ReportConge.objects.filter(conge=conge, statut=StatutReport.DEMANDE).exists()
    assert any("envoyée à la RH" in m for m in _messages(reponse))


def test_un_tiers_ne_peut_pas_demander_de_report(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("hr:conges_reporter", args=[conge.pk]), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("hr:conges_detail", args=[conge.pk])
    assert not ReportConge.objects.exists()


def test_la_rh_valide_le_report_depuis_l_ecran(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")
    _connecte(client, Role.RH)

    reponse = client.post(
        reverse("hr:conges_report_decision", args=[report.pk]), {"action": "valider"}, follow=True,
    )

    report.refresh_from_db()
    assert report.statut == StatutReport.APPROUVE
    assert any("reversé" in m for m in _messages(reponse))


def test_la_rh_refuse_le_report_avec_motif_obligatoire(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    report = services.demander_report(conge, employe.utilisateur, nouvelle_date_fin=date(2026, 10, 26), motif="x")
    _connecte(client, Role.RH)

    sans_motif = client.post(reverse("hr:conges_report_decision", args=[report.pk]), {"action": "refuser"})
    assert "Indiquez le motif" in sans_motif.content.decode() or report.statut == StatutReport.DEMANDE

    reponse = client.post(
        reverse("hr:conges_report_decision", args=[report.pk]),
        {"action": "refuser", "commentaire": "Effectif insuffisant"}, follow=True,
    )
    report.refresh_from_db()
    assert report.statut == StatutReport.REFUSE


def test_le_bouton_reporter_n_apparait_que_sur_sa_propre_ligne_en_cours(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    page = client.get(reverse("hr:conges_liste"), {"vue": "tous"}).content.decode()

    assert reverse("hr:conges_reporter", args=[conge.pk]) in page


def test_la_section_report_apparait_sur_la_fiche(client):
    hierarchie = _hierarchie()
    conge = _en_cours(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    page = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "Report du solde" in page
    assert reverse("hr:conges_reporter", args=[conge.pk]) in page


# --- PDF ---


def test_pdf_indisponible_avant_l_approbation_n2(client):
    hierarchie = _hierarchie()
    conge, _ = _demande(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    assert client.get(reverse("hr:conges_autorisation_pdf", args=[conge.pk])).status_code == 404


def test_pdf_disponible_une_fois_approuve(client):
    hierarchie = _hierarchie()
    conge = _approuve(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    reponse = client.get(reverse("hr:conges_autorisation_pdf", args=[conge.pk]))

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"


def test_pdf_interdit_a_un_tiers(client):
    hierarchie = _hierarchie()
    conge = _approuve(hierarchie)
    _connecte(client, Role.FINANCES)

    assert client.get(reverse("hr:conges_autorisation_pdf", args=[conge.pk])).status_code == 403


def test_le_lien_pdf_apparait_une_fois_approuve(client):
    hierarchie = _hierarchie()
    conge = _approuve(hierarchie)
    employe = hierarchie[0]
    client.force_login(employe.utilisateur)

    page = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert reverse("hr:conges_autorisation_pdf", args=[conge.pk]) in page
