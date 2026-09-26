"""Écrans de facturation : factures, règlements, dépenses.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.rapports import contexte_rapport
from apps.core.views import ImpressionListeMixin, PaginationTolerante
from apps.missions import permissions as missions_permissions
from apps.missions.exceptions import MissionError

from . import permissions, services
from .exceptions import BillingError
from .forms import (
    ConditionsForm,
    DecisionClientProformaForm,
    DepenseForm,
    FactureNouvelleForm,
    FiltreDepensesForm,
    FiltreFacturesForm,
    FiltreProformasForm,
    LigneForm,
    MotifForm,
    ProformaModifierForm,
    ProformaNouveauForm,
    ReglementForm,
)
from .models import (
    CategorieDepense,
    Depense,
    Facture,
    LigneFacture,
    ModePaiement,
    Proforma,
    Reglement,
    StatutFacture,
    StatutProforma,
    STATUTS_A_RECOUVRER,
)


def _fcfa(montant) -> str:
    return f"{nombre(montant)} FCFA"


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


# --- factures ---


class FactureListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "billing/facture_list.html"
    context_object_name = "factures"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreFacturesForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_factures(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            creances=services.creances(aujourd_hui),
            aujourd_hui=aujourd_hui,
            peut_saisir=self.request.user.role_effectif in permissions.SAISIE,
            missions_a_facturer=services.missions_facturables().count(),
            lignes=[
                {"facture": f, "echue": services.est_echue(f, aujourd_hui)}
                for f in contexte["page_obj"]
            ],
        )
        return contexte


class FactureImprimerView(ImpressionListeMixin, FactureListView):
    """Rapport imprimable des factures (mêmes filtres que la liste)."""

    titre_impression = "Factures"
    colonnes = (
        ("N°", lambda f: f.numero or f"Sans numéro ({f.mission.numero})"), ("Client", "client.raison_sociale"),
        ("Mission", "mission.numero"), ("Statut", "get_statut_display"),
        ("Émise le", lambda f: f.date_emission.strftime("%d/%m/%Y") if f.date_emission else "—"),
        ("Échéance", lambda f: f.date_echeance.strftime("%d/%m/%Y") if f.date_echeance else "—"),
        ("TTC", lambda f: f"{nombre(f.montant_ttc)} FCFA"), ("Reste à recouvrer", lambda f: f"{nombre(f.reste)} FCFA"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("statut") in StatutFacture.values:
            morceaux.append(f"statut : {StatutFacture(criteres['statut']).label}")
        if criteres.get("client"):
            morceaux.append(f"client : {criteres['client'].raison_sociale}")
        if criteres.get("echues"):
            morceaux.append("échues seulement")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class FactureCreateView(RoleRequiredMixin, FormView):
    roles = permissions.SAISIE
    form_class = FactureNouvelleForm
    template_name = "billing/facture_form.html"

    def get_initial(self):
        mission = self.request.GET.get("mission", "")
        return {"mission": mission} if mission.isdigit() else {}

    def form_valid(self, form):
        try:
            facture = services.creer_facture(form.cleaned_data["mission"], self.request.user)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Brouillon créé. Vérifiez les lignes et la TVA, puis soumettez-le à la direction.",
        )
        return redirect("billing:facture", pk=facture.pk)


class FactureDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "billing/facture_detail.html"
    context_object_name = "facture"

    def get_queryset(self):
        return services.factures_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        facture, role = self.object, self.request.user.role_effectif
        saisie = role in permissions.SAISIE
        brouillon = facture.statut == StatutFacture.BROUILLON
        a_valider = facture.statut == StatutFacture.A_VALIDER
        # La validation est réservée au rôle DIRECTION lui-même (un superutilisateur n'y est pas admis).
        validation = self.request.user.role in permissions.VALIDATION
        contexte.update(
            lignes=facture.lignes.all(),
            reglements=facture.reglements.select_related("saisi_par"),
            echue=services.est_echue(facture),
            peut_modifier=saisie and brouillon,
            peut_soumettre=saisie and brouillon,
            peut_valider=validation and a_valider,
            peut_regler=saisie and facture.statut in STATUTS_A_RECOUVRER,
            peut_annuler_reglement=saisie and facture.est_emise,
            form_ligne=LigneForm() if saisie and brouillon else None,
            form_conditions=ConditionsForm(
                initial={
                    "taux_tva": facture.taux_tva,
                    "motif_exoneration": facture.motif_exoneration,
                    "delai_paiement_jours": facture.delai_paiement_jours,
                }
            )
            if saisie and brouillon
            else None,
            form_refus=MotifForm() if validation and a_valider else None,
            form_reglement=ReglementForm(
                initial={"date_reglement": timezone.localdate(), "montant": facture.reste}
            )
            if saisie and facture.statut in STATUTS_A_RECOUVRER
            else None,
            form_annulation=MotifForm(),
        )
        return contexte


class FacturePrintView(RoleRequiredMixin, DetailView):
    """Version imprimable (Ctrl+P → « Enregistrer au format PDF »)."""

    roles = permissions.CONSULTATION
    template_name = "billing/facture_print.html"
    context_object_name = "facture"

    def get_queryset(self):
        return services.factures_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        titre = f"FACTURE {self.object.numero}" if self.object.est_emise else "PROJET DE FACTURE"
        contexte.update(contexte_rapport(self.request, titre=titre))
        contexte.update(
            lignes=self.object.lignes.all(),
            reglements=self.object.reglements.all(),
        )
        return contexte


class _ActionFacture(RoleRequiredMixin, View):
    """Action en POST sur une facture : formulaire → service → message → retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def get_facture(self, pk):
        return get_object_or_404(Facture, pk=pk)

    def executer(self, request, facture, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk, **kwargs):
        facture = self.get_facture(pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                _erreurs_en_messages(request, form)
                return redirect("billing:facture", pk=facture.pk)
            donnees = form.cleaned_data
        try:
            message = self.executer(request, facture, donnees, **kwargs)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            if message:
                messages.success(request, message)
        cible, arguments = self.redirection(facture)
        return redirect(cible, **arguments)

    def redirection(self, facture):
        return "billing:facture", {"pk": facture.pk}


class _Saisie(_ActionFacture):
    roles = permissions.SAISIE


class LigneAjouterView(_Saisie):
    form_class = LigneForm

    def executer(self, request, facture, donnees):
        services.ajouter_ligne(
            facture, request.user, designation=donnees["designation"],
            quantite=donnees["quantite"], prix_unitaire_ht=donnees["prix_unitaire_ht"],
        )
        return "Ligne ajoutée."


class LigneSupprimerView(_Saisie):
    def executer(self, request, facture, donnees, ligne_pk):
        ligne = get_object_or_404(LigneFacture, pk=ligne_pk, facture=facture)
        services.supprimer_ligne(ligne, request.user)
        return "Ligne supprimée."

    def post(self, request, pk, ligne_pk):
        return super().post(request, pk, ligne_pk=ligne_pk)


class ConditionsView(_Saisie):
    form_class = ConditionsForm

    def executer(self, request, facture, donnees):
        services.modifier_conditions(facture, request.user, **donnees)
        return "Conditions mises à jour."


class SoumettreView(_Saisie):
    def executer(self, request, facture, donnees):
        services.soumettre(facture, request.user)
        return "Facture envoyée à la direction pour validation."


class AbandonnerView(_Saisie):
    def executer(self, request, facture, donnees):
        services.abandonner_brouillon(facture, request.user)
        messages.success(request, "Brouillon abandonné : la mission peut être facturée à nouveau.")
        return None

    def redirection(self, facture):
        return "billing:factures", {}


class ValiderView(_ActionFacture):
    roles = permissions.VALIDATION

    def executer(self, request, facture, donnees):
        services.valider(facture, request.user)
        facture.refresh_from_db()
        return f"Facture {facture.numero} validée et émise : échéance le {facture.date_echeance:%d/%m/%Y}."


class RefuserView(_ActionFacture):
    roles = permissions.VALIDATION
    form_class = MotifForm

    def executer(self, request, facture, donnees):
        services.refuser(facture, request.user, motif=donnees["motif"])
        return "Facture renvoyée en brouillon avec votre motif."


class ReglementAjouterView(_Saisie):
    form_class = ReglementForm

    def executer(self, request, facture, donnees):
        reglement = services.enregistrer_reglement(facture, request.user, **donnees)
        facture.refresh_from_db()
        reste = services.reste_a_recouvrer(facture)
        suite = "Facture soldée." if reste <= 0 else f"Reste à recouvrer : {_fcfa(reste)}."
        return f"Règlement de {_fcfa(reglement.montant)} enregistré. {suite}"


class ReglementAnnulerView(_Saisie):
    form_class = MotifForm

    def executer(self, request, facture, donnees, reglement_pk):
        reglement = get_object_or_404(Reglement, pk=reglement_pk, facture=facture)
        services.annuler_reglement(reglement, request.user, motif=donnees["motif"])
        return "Règlement annulé : le reste à recouvrer est recalculé."

    def post(self, request, pk, reglement_pk):
        return super().post(request, pk, reglement_pk=reglement_pk)


# --- dépenses ---


class DepenseListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "billing/depense_list.html"
    context_object_name = "depenses"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreDepensesForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_depenses(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        debut = aujourd_hui.replace(day=1)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            par_categorie=services.depenses_par_categorie(debut, aujourd_hui),
            total_mois=services.total_depenses(debut, aujourd_hui),
            peut_saisir=self.request.user.role_effectif in permissions.SAISIE,
            modes=ModePaiement.choices,
        )
        return contexte


class DepenseImprimerView(ImpressionListeMixin, DepenseListView):
    """Rapport imprimable des dépenses (mêmes filtres que la liste, y compris carburant/pièces/OR)."""

    titre_impression = "Dépenses"
    colonnes = (
        ("Date", lambda d: d.date_depense.strftime("%d/%m/%Y")), ("Libellé", "libelle"),
        ("Catégorie", "get_categorie_display"), ("Mode", "get_mode_display"),
        ("Montant", lambda d: f"{nombre(d.montant)} FCFA"),
        ("Origine", lambda d: "Automatique" if d.est_automatique else "Saisie"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("categorie") in CategorieDepense.values:
            morceaux.append(f"catégorie : {CategorieDepense(criteres['categorie']).label}")
        if criteres.get("date_debut"):
            morceaux.append(f"du {criteres['date_debut'].strftime('%d/%m/%Y')}")
        if criteres.get("date_fin"):
            morceaux.append(f"au {criteres['date_fin'].strftime('%d/%m/%Y')}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class DepenseCreateView(RoleRequiredMixin, FormView):
    roles = permissions.SAISIE
    form_class = DepenseForm
    template_name = "billing/depense_form.html"

    def get_initial(self):
        return {"date_depense": timezone.localdate()}

    def form_valid(self, form):
        try:
            depense = services.enregistrer_depense(self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Dépense de {_fcfa(depense.montant)} enregistrée.")
        return redirect("billing:depenses")


class DepenseModeView(RoleRequiredMixin, View):
    """La Finance corrige le mode de paiement d'une dépense automatique (plein, achat de pièces, OR).

    Ces dépenses sont créées en espèces par défaut ; le mode décide du compte débité en trésorerie.
    """

    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request, pk):
        depense = get_object_or_404(Depense, pk=pk)
        mode = request.POST.get("mode", "")
        try:
            services.changer_mode_depense(depense, request.user, mode=mode)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"Mode de paiement de « {depense.libelle} » : {ModePaiement(mode).label}."
            )
        return redirect("billing:depenses")


# --- devis (R5) ---


class ProformaListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_list.html"
    context_object_name = "proformas"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreProformasForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_proformas(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            peut_saisir=self.request.user.role_effectif in permissions.PROFORMA_SAISIE,
        )
        return contexte


class ProformaImprimerView(ImpressionListeMixin, ProformaListView):
    """Rapport imprimable des devis (mêmes filtres que la liste)."""

    titre_impression = "Devis"
    colonnes = (
        ("N°", lambda p: p.numero or "Brouillon"), ("Client", "client.raison_sociale"),
        ("Trajet", lambda p: f"{p.lieu_chargement} → {p.lieu_livraison}"),
        ("Statut", "get_statut_display"),
        ("TTC", lambda p: f"{nombre(p.montant_ttc)} FCFA"),
        ("Valable jusqu'au", lambda p: p.date_validite.strftime("%d/%m/%Y") if p.date_validite else "—"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("statut") in StatutProforma.values:
            morceaux.append(f"statut : {StatutProforma(criteres['statut']).label}")
        if criteres.get("client"):
            morceaux.append(f"client : {criteres['client'].raison_sociale}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class ProformaCreateView(RoleRequiredMixin, FormView):
    roles = permissions.PROFORMA_SAISIE
    form_class = ProformaNouveauForm
    template_name = "billing/proforma_form.html"

    def form_valid(self, form):
        try:
            proforma = services.creer_proforma(self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Devis créé. Vérifiez le prix, puis soumettez-le à la finance.")
        return redirect("billing:proforma", pk=proforma.pk)


class ProformaModifierView(RoleRequiredMixin, FormView):
    roles = permissions.PROFORMA_SAISIE
    form_class = ProformaModifierForm
    template_name = "billing/proforma_modifier.html"

    def dispatch(self, request, *args, **kwargs):
        self.proforma = get_object_or_404(Proforma, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not self.proforma.est_modifiable:
            messages.error(request, "Ce devis n'est plus modifiable dans son état actuel.")
            return redirect("billing:proforma", pk=self.proforma.pk)
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        p = self.proforma
        return {
            "lieu_chargement": p.lieu_chargement,
            "lieu_livraison": p.lieu_livraison,
            "nature_marchandise": p.nature_marchandise,
            "poids_t": p.poids_t,
            "date_depart_souhaitee": p.date_depart_souhaitee,
            "prix_convenu": p.prix_convenu,
            "taux_tva": p.taux_tva,
            "motif_exoneration": p.motif_exoneration,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["proforma"] = self.proforma
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_proforma(self.proforma, self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Devis mis à jour.")
        return redirect("billing:proforma", pk=self.proforma.pk)


class ProformaDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_detail.html"
    context_object_name = "proforma"

    def get_queryset(self):
        return services.proformas_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        proforma = self.object
        # La validation (finance ou direction) et la contre-proposition sont réservées au rôle
        # lui-même (un superutilisateur n'y est pas admis), comme pour la validation d'une facture.
        role_strict = self.request.user.role
        saisie = self.request.user.role_effectif in permissions.PROFORMA_SAISIE
        modifiable = proforma.est_modifiable
        peut_valider_finances = (
            role_strict in permissions.PROFORMA_VALIDATION_FINANCES
            and proforma.statut == StatutProforma.SOUMISE
        )
        peut_valider_direction = (
            role_strict in permissions.PROFORMA_VALIDATION_DIRECTION
            and proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION
        )
        contexte.update(
            peut_modifier=saisie and modifiable,
            peut_abandonner=saisie and modifiable,
            peut_soumettre=saisie and modifiable,
            peut_valider_finances=peut_valider_finances,
            peut_valider_direction=peut_valider_direction,
            peut_contre_proposer=peut_valider_finances or peut_valider_direction,
            peut_envoyer_client=saisie and proforma.statut == StatutProforma.VALIDEE,
            peut_decider_client=saisie and proforma.statut == StatutProforma.ENVOYEE_CLIENT,
            peut_creer_mission=(
                proforma.statut == StatutProforma.ACCEPTEE
                and self.request.user.role_effectif in missions_permissions.CREATION
            ),
            form_contre_proposition=MotifForm() if peut_valider_finances or peut_valider_direction else None,
            form_decision_client=DecisionClientProformaForm()
            if saisie and proforma.statut == StatutProforma.ENVOYEE_CLIENT
            else None,
            historique=services.historique_proforma(proforma),
        )
        return contexte


class ProformaPrintView(RoleRequiredMixin, DetailView):
    """Version imprimable du devis à remettre au client (Ctrl+P → « Enregistrer au format PDF »)."""

    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_print.html"
    context_object_name = "proforma"

    def get_queryset(self):
        return services.proformas_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        titre = f"DEVIS {self.object.numero}" if self.object.numero else "PROJET DE DEVIS"
        contexte.update(contexte_rapport(self.request, titre=titre))
        return contexte


class _ActionProforma(RoleRequiredMixin, View):
    """Action en POST sur un devis : formulaire → service → message → retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def get_proforma(self, pk):
        return get_object_or_404(Proforma, pk=pk)

    def executer(self, request, proforma, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk, **kwargs):
        proforma = self.get_proforma(pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                _erreurs_en_messages(request, form)
                return redirect("billing:proforma", pk=proforma.pk)
            donnees = form.cleaned_data
        try:
            message = self.executer(request, proforma, donnees, **kwargs)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            if message:
                messages.success(request, message)
        cible, arguments = self.redirection(proforma)
        return redirect(cible, **arguments)

    def redirection(self, proforma):
        return "billing:proforma", {"pk": proforma.pk}


class ProformaAbandonnerView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        services.abandonner_proforma(proforma, request.user)
        messages.success(request, "Devis abandonné.")
        return None

    def redirection(self, proforma):
        return "billing:proformas", {}


class ProformaSoumettreView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        services.soumettre_proforma(proforma, request.user)
        return "Devis envoyé à la finance pour validation."


class ProformaContreProposerView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_FINANCES | permissions.PROFORMA_VALIDATION_DIRECTION
    form_class = MotifForm

    def executer(self, request, proforma, donnees):
        services.contre_proposer_proforma(proforma, request.user, motif=donnees["motif"])
        return "Devis renvoyé au chargé clientèle avec votre motif."


class ProformaValiderFinancesView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_FINANCES

    def executer(self, request, proforma, donnees):
        proforma = services.valider_proforma(proforma, request.user)
        if proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION:
            return "Devis validé : transmis à la direction (montant au-delà du seuil)."
        return f"Devis {proforma.numero} validé."


class ProformaValiderDirectionView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_DIRECTION

    def executer(self, request, proforma, donnees):
        proforma = services.valider_proforma_direction(proforma, request.user)
        return f"Devis {proforma.numero} validé."


class ProformaEnvoyerClientView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        proforma = services.envoyer_proforma_au_client(proforma, request.user)
        return f"Devis envoyé au client, valable jusqu'au {proforma.date_validite:%d/%m/%Y}."


class ProformaDecisionClientView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE
    form_class = DecisionClientProformaForm

    def executer(self, request, proforma, donnees):
        services.enregistrer_decision_client(
            proforma, request.user,
            acceptee=donnees["decision"] == "ACCEPTEE",
            motif=donnees.get("motif", ""),
        )
        return "Décision du client enregistrée."


class ProformaCreerMissionView(RoleRequiredMixin, View):
    """Devis accepté → mission (R6) : même rôle que la création manuelle d'une mission."""

    roles = missions_permissions.CREATION
    http_method_names = ["post"]

    def post(self, request, pk):
        proforma = get_object_or_404(Proforma, pk=pk)
        try:
            mission = services.convertir_en_mission(proforma)
        except (BillingError, MissionError) as erreur:
            messages.error(request, str(erreur))
            return redirect("billing:proforma", pk=proforma.pk)
        messages.success(request, f"Mission {mission.numero} créée à partir du devis {proforma.numero}.")
        return redirect("missions:detail", pk=mission.pk)

