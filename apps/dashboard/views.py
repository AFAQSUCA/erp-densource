"""Tableau de bord : page d'accueil après connexion, adaptée au rôle."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import Role
from apps.core import pdf
from apps.core.rapports import contexte_rapport, url_pdf
from apps.core.views import TelechargementPdfMixin, fcfa
from apps.drivers import services as drivers_services

from . import services


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get(self, request, *args, **kwargs):
        # Un chauffeur n'a pas de tableau de bord de bureau : son espace mobile est sa page d'accueil.
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and utilisateur.role_effectif == Role.CHAUFFEUR
            and drivers_services.chauffeur_de(utilisateur) is not None
        ):
            return redirect("chauffeur:accueil")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mois = services.periode_valide(self.request.GET.get("periode"))
        contexte.update(services.tableau_de_bord(self.request.user, mois=mois))
        return contexte


def _repartition(titre: str, graphique: dict, suffixe: str = "") -> pdf.Tableau:
    return pdf.Tableau(
        entetes=[titre, "Nombre" if not suffixe else "Montant"],
        lignes=[[l["libelle"], f"{l['valeur_texte']}{suffixe}"] for l in graphique["lignes"]],
        alignes_a_droite={1}, largeurs=[3, 1],
    )


def _par_mois(graphique: dict) -> pdf.Tableau:
    tableau = graphique["tableau"]
    return pdf.Tableau(
        entetes=["Mois", *tableau["entetes"]],
        lignes=[[l["libelle"], *l["valeurs"]] for l in tableau["lignes"]],
        alignes_a_droite=set(range(1, len(tableau["entetes"]) + 1)),
    )


class DashboardImprimerView(TelechargementPdfMixin, LoginRequiredMixin, TemplateView):
    """Rapport imprimable du tableau de bord de l'utilisateur connecté (mêmes blocs, mêmes droits), et sa version
    PDF (``?format=pdf``)."""

    template_name = "dashboard/index_print.html"

    def get_context_data(self, **kwargs):
        mois = services.periode_valide(self.request.GET.get("periode"))
        tableau = services.tableau_de_bord(self.request.user, mois=mois)
        contexte = contexte_rapport(
            self.request, titre="Tableau de bord",
            sous_titre=self.request.user.get_role_display() or "Administrateur",
        )
        contexte.update(tableau)
        contexte["url_pdf"] = url_pdf(self.request)
        return contexte

    def blocs_pdf(self, c):
        role = self.request.user.role_effectif
        blocs = []
        if c.get("espace_mobile"):
            blocs.append(pdf.Texte("Aucun rapport de bureau pour ce rôle."))
        if c.get("alertes") is not None:
            nombre = c.get("nombre_alertes")
            blocs.append(pdf.Section(f"Centre d'alertes ({nombre})" if nombre else "Centre d'alertes"))
            for groupe in c["alertes"]:
                autres = f" (+{groupe['autres']} non affichés)" if groupe["autres"] else ""
                blocs.append(pdf.Texte(f"{groupe['titre']} — {groupe['nombre']} élément(s){autres}"))
                blocs.append(pdf.Tableau(
                    entetes=["Élément", "Détail"], lignes=[[l["libelle"], l["detail"]] for l in groupe["lignes"]],
                    largeurs=[3, 2],
                ))
            if not c["alertes"]:
                blocs.append(pdf.Texte("Aucune alerte : documents, stock, carburant et congés sont à jour."))
        exploitation = c.get("exploitation")
        if exploitation:
            camions = exploitation["camions"]
            conso = exploitation.get("consommation")
            indicateurs = [
                ("Camions disponibles", f"{camions['disponibles']} / {camions['total']}"),
                ("En mission", str(camions["en_mission"])),
                ("Au garage", str(camions["au_garage"])),
                ("Consommation moyenne", f"{pdf.cellule(round(conso, 1))} L/100 km" if conso else "—"),
            ]
            voit_missions = exploitation.get("missions_en_cours") is not None and role != "PARCAUTO"
            if voit_missions:
                indicateurs += [
                    ("Missions en cours", str(exploitation["missions_en_cours"])),
                    ("Planifiées, à affecter", str(exploitation["missions_a_affecter"])),
                    ("Livrées, à clôturer", str(exploitation["missions_a_cloturer"])),
                ]
            blocs += [pdf.Section("Exploitation"), pdf.Rubriques(indicateurs),
                      _repartition("Camions par statut", exploitation["graphique_camions"])]
            if role != "PARCAUTO":
                blocs += [_repartition("Missions par statut", exploitation["graphique_missions"]),
                          _par_mois(exploitation["graphique_missions_mois"])]
        rh = c.get("ressources_humaines")
        if rh:
            blocs += [
                pdf.Section("Ressources humaines"),
                pdf.Rubriques([
                    ("Effectif", str(rh["effectif"])), ("Absents aujourd'hui", str(rh["nombre_absents"])),
                    ("Demandes à valider (N1)", str(rh["en_attente"]["n1"])),
                    ("Demandes à valider (RH, N2)", str(rh["en_attente"]["n2"])),
                ]),
                _repartition("Département", rh["graphique_departements"]),
            ]
        clientele = c.get("clientele")
        if clientele:
            blocs += [
                pdf.Section("Clientèle"),
                pdf.Rubriques([("Clients actifs (90 j)", str(clientele["clients_actifs"])),
                               ("Réclamations (30 j)", str(clientele["reclamations"]))]),
                _repartition("Top clients (12 mois)", clientele["graphique_clients"], " FCFA"),
            ]
        finances = c.get("finances")
        if finances:
            charges = finances["charges"]
            indicateurs = [
                ("CA facturé (HT)", fcfa(finances["chiffre_affaires"])),
                ("Total encaissé", fcfa(finances["encaisse"])),
                ("Charges du mois" + (" (TTC)" if charges.get("tva_deductible") else ""), fcfa(charges["total"])),
            ]
            if charges.get("tva_deductible"):
                indicateurs.append(("dont TVA récupérable", fcfa(charges["tva_deductible"])))
            indicateurs += [
                ("Marge nette (CA HT − charges HT)", fcfa(finances["marge_nette"])),
                ("Créances (dont échues)",
                 f"{pdf.cellule(finances['creances']['total'])} ({pdf.cellule(finances['creances']['echu'])}) FCFA"),
                ("Trésorerie", fcfa(finances["tresorerie"])),
            ]
            blocs += [
                pdf.Section("Finances du mois"), pdf.Rubriques(indicateurs), _par_mois(finances["graphique_mensuel"]),
                _repartition("Charges du mois", finances["graphique_charges"], " FCFA"),
                _repartition("Créances par ancienneté", finances["graphique_creances"], " FCFA"),
            ]
        return blocs
