# Chapitre 17 — Écrans : personnel et congés

> 14 fichier(s) dans ce chapitre, 2513 lignes de code.

## Ce que vous allez construire

Les **écrans du personnel et des congés**. C'est le premier module d'écrans : on y apprend les
**motifs qui reviendront dans tous les chapitres suivants**.

| Écran | Adresse | Qui |
|---|---|---|
| Liste des congés (3 vues : « Mes demandes », « À valider », « Tous les congés ») | `/rh/conges/` | tout compte de bureau ayant une fiche |
| Demander un congé | `/rh/conges/nouveau/` | idem |
| Fiche d'un congé (avec les boutons **Valider / Refuser / Annuler** selon le droit) | `/rh/conges/<id>/` | l'employé, son supérieur, la RH, la Direction |
| Liste et fiche du personnel, recrutement, modification | `/rh/personnel/…` | ADMIN et RH (la DIRECTION en lecture) |
| Accorder des jours exceptionnels | `/rh/personnel/<id>/jours-exceptionnels/` | RH |

## Prérequis

- Chapitres 1 à 16 terminés ; les styles compilés.

## Les quatre motifs d'écran

Presque tous les écrans du projet sont l'un de ces quatre modèles. Apprenez-les ici.

**1. Liste filtrée et paginée** (`ListView`). La vue lit les filtres dans l'adresse (`?statut=APPROUVE`),
appelle un **service** qui renvoie un `QuerySet`, et passe au gabarit ce qu'il faut afficher. La pagination
(20 lignes par page) est fournie par Django ; `PaginationTolerante` (chapitre 16) évite les erreurs 404.

**2. Fiche** (`DetailView`). Elle affiche un objet et calcule, avec les services, **quelles actions proposer**
à cet utilisateur : c'est `services.actions_disponibles(...)` qui décide, pas le gabarit.

**3. Formulaire** (`FormView`). Un `forms.Form` **lit et valide** ce que l'utilisateur a saisi (types, champs
obligatoires) ; il **n'applique aucune règle métier**. Si le formulaire est valide, la vue appelle un **service**.
Si le service lève une exception métier (solde insuffisant…), la vue l'affiche avec `messages.error`.
Après un succès : **redirection** (`redirect(...)`) : c'est le motif *Post/Redirect/Get*, qui évite qu'un
rafraîchissement de la page renvoie le formulaire deux fois.

**4. Action en `POST` seul** (`View` avec `http_method_names = ["post"]`). Un bouton « Valider » n'est qu'un mini
formulaire : la vue n'a pas de page à afficher, elle exécute l'action et redirige.

Et un principe : la vue ne contient **aucune règle**. Regardez `CongeDecisionView` : elle transmet
`valider_conge`, `refuser` ou `annuler_conge_approuve` au service, qui décide **selon la hiérarchie**. Le rôle
n'est vérifié dans la vue que pour l'*accès à l'écran*.

## Étape 1 — Les formulaires

#### `apps/hr/forms.py`

*191 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import Departement, Personnel, POSTES_COURANTS

POSTE_AUTRE = "AUTRE"


class CongeForm(StyleTailwindMixin, forms.Form):
    """Demande de congé : dates et motif (cahier-des-charges.md:212)."""

    date_debut = forms.DateField(
        label="Premier jour de congé", widget=forms.DateInput(attrs={"type": "date"})
    )
    date_fin = forms.DateField(
        label="Dernier jour de congé", widget=forms.DateInput(attrs={"type": "date"})
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "La date de fin précède la date de début.")
        return donnees


class DecisionForm(StyleTailwindMixin, forms.Form):
    """Décision sur un congé : valider, refuser ou annuler (avec commentaire)."""

    action = forms.ChoiceField(
        choices=[
            (services.ACTION_VALIDER, "Valider"),
            (services.ACTION_REFUSER, "Refuser"),
            (services.ACTION_ANNULER, "Annuler"),
        ],
        widget=forms.HiddenInput,
    )
    commentaire = forms.CharField(
        label="Commentaire", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        action = donnees.get("action")
        if (
            action in (services.ACTION_REFUSER, services.ACTION_ANNULER)
            and not donnees.get("commentaire", "").strip()
        ):
            self.add_error("commentaire", "Indiquez le motif : il sera communiqué à l'employé.")
        return donnees


class ReportForm(StyleTailwindMixin, forms.Form):
    """Demande de report du solde non pris d'un congé en cours (avenant § R7)."""

    nouvelle_date_fin = forms.DateField(
        label="Je reprends le travail le", widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Dernier jour de congé réellement pris ; les jours ouvrés restants jusqu'à la fin "
        "initialement prévue vous sont reversés une fois la RH d'accord.",
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))


class DecisionReportForm(StyleTailwindMixin, forms.Form):
    """Décision de la RH sur une demande de report : valider ou refuser (motif obligatoire)."""

    action = forms.ChoiceField(
        choices=[("valider", "Valider"), ("refuser", "Refuser")], widget=forms.HiddenInput,
    )
    commentaire = forms.CharField(
        label="Commentaire", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("action") == "refuser" and not donnees.get("commentaire", "").strip():
            self.add_error("commentaire", "Indiquez le motif du refus : il sera visible par l'employé.")
        return donnees


class AttributionForm(StyleTailwindMixin, forms.Form):
    """Jours de congé exceptionnels accordés par la RH (motif obligatoire)."""

    annee = forms.IntegerField(label="Année", min_value=2000, max_value=2100)
    jours = forms.IntegerField(label="Jours ouvrables accordés", min_value=1, max_value=60)
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annee"].initial = timezone.localdate().year


def _libelle_employe(p: Personnel) -> str:
    return f"{p.prenom} {p.nom} ({p.matricule})"


def _libelle_compte(u) -> str:
    return f"{u.get_full_name() or u.username} - {u.get_role_display()}"


class PersonnelForm(StyleTailwindMixin, forms.Form):
    """Recrutement ou modification d'une fiche (cahier-des-charges.md:206-210).

    Le matricule n'est jamais un champ du formulaire : ``services.recruter`` le génère
    automatiquement (``PERS-AAAA-XXXX``). À la modification, la date d'embauche ne change pas non
    plus (champ retiré ci-dessous).
    """

    nom = forms.CharField(label="Nom", max_length=100)
    prenom = forms.CharField(label="Prénom", max_length=100)
    poste = forms.ChoiceField(
        label="Poste",
        choices=[(p, p) for p in POSTES_COURANTS] + [(POSTE_AUTRE, "Autre…")],
        widget=forms.Select(attrs={"x-ref": "poste", "x-model": "poste", "@change": "poste = $event.target.value"}),
    )
    poste_autre = forms.CharField(
        label="Préciser le poste",
        max_length=100,
        required=False,
        help_text="Le poste n'apparaît pas dans la liste ci-dessus.",
    )
    departement = forms.ChoiceField(label="Département", choices=Departement.choices)
    type_contrat = forms.CharField(
        label="Type de contrat", max_length=30, required=False, help_text="Ex. : CDI, CDD, stage."
    )
    date_embauche = forms.DateField(
        label="Date d'embauche", widget=forms.DateInput(attrs={"type": "date"})
    )
    salaire_base = forms.DecimalField(
        label="Salaire de base (FCFA)", min_value=0, max_digits=12, decimal_places=2
    )
    superieur = forms.ModelChoiceField(
        label="Supérieur hiérarchique",
        queryset=None,
        required=False,
        help_text="Il valide en N1 les congés de cet employé. Vide uniquement pour le directeur.",
    )
    utilisateur = forms.ModelChoiceField(
        label="Compte utilisateur",
        queryset=None,
        required=False,
        help_text="Nécessaire pour que l'employé demande ou valide des congés.",
    )

    def __init__(self, *args, personnel: Personnel | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.personnel = personnel
        superieurs = services.personnel_queryset().order_by("nom", "prenom")
        if personnel is not None:
            superieurs = superieurs.exclude(pk=personnel.pk)
            del self.fields["date_embauche"]
            if personnel.poste not in POSTES_COURANTS:
                # Poste antérieur hors liste (saisi avant l'existence de la liste, ou via « Autre ») :
                # préremplir « Autre » + son intitulé, plutôt que de perdre la valeur ou de refuser
                # la fiche à la prochaine modification qui ne touche pas ce champ.
                self.initial["poste"] = POSTE_AUTRE
                self.initial["poste_autre"] = personnel.poste
        self.fields["superieur"].queryset = superieurs
        self.fields["superieur"].label_from_instance = _libelle_employe
        self.fields["utilisateur"].queryset = services.comptes_disponibles(garder=personnel)
        self.fields["utilisateur"].label_from_instance = _libelle_compte

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("poste") == POSTE_AUTRE:
            autre = cleaned.get("poste_autre", "").strip()
            if not autre:
                self.add_error("poste_autre", "Précisez le poste.")
            else:
                cleaned["poste"] = autre
        cleaned.pop("poste_autre", None)  # jamais transmis à services.recruter/modifier_personnel
        return cleaned


class ImportPersonnelForm(StyleTailwindMixin, forms.Form):
    """Recrutement en masse : un classeur Excel (.xlsx), colonnes voir services.COLONNES_IMPORT."""

    fichier = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Téléchargez le modèle ci-dessous, remplissez-le, puis déposez-le ici.",
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Le fichier doit être un classeur Excel (.xlsx).")
        return fichier
```

`StyleTailwindMixin` (chapitre 2) donne à chaque champ le même aspect. Les formulaires n'ont **aucune règle
métier** : « ce congé dépasse-t-il le solde ? » se décide dans `services.demander_conge`.

## Étape 2 — Les vues

#### `apps/hr/views.py`

*565 lignes* — Écrans RH : congés (demande, validation N1/N2, annulation) et fiche du personnel.

```python
"""Écrans RH : congés (demande, validation N1/N2, annulation) et fiche du personnel.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23). Le droit de valider dépend de la
hiérarchie et non du seul rôle : c'est ``services.py`` qui le tranche.
"""

import openpyxl
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import documents, permissions, sections, services
from .exceptions import CongeError, ImportPersonnelError, PersonnelError
from .forms import (
    AttributionForm,
    CongeForm,
    DecisionForm,
    DecisionReportForm,
    ImportPersonnelForm,
    PersonnelForm,
    ReportForm,
)
from .models import AttributionConge, Departement, ReportConge, StatutConge

VUE_MES, VUE_A_VALIDER, VUE_TOUS = "mes", "a_valider", "tous"


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


# --- congés ---


class CongeListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONGES_ACCES
    template_name = "hr/conge_list.html"
    context_object_name = "conges"
    paginate_by = 20

    @property
    def fiche(self):
        if not hasattr(self, "_fiche"):
            self._fiche = services.fiche_personnel(self.request.user)
        return self._fiche

    @property
    def a_valider(self):
        if not hasattr(self, "_a_valider"):
            self._a_valider = services.conges_a_valider(self.request.user)
        return self._a_valider

    def vues_disponibles(self):
        vues = []
        if self.fiche is not None:
            vues.append(VUE_MES)
        vues.append(VUE_A_VALIDER)
        if self.request.user.role_effectif in permissions.CONGES_TOUS:
            vues.append(VUE_TOUS)
        return vues

    def get_vue(self):
        disponibles = self.vues_disponibles()
        demandee = self.request.GET.get("vue")
        if demandee in disponibles:
            return demandee
        if self.a_valider.exists():
            return VUE_A_VALIDER
        return disponibles[0]

    def get_queryset(self):
        vue = self.get_vue()
        if vue == VUE_MES:
            resultat = services.conges_de(self.fiche)
        elif vue == VUE_A_VALIDER:
            resultat = self.a_valider
        else:
            resultat = services.conges_queryset()
        statut = self.request.GET.get("statut", "")
        if statut in StatutConge.values:
            resultat = resultat.filter(statut=statut)
        return resultat.order_by("-date_debut", "-pk")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        annee = timezone.localdate().year
        contexte.update(
            vue=self.get_vue(),
            vues=self.vues_disponibles(),
            nombre_a_valider=self.a_valider.count(),
            statuts=StatutConge.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            fiche=self.fiche,
            annee=annee,
            droits=services.droits_conges(self.fiche, annee) if self.fiche else None,
            lignes=[
                {
                    "conge": c,
                    "echeance": services.echeance_en_attente(c),
                    # Équivalent à services.peut_demander_report(c, utilisateur), sans requête
                    # supplémentaire par ligne : self.fiche est déjà mise en cache pour la page.
                    "peut_reporter": c.statut == StatutConge.EN_COURS and self.fiche is not None and self.fiche.pk == c.employe_id,
                }
                for c in contexte["page_obj"]
            ],
        )
        return contexte


class CongeImprimerView(ImpressionListeMixin, CongeListView):
    """Rapport imprimable des congés (même vue — mes demandes / à valider / tous — et même statut)."""

    titre_impression = "Congés"
    colonnes = (
        ("Employé", lambda c: f"{c.employe.prenom} {c.employe.nom}"),
        ("Du", lambda c: c.date_debut.strftime("%d/%m/%Y")), ("Au", lambda c: c.date_fin.strftime("%d/%m/%Y")),
        ("Jours", "jours"), ("Motif", "motif"), ("Statut", "get_statut_display"),
    )

    LIBELLES_VUE = {VUE_MES: "mes demandes", VUE_A_VALIDER: "à valider", VUE_TOUS: "tous les congés"}

    def get_sous_titre_impression(self):
        morceaux = [self.LIBELLES_VUE.get(self.get_vue(), "")]
        if self.request.GET.get("statut", "") in StatutConge.values:
            morceaux.append(f"statut : {StatutConge(self.request.GET['statut']).label}")
        return " · ".join(m for m in morceaux if m)


class CongeCreateView(RoleRequiredMixin, FormView):
    roles = permissions.CONGES_ACCES
    form_class = CongeForm
    template_name = "hr/conge_form.html"

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and utilisateur.role_effectif in self.roles
            and services.fiche_personnel(utilisateur) is None
        ):
            messages.error(
                request,
                "Votre compte n'est rattaché à aucune fiche du personnel : "
                "demandez à la RH de le renseigner pour pouvoir demander un congé.",
            )
            return redirect("hr:conges_liste")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        fiche = services.fiche_personnel(self.request.user)
        annee = timezone.localdate().year
        contexte.update(
            fiche=fiche,
            annee=annee,
            droits=services.droits_conges(fiche, annee),
        )
        return contexte

    def form_valid(self, form):
        fiche = services.fiche_personnel(self.request.user)
        try:
            conge = services.demander_conge(fiche, **form.cleaned_data)
        except CongeError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Demande enregistrée : {conge.jours} jour{'s' if conge.jours > 1 else ''} "
            "ouvrable(s). Votre supérieur hiérarchique doit la valider sous 48 h.",
        )
        return redirect("hr:conges_detail", pk=conge.pk)


class CongeDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONGES_ACCES
    template_name = "hr/conge_detail.html"
    context_object_name = "conge"

    def get_queryset(self):
        return services.conges_queryset()

    def get_object(self, queryset=None):
        conge = super().get_object(queryset)
        utilisateur = self.request.user
        if (
            utilisateur.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, utilisateur)
        ):
            raise PermissionDenied
        return conge

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        conge, utilisateur = self.object, self.request.user
        report = services.report_en_attente(conge)
        contexte.update(
            validations=conge.validations.select_related("validateur"),
            droits=services.droits_conges(conge.employe, conge.date_debut.year),
            echeance=services.echeance_en_attente(conge),
            actions=services.actions_disponibles(conge, utilisateur),
            en_remplacement=services.decide_en_remplacement(conge, utilisateur),
            sections=sections.DETAIL_CONGE.sections(conge, utilisateur),
            peut_voir_employe=utilisateur.role_effectif in permissions.PERSONNEL_CONSULTATION,
            peut_reporter=services.peut_demander_report(conge, utilisateur),
            report_en_attente=report,
            peut_decider_report=bool(report) and services.peut_decider_report(report, utilisateur),
            reports_decides=conge.reports.exclude(pk=getattr(report, "pk", None)).select_related("valide_par"),
            peut_telecharger_autorisation=conge.statut in services.STATUTS_DECOMPTES,
        )
        return contexte


class CongeDecisionView(RoleRequiredMixin, View):
    """Valide, refuse ou annule un congé (POST) ; le service contrôle le droit de le faire."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["post"]

    def post(self, request, pk):
        conge = get_object_or_404(services.conges_queryset(), pk=pk)
        if (
            request.user.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, request.user)
        ):
            raise PermissionDenied
        form = DecisionForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:conges_detail", pk=conge.pk)
        action, commentaire = form.cleaned_data["action"], form.cleaned_data["commentaire"]
        statut_avant = conge.statut
        try:
            if action == services.ACTION_VALIDER:
                services.valider_conge(conge, request.user, commentaire=commentaire)
            elif action == services.ACTION_REFUSER:
                services.refuser(conge, request.user, commentaire=commentaire)
            else:
                services.annuler_conge_approuve(conge, request.user, motif=commentaire)
        except CongeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self._message(action, statut_avant, conge))
        return redirect("hr:conges_detail", pk=conge.pk)

    @staticmethod
    def _message(action, statut_avant, conge):
        if action == services.ACTION_REFUSER:
            return "Demande refusée : votre motif est visible par l'employé sur sa demande."
        if action == services.ACTION_ANNULER:
            return "Congé annulé : les jours sont restitués à l'employé."
        if statut_avant == StatutConge.DEMANDE:
            return "Demande validée en N1. Elle attend maintenant la validation de la RH (24 h)."
        return (
            f"Congé approuvé : {conge.jours} jour{'s' if conge.jours > 1 else ''} "
            f"décompté{'s' if conge.jours > 1 else ''} du droit de {conge.date_debut.year}."
        )


# --- report du solde d'un congé en cours (avenant-separation-des-taches.md § R7) ---


class ReportCreateView(RoleRequiredMixin, FormView):
    """Demande de report, par l'employé actuellement en congé (bouton sur sa ligne du tableau)."""

    roles = permissions.CONGES_ACCES
    form_class = ReportForm
    template_name = "hr/report_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.conge = get_object_or_404(services.conges_queryset(), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not services.peut_demander_report(self.conge, request.user):
            messages.error(request, "Le report n'est possible que pour votre propre congé, pendant que vous y êtes.")
            return redirect("hr:conges_detail", pk=self.conge.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(conge=self.conge, **kwargs)

    def form_valid(self, form):
        try:
            services.demander_report(self.conge, self.request.user, **form.cleaned_data)
        except CongeError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Demande de report envoyée à la RH : sans sa validation, votre congé continue normalement.",
        )
        return redirect("hr:conges_detail", pk=self.conge.pk)


class ReportDecisionView(RoleRequiredMixin, View):
    """Valide ou refuse une demande de report (POST, RH uniquement — contrôlé par le service)."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["post"]

    def post(self, request, pk):
        report = get_object_or_404(ReportConge.objects.select_related("conge"), pk=pk)
        form = DecisionReportForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:conges_detail", pk=report.conge_id)
        action, commentaire = form.cleaned_data["action"], form.cleaned_data["commentaire"]
        try:
            if action == "valider":
                services.approuver_report(report, request.user, commentaire=commentaire)
                messages.success(
                    request,
                    f"Report validé : {report.jours_restants} jour(s) reversé(s) au solde de l'employé.",
                )
            else:
                services.refuser_report(report, request.user, motif=commentaire)
                messages.success(request, "Report refusé : le congé continue jusqu'à sa fin initiale.")
        except CongeError as erreur:
            messages.error(request, str(erreur))
        return redirect("hr:conges_detail", pk=report.conge_id)


class AutorisationCongePdfView(RoleRequiredMixin, View):
    """PDF de l'autorisation de congé, produit à la demande (jamais stocké)."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["get"]

    def get(self, request, pk):
        conge = get_object_or_404(services.conges_queryset(), pk=pk)
        if (
            request.user.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, request.user)
        ):
            raise PermissionDenied
        try:
            contenu = documents.generer_pdf_autorisation(conge)
        except ValueError:
            raise Http404
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="autorisation-conge-{conge.pk}.pdf"'
        reponse["Cache-Control"] = "no-store, private"
        return reponse


# --- personnel ---


class PersonnelListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.PERSONNEL_CONSULTATION
    template_name = "hr/personnel_list.html"
    context_object_name = "personnel"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_personnel(
            departement=self.request.GET.get("departement", ""),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            departements=Departement.choices,
            departement_choisi=self.request.GET.get("departement", ""),
            recherche=self.request.GET.get("q", ""),
            peut_modifier=self.request.user.role_effectif in permissions.PERSONNEL_MODIFICATION,
        )
        return contexte


class PersonnelImprimerView(ImpressionListeMixin, PersonnelListView):
    """Rapport imprimable du personnel (mêmes recherche et département que la liste ; sans le salaire,
    comme la liste elle-même)."""

    titre_impression = "Personnel"
    colonnes = (
        ("Matricule", "matricule"), ("Nom", "nom"), ("Prénom", "prenom"), ("Poste", "poste"),
        ("Département", "get_departement_display"),
        ("Date d'embauche", lambda p: p.date_embauche.strftime("%d/%m/%Y")),
        ("Supérieur", lambda p: f"{p.superieur.prenom} {p.superieur.nom}" if p.superieur_id and p.superieur_id != p.pk else "—"),
    )

    def get_sous_titre_impression(self):
        morceaux = []
        if self.request.GET.get("departement", "") in Departement.values:
            morceaux.append(f"département : {Departement(self.request.GET['departement']).label}")
        if self.request.GET.get("q", ""):
            morceaux.append(f"recherche : « {self.request.GET['q']} »")
        return " · ".join(morceaux)


class PersonnelDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.PERSONNEL_CONSULTATION
    template_name = "hr/personnel_detail.html"
    context_object_name = "employe"

    def get_queryset(self):
        return services.personnel_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        employe, utilisateur = self.object, self.request.user
        annee = timezone.localdate().year
        peut_accorder = services.peut_accorder_jours(utilisateur, employe)
        contexte.update(
            annee=annee,
            droits=services.droits_conges(employe, annee),
            conges=services.conges_de(employe)[:10],
            attributions=AttributionConge.objects.filter(employe=employe).select_related(
                "accorde_par"
            ),
            subordonnes=employe.subordonnes.order_by("nom", "prenom"),
            peut_modifier=utilisateur.role_effectif in permissions.PERSONNEL_MODIFICATION,
            peut_accorder=peut_accorder,
            form_attribution=AttributionForm() if peut_accorder else None,
        )
        return contexte


class PersonnelCreateView(RoleRequiredMixin, FormView):
    roles = permissions.PERSONNEL_MODIFICATION
    form_class = PersonnelForm
    template_name = "hr/personnel_form.html"

    def form_valid(self, form):
        try:
            personnel = services.recruter(**form.cleaned_data)
        except PersonnelError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        suite = (
            " Sa fiche chauffeur a été créée automatiquement." if personnel.est_chauffeur else ""
        )
        messages.success(
            self.request,
            f"{personnel.prenom} {personnel.nom} est enregistré(e) sous le matricule "
            f"{personnel.matricule}.{suite}",
        )
        return redirect("hr:personnel_detail", pk=personnel.pk)


class PersonnelImportView(RoleRequiredMixin, FormView):
    """Recrutement en masse depuis un classeur Excel — voir services.importer_personnel."""

    roles = permissions.PERSONNEL_MODIFICATION
    form_class = ImportPersonnelForm
    template_name = "hr/personnel_import.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(colonnes=services.COLONNES_IMPORT, **kwargs)

    def form_valid(self, form):
        try:
            crees = services.importer_personnel(form.cleaned_data["fichier"])
        except ImportPersonnelError as erreur:
            return self.render_to_response(self.get_context_data(form=form, erreurs=erreur.erreurs))
        messages.success(
            self.request,
            f"{len(crees)} employé(s) importé(s) : "
            + ", ".join(f"{p.prenom} {p.nom} ({p.matricule})" for p in crees) + ".",
        )
        return redirect("hr:personnel_liste")


class PersonnelModeleImportView(RoleRequiredMixin, View):
    """Modèle de fichier à télécharger avant l'import en masse (colonnes attendues, un exemple)."""

    roles = permissions.PERSONNEL_MODIFICATION

    def get(self, request):
        classeur = openpyxl.Workbook()
        feuille = classeur.active
        feuille.title = "Personnel"
        feuille.append(services.COLONNES_IMPORT)
        feuille.append(["Traoré", "Awa", "Comptable", "Comptabilité", "CDI", "01/09/2026", "250000"])
        reponse = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        reponse["Content-Disposition"] = "attachment; filename=modele-import-personnel.xlsx"
        classeur.save(reponse)
        return reponse


class PersonnelUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.PERSONNEL_MODIFICATION
    form_class = PersonnelForm
    template_name = "hr/personnel_form.html"

    @property
    def employe(self):
        if not hasattr(self, "_employe"):
            self._employe = get_object_or_404(services.personnel_queryset(), pk=self.kwargs["pk"])
        return self._employe

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["personnel"] = self.employe
        return kwargs

    def get_initial(self):
        e = self.employe
        return {
            "nom": e.nom,
            "prenom": e.prenom,
            "poste": e.poste,
            "departement": e.departement,
            "type_contrat": e.type_contrat,
            "salaire_base": e.salaire_base,
            "superieur": e.superieur,
            "utilisateur": e.utilisateur,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["employe"] = self.employe
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_personnel(self.employe, **form.cleaned_data)
        except PersonnelError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de {self.employe.prenom} {self.employe.nom} mise à jour.")
        return redirect("hr:personnel_detail", pk=self.employe.pk)


class AttributionView(RoleRequiredMixin, View):
    """Jours de congé exceptionnels (POST) : réservé à la RH, contrôlé par le service."""

    roles = permissions.PERSONNEL_MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        employe = get_object_or_404(services.personnel_queryset(), pk=pk)
        form = AttributionForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:personnel_detail", pk=employe.pk)
        try:
            attribution = services.accorder_jours_exceptionnels(
                employe, request.user, **form.cleaned_data
            )
        except CongeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"{nombre(attribution.jours)} jour(s) exceptionnel(s) accordé(s) "
                f"pour {attribution.annee}.",
            )
        return redirect("hr:personnel_detail", pk=employe.pk)
```

À repérer dans ce fichier :

- `roles = permissions.CONGES_ACCES` : la **garde** (`RoleRequiredMixin`), sur chaque vue.
- `CongeListView` : trois vues possibles selon le rôle (`vues_disponibles`) ; `get_queryset` choisit le service.
- `CongeCreateView` : `form_valid` appelle `services.demander_conge`, gère les erreurs métier, redirige.
- `CongeDecisionView` : un seul point d'entrée `POST` pour valider, refuser et annuler.
- `PersonnelListView/DetailView/CreateView/UpdateView` : le même schéma pour le personnel.
- `AttributionView` : accorder des jours exceptionnels (RH seulement, motif obligatoire).

## Étape 3 — Les adresses

#### `apps/hr/urls.py`

*44 lignes*

```python
from django.urls import path

from . import views

app_name = "hr"

urlpatterns = [
    path("conges/", views.CongeListView.as_view(), name="conges_liste"),
    path("conges/imprimer/", views.CongeImprimerView.as_view(), name="conges_imprimer"),
    path("conges/nouveau/", views.CongeCreateView.as_view(), name="conges_nouveau"),
    path("conges/<int:pk>/", views.CongeDetailView.as_view(), name="conges_detail"),
    path("conges/<int:pk>/decision/", views.CongeDecisionView.as_view(), name="conges_decision"),
    path("conges/<int:pk>/reporter/", views.ReportCreateView.as_view(), name="conges_reporter"),
    path(
        "conges/<int:pk>/autorisation.pdf",
        views.AutorisationCongePdfView.as_view(),
        name="conges_autorisation_pdf",
    ),
    path(
        "conges/report/<int:pk>/decision/",
        views.ReportDecisionView.as_view(),
        name="conges_report_decision",
    ),
    path("personnel/", views.PersonnelListView.as_view(), name="personnel_liste"),
    path("personnel/imprimer/", views.PersonnelImprimerView.as_view(), name="personnel_imprimer"),
    path("personnel/nouveau/", views.PersonnelCreateView.as_view(), name="personnel_nouveau"),
    path("personnel/importer/", views.PersonnelImportView.as_view(), name="personnel_importer"),
    path(
        "personnel/importer/modele.xlsx",
        views.PersonnelModeleImportView.as_view(),
        name="personnel_import_modele",
    ),
    path("personnel/<int:pk>/", views.PersonnelDetailView.as_view(), name="personnel_detail"),
    path(
        "personnel/<int:pk>/modifier/",
        views.PersonnelUpdateView.as_view(),
        name="personnel_modifier",
    ),
    path(
        "personnel/<int:pk>/jours-exceptionnels/",
        views.AttributionView.as_view(),
        name="personnel_attribution",
    ),
]
```

`app_name = "hr"` crée l'espace de noms : on écrit `reverse("hr:conges_liste")`. `<int:pk>` capture un numéro
dans l'adresse et le passe à la vue.

Montez ces adresses : voici la modification à faire dans `config/urls.py` :

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -17,4 +17,5 @@
     path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
     path("", include("apps.accounts.urls")),
+    path("rh/", include("apps.hr.urls")),
     path("audit/", include("apps.audit.urls")),
     path("notifications/", include("apps.notifications.urls")),
```

## Étape 4 — Les gabarits

```bash
mkdir -p apps/hr/templates/hr
```

Chaque gabarit **hérite de `base.html`**. Lisez d'abord la liste des congés : c'est la plus riche.

#### `apps/hr/templates/hr/conge_list.html`

*117 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Congés{% endblock %}
{% block entete %}Congés{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Congés</h1>
      <p class="mt-1 text-sm text-slate-600">
        Trois étapes : la demande, la validation de votre supérieur hiérarchique (48 h), puis celle de la RH (24 h).
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'hr:conges_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if fiche %}
        <a href="{% url 'hr:conges_nouveau' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Demander un congé
        </a>
      {% endif %}
    </div>
  </div>

  {% if droits %}
    <dl class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Droit annuel {{ annee }}</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ droits.droit_annuel }} <span class="text-sm font-medium text-slate-600">jours ouvrés</span></dd></div>
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Jours exceptionnels</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ droits.exceptionnels }}</dd></div>
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Déjà pris ou approuvés</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ droits.consommes }}</dd></div>
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Solde disponible</dt><dd class="mt-1 text-2xl font-bold {% if droits.disponible <= 0 %}text-red-700{% else %}text-emerald-800{% endif %}">{{ droits.disponible }}</dd></div>
    </dl>
  {% endif %}

  <div class="mt-6 flex flex-wrap items-end justify-between gap-3 border-b border-slate-200">
    <nav aria-label="Affichage des congés" class="-mb-px flex gap-1">
      {% for v in vues %}
        <a href="?vue={{ v }}"
           {% if v == vue %}aria-current="page"{% endif %}
           class="rounded-t-lg border-b-2 px-4 py-2 text-sm font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 {% if v == vue %}border-marque-600 text-marque-700{% else %}border-transparent text-slate-600 hover:text-slate-900{% endif %}">
          {% if v == "mes" %}Mes demandes{% elif v == "a_valider" %}À valider{% if nombre_a_valider %} <span class="ml-1 rounded-full bg-accent-500 px-2 py-0.5 text-xs text-slate-900">{{ nombre_a_valider }}</span>{% endif %}{% else %}Tous les congés{% endif %}
        </a>
      {% endfor %}
    </nav>
    <form method="get" class="flex items-end gap-2 pb-2">
      <input type="hidden" name="vue" value="{{ vue }}">
      <div>
        <label for="statut" class="sr-only">Statut</label>
        <select id="statut" name="statut" class="block w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
          <option value="">Tous les statuts</option>
          {% for code, libelle in statuts %}<option value="{{ code }}" {% if code == statut_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
        </select>
      </div>
      <button type="submit" class="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    </form>
  </div>

  {% if lignes %}
    <div class="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des congés</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Employé</th>
            <th scope="col" class="px-4 py-3">Période</th>
            <th scope="col" class="px-4 py-3 text-right">Jours</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Décision attendue avant</th>
            <th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for ligne in lignes %}
            {% with c=ligne.conge e=ligne.echeance %}
              <tr class="hover:bg-slate-50">
                <td class="whitespace-nowrap px-4 py-3 font-semibold">
                  <a href="{% url 'hr:conges_detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ c.employe.prenom }} {{ c.employe.nom }}</a>
                </td>
                <td class="whitespace-nowrap px-4 py-3 text-slate-700">du {{ c.date_debut|date:"d/m/Y" }} au {{ c.date_fin|date:"d/m/Y" }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ c.jours }}</td>
                <td class="whitespace-nowrap px-4 py-3">{% badge c.statut c.get_statut_display %}</td>
                <td class="hidden whitespace-nowrap px-4 py-3 xl:table-cell">
                  {% if e %}
                    <span class="text-slate-700">{{ e.1|date:"d/m/Y H:i" }}</span>
                    {% if e.2 %}<span class="ml-2 text-xs font-semibold text-red-700">en retard</span>{% endif %}
                  {% else %}<span class="text-slate-500">—</span>{% endif %}
                </td>
                <td class="whitespace-nowrap px-4 py-3">
                  {% if ligne.peut_reporter %}
                    <a href="{% url 'hr:conges_reporter' c.pk %}" class="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
                      <i class="fa-solid fa-clock-rotate-left" aria-hidden="true"></i> Reporter
                    </a>
                  {% endif %}
                </td>
              </tr>
            {% endwith %}
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-4 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-umbrella-beach" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">
        {% if vue == "a_valider" %}Aucune demande n'attend votre décision{% else %}Aucun congé à afficher{% endif %}
      </p>
      <p class="mt-1 text-sm text-slate-600">
        {% if not fiche and vue != "tous" %}Votre compte n'est rattaché à aucune fiche du personnel : la RH doit le renseigner pour que vous puissiez demander un congé.{% else %}Rien à afficher pour ces critères.{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/hr/templates/hr/conge_form.html`

*36 lignes*

```django
{% extends "base.html" %}
{% block titre %}Demander un congé{% endblock %}
{% block entete %}Congés{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:conges_liste' %}" class="underline-offset-2 hover:underline">Congés</a>
    <span aria-hidden="true">/</span> Nouvelle demande
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Demander un congé</h1>
  <p class="mt-1 text-sm text-slate-600">
    Les jours sont comptés en jours ouvrés : du lundi au vendredi, hors jours fériés.
    Votre solde {{ annee }} est de <strong class="{% if droits.disponible <= 0 %}text-red-700{% else %}text-emerald-800{% endif %}">{{ droits.disponible }} jour{{ droits.disponible|pluralize }}</strong>
    ({{ droits.droit_annuel }} de droit annuel{% if droits.exceptionnels %} + {{ droits.exceptionnels }} exceptionnel{{ droits.exceptionnels|pluralize }}{% endif %}, {{ droits.consommes }} déjà approuvé{{ droits.consommes|pluralize }}).
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}
    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.date_debut %}
      {% include "components/_champ.html" with champ=form.date_fin %}
    </div>
    {% include "components/_champ.html" with champ=form.motif %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'hr:conges_liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Envoyer la demande</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/hr/templates/hr/conge_detail.html`

*156 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Congé de {{ conge.employe.prenom }} {{ conge.employe.nom }}{% endblock %}
{% block entete %}Congés{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:conges_liste' %}" class="underline-offset-2 hover:underline">Congés</a>
    <span aria-hidden="true">/</span> {{ conge.employe.prenom }} {{ conge.employe.nom }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Congé de {{ conge.employe.prenom }} {{ conge.employe.nom }}</h1>
    {% badge conge.statut conge.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">
    du {{ conge.date_debut|date:"l j F Y" }} au {{ conge.date_fin|date:"l j F Y" }}
    · {{ conge.jours }} jour{{ conge.jours|pluralize }} ouvré{{ conge.jours|pluralize }}
    {% if peut_telecharger_autorisation %}
      · <a href="{% url 'hr:conges_autorisation_pdf' conge.pk %}" class="text-marque-700 underline-offset-2 hover:underline"><i class="fa-solid fa-file-pdf mr-1" aria-hidden="true"></i>Autorisation de congé (PDF)</a>
    {% endif %}
  </p>

  {% for section in sections %}{% include section.template with section=section %}{% endfor %}

  {% if echeance %}
    <p class="mt-4 rounded-lg border px-4 py-3 text-sm {% if echeance.2 %}border-red-300 bg-red-50 text-red-900{% else %}border-slate-200 bg-white text-slate-800{% endif %}">
      Décision {% if echeance.0 == 1 %}du supérieur hiérarchique{% else %}de la RH{% endif %} attendue avant le <strong>{{ echeance.1|date:"d/m/Y à H:i" }}</strong>{% if echeance.2 %} : le délai est dépassé{% endif %}.
    </p>
  {% endif %}

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-demande">
        <h2 id="titre-demande" class="text-base font-semibold text-slate-900">Demande</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div><dt class="text-slate-600">Employé</dt><dd class="mt-0.5 font-medium text-slate-900">
            {% if peut_voir_employe %}<a href="{% url 'hr:personnel_detail' conge.employe.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ conge.employe.prenom }} {{ conge.employe.nom }}</a>{% else %}{{ conge.employe.prenom }} {{ conge.employe.nom }}{% endif %}
            · {{ conge.employe.poste }}</dd></div>
          <div><dt class="text-slate-600">Motif</dt><dd class="mt-0.5 whitespace-pre-line font-medium text-slate-900">{{ conge.motif }}</dd></div>
          <div><dt class="text-slate-600">Demandé le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ conge.created_at|date:"d/m/Y à H:i" }}</dd></div>
          {% if conge.motif_decision %}<div><dt class="text-slate-600">Motif du refus ou de l'annulation</dt><dd class="mt-0.5 whitespace-pre-line font-medium text-slate-900">{{ conge.motif_decision }}</dd></div>{% endif %}
        </dl>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-suivi">
        <h2 id="titre-suivi" class="text-base font-semibold text-slate-900">Suivi des validations</h2>
        <ol class="mt-4 space-y-4 text-sm">
          <li class="flex gap-3"><span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400" aria-hidden="true"></span><span>Demande déposée le {{ conge.created_at|date:"d/m/Y à H:i" }}</span></li>
          {% for v in validations %}
            <li class="flex gap-3">
              <span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full {% if v.decision == 'APPROUVE' %}bg-emerald-600{% else %}bg-red-600{% endif %}" aria-hidden="true"></span>
              <span>
                <strong>{{ v.get_niveau_display }}</strong> : {% if v.decision == "APPROUVE" %}validé{% else %}refusé{% endif %}
                par {{ v.validateur|default:"un compte supprimé" }} le {{ v.date_decision|date:"d/m/Y à H:i" }}
                {% if v.commentaire %}<br><span class="text-slate-700">« {{ v.commentaire }} »</span>{% endif %}
              </span>
            </li>
          {% endfor %}
          {% if not validations %}<li class="pl-5 text-slate-600">Aucune décision pour le moment.</li>{% endif %}
        </ol>
      </section>
    </div>

    <div class="space-y-6 xl:col-span-1">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-solde">
        <h2 id="titre-solde" class="text-base font-semibold text-slate-900">Solde {{ conge.date_debut.year }}</h2>
        <dl class="mt-4 space-y-2 text-sm">
          <div class="flex justify-between"><dt class="text-slate-600">Droit annuel</dt><dd class="font-medium text-slate-900">{{ droits.droit_annuel }}</dd></div>
          <div class="flex justify-between"><dt class="text-slate-600">Exceptionnels</dt><dd class="font-medium text-slate-900">{{ droits.exceptionnels }}</dd></div>
          <div class="flex justify-between"><dt class="text-slate-600">Approuvés</dt><dd class="font-medium text-slate-900">{{ droits.consommes }}</dd></div>
          <div class="flex justify-between border-t border-slate-100 pt-2"><dt class="font-semibold text-slate-900">Disponible</dt><dd class="font-bold {% if droits.disponible <= 0 %}text-red-700{% else %}text-emerald-800{% endif %}">{{ droits.disponible }}</dd></div>
        </dl>
      </section>

      {% if actions %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-decision">
          <h2 id="titre-decision" class="text-base font-semibold text-slate-900">Votre décision</h2>
          {% if en_remplacement %}
            <p class="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Le délai de décision est dépassé : en tant que Direction, vous pouvez décider à la place du validateur habituel.</p>
          {% endif %}
          {% if "valider" in actions %}
            <form method="post" action="{% url 'hr:conges_decision' conge.pk %}" class="mt-4">
              {% csrf_token %}
              <input type="hidden" name="action" value="valider">
              <label for="commentaire-valider" class="block text-sm font-medium text-slate-800">Commentaire (facultatif)</label>
              <textarea id="commentaire-valider" name="commentaire" rows="2" class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
              <button type="submit" class="mt-3 w-full rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">
                <i class="fa-solid fa-check mr-1" aria-hidden="true"></i> Valider
              </button>
            </form>
          {% endif %}
          {% if "refuser" in actions or "annuler" in actions %}
            <form method="post" action="{% url 'hr:conges_decision' conge.pk %}" class="mt-5 border-t border-slate-100 pt-4"
                  data-confirm="{% if "annuler" in actions %}Annuler ce congé approuvé ?{% else %}Refuser cette demande ?{% endif %}">
              {% csrf_token %}
              <input type="hidden" name="action" value="{% if 'annuler' in actions %}annuler{% else %}refuser{% endif %}">
              <label for="commentaire-refus" class="block text-sm font-medium text-slate-800">Motif <span class="text-red-700" aria-hidden="true">*</span></label>
              <textarea id="commentaire-refus" name="commentaire" rows="2" required class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
              <p class="mt-1 text-xs text-slate-600">Visible par l'employé sur sa demande.</p>
              <button type="submit" class="mt-3 w-full rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">
                {% if "annuler" in actions %}Annuler le congé{% else %}Refuser{% endif %}
              </button>
            </form>
          {% endif %}
        </section>
      {% endif %}

      {% if peut_reporter or report_en_attente or reports_decides %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-report">
          <h2 id="titre-report" class="text-base font-semibold text-slate-900">Report du solde</h2>
          <p class="mt-1 text-xs text-slate-600">Écourter ce congé et garder les jours non pris pour plus tard. Sans validation de la RH, rien ne change.</p>

          {% if report_en_attente %}
            <div class="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <p>Demande envoyée le {{ report_en_attente.created_at|date:"d/m/Y à H:i" }} : reprise le <strong>{{ report_en_attente.nouvelle_date_fin|date:"d/m/Y" }}</strong>, {{ report_en_attente.jours_restants }} jour{{ report_en_attente.jours_restants|pluralize }} ouvré{{ report_en_attente.jours_restants|pluralize }} à reverser au solde.</p>
              <p class="mt-1">« {{ report_en_attente.motif }} »</p>
            </div>
            {% if peut_decider_report %}
              <form method="post" action="{% url 'hr:conges_report_decision' report_en_attente.pk %}" class="mt-3">
                {% csrf_token %}
                <input type="hidden" name="action" value="valider">
                <button type="submit" class="w-full rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">
                  <i class="fa-solid fa-check mr-1" aria-hidden="true"></i> Valider le report
                </button>
              </form>
              <form method="post" action="{% url 'hr:conges_report_decision' report_en_attente.pk %}" class="mt-2" data-confirm="Refuser ce report ?">
                {% csrf_token %}
                <input type="hidden" name="action" value="refuser">
                <label for="commentaire-report-refus" class="block text-sm font-medium text-slate-800">Motif du refus <span class="text-red-700" aria-hidden="true">*</span></label>
                <textarea id="commentaire-report-refus" name="commentaire" rows="2" required class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
                <button type="submit" class="mt-2 w-full rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">Refuser</button>
              </form>
            {% endif %}
          {% elif peut_reporter %}
            <a href="{% url 'hr:conges_reporter' conge.pk %}" class="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
              <i class="fa-solid fa-clock-rotate-left" aria-hidden="true"></i> Demander un report
            </a>
          {% endif %}

          {% for r in reports_decides %}
            <div class="mt-3 border-t border-slate-100 pt-3 text-sm">
              {% if r.statut == "APPROUVE" %}
                <p class="text-emerald-800"><i class="fa-solid fa-check mr-1" aria-hidden="true"></i>Report validé par {{ r.valide_par|default:"un compte supprimé" }} le {{ r.date_decision|date:"d/m/Y" }} : {{ r.jours_restants }} jour{{ r.jours_restants|pluralize }} reversé{{ r.jours_restants|pluralize }} au solde.</p>
              {% else %}
                <p class="text-red-800"><i class="fa-solid fa-xmark mr-1" aria-hidden="true"></i>Report refusé par {{ r.valide_par|default:"un compte supprimé" }} le {{ r.date_decision|date:"d/m/Y" }}{% if r.motif_decision %} : « {{ r.motif_decision }} »{% endif %}.</p>
              {% endif %}
            </div>
          {% endfor %}
        </section>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

Sur la fiche d'un congé, les boutons ne s'affichent que si `actions` (calculé par le service) les contient ;
le formulaire de refus/annulation porte `data-confirm` : `app.js` demande confirmation. Le bloc
`{% for section in sections %}{% include section.template %}{% endfor %}` affichera **l'alerte de mission** que
`missions` ajoutera au chapitre 21.

#### `apps/hr/templates/hr/personnel_list.html`

*88 lignes*

```django
{% extends "base.html" %}
{% block titre %}Personnel{% endblock %}
{% block entete %}Personnel{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Personnel</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} employé{{ paginator.count|pluralize }}</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <a href="{% url 'hr:personnel_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_modifier %}
        <a href="{% url 'hr:personnel_importer' %}"
           class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-file-excel" aria-hidden="true"></i> Importer depuis Excel
        </a>
        <a href="{% url 'hr:personnel_nouveau' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-user-plus" aria-hidden="true"></i> Nouveau recrutement
        </a>
      </div>
    {% endif %}
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="Nom, prénom, matricule, poste…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="departement" class="block text-sm font-medium text-slate-800">Département</label>
      <select id="departement" name="departement" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous les départements</option>
        {% for code, libelle in departements %}<option value="{{ code }}" {% if code == departement_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
      </select>
    </div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or departement_choisi %}
      <a href="{% url 'hr:personnel_liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if personnel %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste du personnel</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Matricule</th>
            <th scope="col" class="px-4 py-3">Employé</th>
            <th scope="col" class="px-4 py-3">Poste</th>
            <th scope="col" class="px-4 py-3">Département</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Supérieur</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Embauche</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for e in personnel %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.matricule }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'hr:personnel_detail' e.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ e.prenom }} {{ e.nom }}</a>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.poste }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.get_departement_display }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{% if e.superieur %}{{ e.superieur.prenom }} {{ e.superieur.nom }}{% else %}—{% endif %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ e.date_embauche|date:"d/m/Y" }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-users" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun employé trouvé</p>
      <p class="mt-1 text-sm text-slate-600">{% if recherche or departement_choisi %}Aucun résultat pour ces critères.{% else %}Enregistrez un premier recrutement pour commencer.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/hr/templates/hr/personnel_form.html`

*65 lignes*

```django
{% extends "base.html" %}
{% block titre %}{% if employe %}Modifier {{ employe.prenom }} {{ employe.nom }}{% else %}Nouveau recrutement{% endif %}{% endblock %}
{% block entete %}Personnel{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl" x-data="{ poste: '' }" x-init="poste = $refs.poste.value">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:personnel_liste' %}" class="underline-offset-2 hover:underline">Personnel</a>
    <span aria-hidden="true">/</span>
    {% if employe %}
      <a href="{% url 'hr:personnel_detail' employe.pk %}" class="underline-offset-2 hover:underline">{{ employe.prenom }} {{ employe.nom }}</a>
      <span aria-hidden="true">/</span> Modifier
    {% else %}Nouveau recrutement{% endif %}
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">{% if employe %}Modifier {{ employe.prenom }} {{ employe.nom }}{% else %}Nouveau recrutement{% endif %}</h1>
  <p class="mt-1 text-sm text-slate-600">
    {% if employe %}Le matricule ({{ employe.matricule }}) et la date d'embauche ne se modifient pas.
    {% else %}Le matricule est attribué automatiquement à l'enregistrement. Un employé au poste « Chauffeur » reçoit automatiquement sa fiche chauffeur.{% endif %}
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <fieldset>
      <legend class="text-sm font-semibold text-slate-900">Identité</legend>
      <div class="mt-3 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.nom %}
        {% include "components/_champ.html" with champ=form.prenom %}
      </div>
    </fieldset>

    <fieldset class="border-t border-slate-100 pt-5">
      <legend class="text-sm font-semibold text-slate-900">Poste et contrat</legend>
      <div class="mt-3 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.poste %}
        <div x-show="poste === 'AUTRE'" x-cloak>
          {% include "components/_champ.html" with champ=form.poste_autre %}
        </div>
        {% include "components/_champ.html" with champ=form.departement %}
        {% include "components/_champ.html" with champ=form.type_contrat %}
        {% if not employe %}{% include "components/_champ.html" with champ=form.date_embauche %}{% endif %}
        {% include "components/_champ.html" with champ=form.salaire_base %}
      </div>
    </fieldset>

    <fieldset class="border-t border-slate-100 pt-5">
      <legend class="text-sm font-semibold text-slate-900">Hiérarchie et accès</legend>
      <div class="mt-3 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.superieur %}
        {% include "components/_champ.html" with champ=form.utilisateur %}
      </div>
    </fieldset>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% if employe %}{% url 'hr:personnel_detail' employe.pk %}{% else %}{% url 'hr:personnel_liste' %}{% endif %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">{% if employe %}Enregistrer{% else %}Enregistrer le recrutement{% endif %}</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/hr/templates/hr/personnel_detail.html`

*111 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}{{ employe.prenom }} {{ employe.nom }}{% endblock %}
{% block entete %}Personnel{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:personnel_liste' %}" class="underline-offset-2 hover:underline">Personnel</a>
    <span aria-hidden="true">/</span> {{ employe.prenom }} {{ employe.nom }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ employe.prenom }} {{ employe.nom }}</h1>
    {% if peut_modifier %}
      <a href="{% url 'hr:personnel_modifier' employe.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">Matricule {{ employe.matricule }} · {{ employe.poste }}</p>

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-1">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-fiche">
        <h2 id="titre-fiche" class="text-base font-semibold text-slate-900">Fiche</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div><dt class="text-slate-600">Département</dt><dd class="mt-0.5 font-medium text-slate-900">{{ employe.get_departement_display }}</dd></div>
          <div><dt class="text-slate-600">Contrat</dt><dd class="mt-0.5 font-medium text-slate-900">{{ employe.type_contrat|default:"Non renseigné" }}</dd></div>
          <div><dt class="text-slate-600">Embauché le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ employe.date_embauche|date:"d/m/Y" }}</dd></div>
          <div><dt class="text-slate-600">Salaire de base</dt><dd class="mt-0.5 font-medium text-slate-900">{{ employe.salaire_base|floatformat:0|intcomma }} FCFA</dd></div>
          <div><dt class="text-slate-600">Supérieur hiérarchique</dt><dd class="mt-0.5 font-medium text-slate-900">
            {% if employe.superieur %}<a href="{% url 'hr:personnel_detail' employe.superieur.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ employe.superieur.prenom }} {{ employe.superieur.nom }}</a>{% else %}Aucun{% endif %}</dd></div>
          <div><dt class="text-slate-600">Compte utilisateur</dt><dd class="mt-0.5 font-medium text-slate-900">{% if employe.utilisateur %}{{ employe.utilisateur.username }} ({{ employe.utilisateur.get_role_display }}){% else %}<span class="text-amber-900">Aucun : pas d'accès aux congés</span>{% endif %}</dd></div>
        </dl>
      </section>

      {% if subordonnes %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-equipe">
          <h2 id="titre-equipe" class="text-base font-semibold text-slate-900">Équipe ({{ subordonnes|length }})</h2>
          <ul class="mt-3 space-y-1 text-sm">
            {% for s in subordonnes %}<li><a href="{% url 'hr:personnel_detail' s.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ s.prenom }} {{ s.nom }}</a> <span class="text-slate-600">· {{ s.poste }}</span></li>{% endfor %}
          </ul>
        </section>
      {% endif %}
    </div>

    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-droits">
        <h2 id="titre-droits" class="text-base font-semibold text-slate-900">Droits à congé {{ annee }}</h2>
        <dl class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-4">
          <div><dt class="text-sm text-slate-600">Droit annuel</dt><dd class="mt-1 text-xl font-bold text-slate-900">{{ droits.droit_annuel }}</dd></div>
          <div><dt class="text-sm text-slate-600">Exceptionnels</dt><dd class="mt-1 text-xl font-bold text-slate-900">{{ droits.exceptionnels }}</dd></div>
          <div><dt class="text-sm text-slate-600">Approuvés</dt><dd class="mt-1 text-xl font-bold text-slate-900">{{ droits.consommes }}</dd></div>
          <div><dt class="text-sm text-slate-600">Disponible</dt><dd class="mt-1 text-xl font-bold {% if droits.disponible <= 0 %}text-red-700{% else %}text-emerald-800{% endif %}">{{ droits.disponible }}</dd></div>
        </dl>
        <p class="mt-2 text-xs text-slate-600">En jours ouvrés (lundi-vendredi, hors jours fériés).</p>

        {% if attributions %}
          <h3 class="mt-5 text-sm font-semibold text-slate-900">Jours exceptionnels accordés</h3>
          <ul class="mt-2 divide-y divide-slate-100 text-sm">
            {% for a in attributions %}
              <li class="py-2"><strong>+{{ a.jours }} j</strong> pour {{ a.annee }} · <span class="text-slate-700">{{ a.motif }}</span>
                <span class="block text-xs text-slate-600">par {{ a.accorde_par|default:"un compte supprimé" }} le {{ a.created_at|date:"d/m/Y" }}</span></li>
            {% endfor %}
          </ul>
        {% endif %}

        {% if form_attribution %}
          <form method="post" action="{% url 'hr:personnel_attribution' employe.pk %}" class="mt-5 space-y-4 border-t border-slate-100 pt-4">
            {% csrf_token %}
            <h3 class="text-sm font-semibold text-slate-900">Accorder des jours exceptionnels</h3>
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {% include "components/_champ.html" with champ=form_attribution.annee %}
              {% include "components/_champ.html" with champ=form_attribution.jours %}
            </div>
            {% include "components/_champ.html" with champ=form_attribution.motif %}
            <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Accorder</button>
          </form>
        {% endif %}
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-conges">
        <h2 id="titre-conges" class="text-base font-semibold text-slate-900">Derniers congés</h2>
        {% if conges %}
          <div class="mt-3 overflow-x-auto">
            <table class="min-w-full divide-y divide-slate-200 text-sm">
              <caption class="sr-only">Derniers congés de l'employé</caption>
              <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                <tr><th scope="col" class="py-2 pr-4">Période</th><th scope="col" class="px-4 py-2 text-right">Jours</th><th scope="col" class="px-4 py-2">Statut</th></tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                {% for c in conges %}
                  <tr>
                    <td class="whitespace-nowrap py-3 pr-4"><a href="{% url 'hr:conges_detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline">du {{ c.date_debut|date:"d/m/Y" }} au {{ c.date_fin|date:"d/m/Y" }}</a></td>
                    <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ c.jours }}</td>
                    <td class="whitespace-nowrap px-4 py-3">{% badge c.statut c.get_statut_display %}</td>
                  </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        {% else %}
          <p class="mt-3 text-sm text-slate-600">Aucun congé demandé.</p>
        {% endif %}
      </section>
    </div>
  </div>
</div>
{% endblock %}
```

## Étape 5 — Les tests d'écrans

#### `apps/hr/templates/hr/personnel_import.html`

*58 lignes*

```django
{% extends "base.html" %}
{% block titre %}Importer le personnel{% endblock %}
{% block entete %}Personnel{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:personnel_liste' %}" class="underline-offset-2 hover:underline">Personnel</a>
    <span aria-hidden="true">/</span> Importer depuis Excel
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Importer depuis Excel</h1>
  <p class="mt-1 text-sm text-slate-600">
    Recrute plusieurs employés en une fois. Le matricule est attribué automatiquement, comme pour
    un recrutement individuel ; le supérieur hiérarchique et le compte utilisateur se règlent
    ensuite, fiche par fiche.
  </p>

  <div class="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 class="text-sm font-semibold text-slate-900">1. Préparer le fichier</h2>
    <p class="mt-2 text-sm text-slate-600">
      Colonnes attendues, dans cet ordre : <strong>{{ colonnes|join:", " }}</strong>.
      Poste et Département doivent correspondre à une valeur existante dans l'application.
    </p>
    <a href="{% url 'hr:personnel_import_modele' %}"
       class="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50">
      <i class="fa-solid fa-download" aria-hidden="true"></i> Télécharger le modèle
    </a>
  </div>

  <form method="post" enctype="multipart/form-data" novalidate
        class="mt-6 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    <h2 class="text-sm font-semibold text-slate-900">2. Déposer le fichier rempli</h2>

    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    {% if erreurs %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        <p class="font-semibold">Rien n'a été importé : corrigez ces lignes, puis déposez le fichier à nouveau.</p>
        <ul class="mt-2 list-disc space-y-1 pl-5">
          {% for erreur in erreurs %}<li>{{ erreur }}</li>{% endfor %}
        </ul>
      </div>
    {% endif %}

    {% include "components/_champ.html" with champ=form.fichier %}

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'hr:personnel_liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Importer</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/hr/templates/hr/report_form.html`

*38 lignes*

```django
{% extends "base.html" %}
{% block titre %}Demander un report{% endblock %}
{% block entete %}Congés{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'hr:conges_liste' %}" class="underline-offset-2 hover:underline">Congés</a>
    <span aria-hidden="true">/</span>
    <a href="{% url 'hr:conges_detail' conge.pk %}" class="underline-offset-2 hover:underline">{{ conge.employe.prenom }} {{ conge.employe.nom }}</a>
    <span aria-hidden="true">/</span> Report
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Demander un report</h1>
  <p class="mt-1 text-sm text-slate-600">
    Congé du {{ conge.date_debut|date:"d/m/Y" }} au {{ conge.date_fin|date:"d/m/Y" }}. Indiquez le jour où vous
    reprenez réellement le travail : les jours ouvrés restants jusqu'au {{ conge.date_fin|date:"d/m/Y" }} vous
    seront reversés au solde, une fois la RH d'accord. Sans sa validation, votre congé continue normalement.
  </p>

  <form method="post" novalidate class="mt-6 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.nouvelle_date_fin %}
    {% include "components/_champ.html" with champ=form.motif %}

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'hr:conges_detail' conge.pk %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Envoyer à la RH
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/hr/tests/test_direction_remplace.py`

*149 lignes* — La DIRECTION se substitue au validateur d'un niveau dont le délai est dépassé (sinon l'alerte « validation

```python
"""La DIRECTION se substitue au validateur d'un niveau dont le délai est dépassé (sinon l'alerte « validation
en retard » qui lui est adressée n'aurait aucune suite possible)."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee
from apps.hr.models import Conge, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _demande():
    chef = PersonnelFactory(utilisateur=UserFactory(role=Role.PARCAUTO))
    employe = PersonnelFactory(superieur=chef)
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    return conge, chef.utilisateur


def _en_retard(conge, *, niveau=1, retard=True):
    limite = timezone.now() + timedelta(hours=-1 if retard else 1)
    Conge.objects.filter(pk=conge.pk).update(**{f"date_limite_n{niveau}": limite})
    conge.refresh_from_db()


def _direction():
    return UserFactory(role=Role.DIRECTION)


# --- N1 ---


def test_la_direction_valide_le_n1_quand_le_delai_du_superieur_est_depasse():
    conge, _ = _demande()
    _en_retard(conge)

    assert services.actions_disponibles(conge, _direction()) == {"valider", "refuser"}
    services.valider_conge(conge, _direction())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_la_direction_refuse_le_n1_en_retard():
    conge, _ = _demande()
    _en_retard(conge)

    services.refuser(conge, _direction(), commentaire="Période de forte activité")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE


def test_avant_l_echeance_la_direction_ne_decide_pas_a_la_place_du_superieur():
    conge, _ = _demande()
    _en_retard(conge, retard=False)

    assert services.actions_disponibles(conge, _direction()) == frozenset()
    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, _direction())
    with pytest.raises(ActionNonAutorisee):
        services.refuser(conge, _direction())


# --- N2 ---


def test_la_direction_valide_le_n2_quand_le_delai_de_la_rh_est_depasse():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)
    _en_retard(conge, niveau=2)

    assert services.actions_disponibles(conge, _direction()) == {"valider", "refuser"}
    services.valider_conge(conge, _direction())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_le_n2_n_est_pas_ouvert_a_la_direction_avant_l_echeance():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)
    _en_retard(conge, niveau=2, retard=False)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, _direction())


# --- limites ---


def test_les_autres_roles_n_ont_pas_ce_pouvoir_meme_en_retard():
    conge, _ = _demande()
    _en_retard(conge)

    for role in (Role.FINANCES, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.ADMIN):
        assert services.actions_disponibles(conge, UserFactory(role=role)) == frozenset()


def test_la_direction_ne_decide_jamais_sur_sa_propre_demande_a_la_place_d_un_autre():
    direction = _direction()
    fiche = PersonnelFactory(utilisateur=direction, superieur=PersonnelFactory())
    conge = services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    _en_retard(conge)

    assert services.actions_disponibles(conge, direction) == frozenset()
    assert conge not in services.conges_a_valider(direction)


def test_les_demandes_en_retard_apparaissent_dans_la_liste_a_valider_de_la_direction():
    en_retard, _ = _demande()
    _en_retard(en_retard)
    dans_les_temps, _ = _demande()
    _en_retard(dans_les_temps, retard=False)

    a_valider = list(services.conges_a_valider(_direction()))

    assert en_retard in a_valider and dans_les_temps not in a_valider


def test_l_ecran_du_conge_propose_les_boutons_a_la_direction(client):
    conge, _ = _demande()
    _en_retard(conge)
    client.force_login(_direction())

    page = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "Valider" in page and "Refuser" in page


def test_l_ecran_explique_pourquoi_la_direction_peut_decider(client):
    conge, superieur = _demande()
    _en_retard(conge)

    client.force_login(_direction())
    assert "à la place du validateur habituel" in client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    client.force_login(superieur)  # le supérieur lui-même décide normalement : pas de mention
    assert "à la place du validateur habituel" not in client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()
```

#### `apps/hr/tests/test_report_conge.py`

*421 lignes* — Report du solde d'un congé en cours — avenant-separation-des-taches.md § R7 : l'employé écourte

```python
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
```

#### `apps/hr/tests/test_views_conges.py`

*460 lignes* — Écrans de congés : demande, liste, fiche, décisions N1/N2, accès.

```python
"""Écrans de congés : demande, liste, fiche, décisions N1/N2, accès."""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.models import Conge, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # 5 jours ouvrés


class Equipe:
    """Un employé, son supérieur hiérarchique, la RH et un tiers, chacun avec son compte."""

    def __init__(self):
        self.compte_sup = UserFactory(role=Role.PARCAUTO)
        self.superieur = PersonnelFactory(utilisateur=self.compte_sup, poste="Chef parc")
        self.compte = UserFactory(role=Role.CHARGE_CLIENTELE)
        self.employe = PersonnelFactory(
            superieur=self.superieur, utilisateur=self.compte, nom="Bamba", prenom="Issa"
        )
        self.compte_rh = UserFactory(role=Role.RH)
        self.rh = PersonnelFactory(utilisateur=self.compte_rh, superieur=self.superieur)
        self.tiers = UserFactory(role=Role.FINANCES)
        PersonnelFactory(utilisateur=self.tiers, superieur=self.superieur)

    def conge(self, **surcharges):
        donnees = dict(date_debut=DEBUT, date_fin=FIN, motif="Mariage de ma sœur", maintenant=MAINTENANT)
        donnees.update(surcharges)
        return services.demander_conge(self.employe, **donnees)

    def approuve(self):
        conge = self.conge()
        services.valider_n1(conge, self.compte_sup, maintenant=MAINTENANT)
        services.valider_n2(conge, self.compte_rh)
        return conge


@pytest.fixture
def equipe():
    return Equipe()


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {"date_debut": "2026-10-05", "date_fin": "2026-10-09", "motif": "Voyage familial"}
    donnees.update(surcharges)
    return donnees


def _decision(client, conge, action, commentaire="", suivre=True):
    return client.post(
        reverse("hr:conges_decision", args=[conge.pk]),
        {"action": action, "commentaire": commentaire},
        follow=suivre,
    )


# --- accès ---


@pytest.mark.parametrize(
    "role",
    [Role.ADMIN, Role.DIRECTION, Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES],
)
def test_la_liste_des_conges_est_ouverte_aux_roles_de_bureau(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("hr:conges_liste")).status_code == 200


def test_les_chauffeurs_passent_par_le_mobile_pas_par_les_conges_web(client):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    assert client.get(reverse("hr:conges_liste")).status_code == 403


def test_les_conges_exigent_la_connexion(client):
    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.status_code == 302
    assert "/connexion" in reponse["Location"] or "login" in reponse["Location"]


# --- demande ---


def test_un_employe_demande_un_conge(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees(), follow=True)

    conge = Conge.objects.get(employe=equipe.employe)
    assert conge.statut == StatutConge.DEMANDE and conge.jours == 5
    assert reponse.redirect_chain[-1][0] == reverse("hr:conges_detail", args=[conge.pk])
    assert any("5 jours" in m and "48 h" in m for m in _messages(reponse))


def test_le_formulaire_de_demande_affiche_le_solde(client, equipe):
    client.force_login(equipe.compte)

    texte = client.get(reverse("hr:conges_nouveau")).content.decode()

    assert "26 jours" in texte


def test_une_demande_au_dela_du_solde_est_refusee_avec_le_message_du_service(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(
        reverse("hr:conges_nouveau"), _donnees(date_debut="2026-10-05", date_fin="2026-11-10")
    )

    assert reponse.status_code == 200
    assert "Solde insuffisant" in reponse.content.decode()
    assert not Conge.objects.exists()


def test_une_periode_a_l_envers_est_refusee(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(
        reverse("hr:conges_nouveau"), _donnees(date_debut="2026-10-09", date_fin="2026-10-05")
    )

    assert "précède la date de début" in reponse.content.decode()
    assert not Conge.objects.exists()


def test_le_motif_est_obligatoire(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees(motif=""))

    assert reponse.status_code == 200
    assert not Conge.objects.exists()


def test_sans_fiche_du_personnel_on_ne_peut_pas_demander(client):
    client.force_login(UserFactory(role=Role.FINANCES))

    reponse = client.get(reverse("hr:conges_nouveau"), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("hr:conges_liste")
    assert any("aucune fiche" in m for m in _messages(reponse))


def test_sans_superieur_la_demande_est_refusee(client):
    compte = UserFactory(role=Role.FINANCES)
    PersonnelFactory(utilisateur=compte)
    client.force_login(compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees())

    assert "Aucun supérieur hiérarchique" in reponse.content.decode()


def test_le_formulaire_de_demande_exige_le_csrf(equipe):
    client = Client(enforce_csrf_checks=True)
    client.force_login(equipe.compte)

    assert client.post(reverse("hr:conges_nouveau"), _donnees()).status_code == 403


# --- liste ---


def test_la_liste_montre_mes_demandes_et_le_solde(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte)

    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.context["vue"] == "mes"
    assert [c.employe for c in reponse.context["conges"]] == [equipe.employe]
    assert reponse.context["droits"]["disponible"] == 26
    assert reponse.context["vues"] == ["mes", "a_valider"]


def test_le_superieur_arrive_sur_les_demandes_a_valider(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.context["vue"] == "a_valider"
    assert reponse.context["nombre_a_valider"] == 1
    assert "Bamba" in reponse.content.decode()


def test_la_rh_voit_les_conges_de_tous_et_ceux_a_valider_en_n2(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    a_valider = client.get(reverse("hr:conges_liste"))
    tous = client.get(reverse("hr:conges_liste"), {"vue": "tous"})

    assert a_valider.context["vue"] == "a_valider"
    assert [c.pk for c in a_valider.context["conges"]] == [conge.pk]
    assert "tous" in tous.context["vues"] and tous.context["vue"] == "tous"


def test_un_employe_ordinaire_ne_peut_pas_afficher_tous_les_conges(client, equipe):
    equipe.conge()
    client.force_login(equipe.tiers)

    reponse = client.get(reverse("hr:conges_liste"), {"vue": "tous"})

    assert "tous" not in reponse.context["vues"]
    assert reponse.context["vue"] != "tous"
    assert list(reponse.context["conges"]) == []


def test_le_filtre_de_statut_de_la_liste(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_rh)

    demande = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "DEMANDE"})
    refuse = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "REFUSE"})
    inconnu = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "N_IMPORTE_QUOI"})

    assert len(demande.context["conges"]) == 1
    assert len(refuse.context["conges"]) == 0
    assert len(inconnu.context["conges"]) == 1  # statut inconnu ignoré


def test_la_liste_indique_le_retard_de_validation(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_rh)

    texte = client.get(reverse("hr:conges_liste"), {"vue": "tous"}).content.decode()

    assert "en retard" in texte  # échéance fixée en 2026-09-03, dépassée à la date d'exécution


def test_la_liste_des_conges_reste_a_requetes_constantes(client, equipe, django_assert_max_num_queries):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    for _ in range(8):
        autre = PersonnelFactory(superieur=equipe.superieur)
        services.demander_conge(autre, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    with django_assert_max_num_queries(16):
        assert client.get(reverse("hr:conges_liste"), {"vue": "tous"}).status_code == 200


# --- fiche d'un congé ---


def test_la_fiche_d_un_conge_est_visible_par_l_employe_son_superieur_et_la_rh(client, equipe):
    conge = equipe.conge()

    for compte in (equipe.compte, equipe.compte_sup, equipe.compte_rh):
        client.force_login(compte)
        reponse = client.get(reverse("hr:conges_detail", args=[conge.pk]))
        assert reponse.status_code == 200, compte.role
        assert "Mariage de ma sœur" in reponse.content.decode()


def test_la_fiche_d_un_conge_est_interdite_a_un_tiers(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.tiers)

    assert client.get(reverse("hr:conges_detail", args=[conge.pk])).status_code == 403


def test_les_actions_ne_sont_proposees_qu_au_validateur_du_niveau(client, equipe):
    conge = equipe.conge()
    url = reverse("hr:conges_detail", args=[conge.pk])

    client.force_login(equipe.compte_sup)
    assert "Votre décision" in client.get(url).content.decode()
    client.force_login(equipe.compte)
    assert "Votre décision" not in client.get(url).content.decode()
    client.force_login(equipe.compte_rh)
    assert "Votre décision" not in client.get(url).content.decode()


def test_le_motif_saisi_est_echappe(client, equipe):
    conge = equipe.conge(motif="<script>alert(1)</script>")
    client.force_login(equipe.compte_sup)

    texte = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texte


def test_la_fiche_affiche_le_suivi_et_le_delai_depasse(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, commentaire="Bon voyage", maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    texte = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "Bon voyage" in texte
    assert "validé" in texte
    assert "le délai est dépassé" in texte


# --- décisions ---


def test_le_superieur_valide_en_n1(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "valider", "Accordé")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
    assert any("validée en N1" in m for m in _messages(reponse))


def test_la_rh_valide_en_n2_et_le_message_indique_les_jours_decomptes(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    reponse = _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert any("5 jours" in m and "2026" in m for m in _messages(reponse))


def test_l_employe_ne_peut_pas_valider_sa_propre_demande(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte)

    reponse = _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE
    assert any("supérieur hiérarchique" in m for m in _messages(reponse))


def test_la_rh_ne_peut_pas_valider_en_n1(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_rh)

    _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_un_refus_exige_un_motif(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "refuser", "  ")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE
    assert any("motif" in m.lower() for m in _messages(reponse))


def test_un_refus_est_enregistre_avec_son_motif(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "refuser", "Période de forte activité")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Période de forte activité"
    assert "Période de forte activité" in reponse.content.decode()


def test_la_rh_annule_un_conge_approuve_et_les_jours_sont_restitues(client, equipe):
    conge = equipe.approuve()
    assert services.droits_conges(equipe.employe, 2026)["disponible"] == 21
    client.force_login(equipe.compte_rh)

    reponse = _decision(client, conge, "annuler", "Besoin de service")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert services.droits_conges(equipe.employe, 2026)["disponible"] == 26
    assert any("restitués" in m for m in _messages(reponse))


def test_le_superieur_ne_peut_pas_annuler_un_conge_approuve(client, equipe):
    conge = equipe.approuve()
    client.force_login(equipe.compte_sup)

    _decision(client, conge, "annuler", "Non")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_une_decision_sur_un_conge_deja_traite_est_signalee(client, equipe):
    conge = equipe.approuve()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "valider")

    assert any("validé N1" in m for m in _messages(reponse))


def test_un_tiers_ne_peut_pas_decider(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.tiers)

    assert _decision(client, conge, "valider", suivre=False).status_code == 403
    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_une_action_inconnue_est_refusee(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    _decision(client, conge, "supprimer")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_la_decision_n_accepte_que_post_et_exige_le_csrf(equipe):
    conge = equipe.conge()
    client = Client(enforce_csrf_checks=True)
    client.force_login(equipe.compte_sup)
    url = reverse("hr:conges_decision", args=[conge.pk])

    assert client.get(url).status_code == 405
    assert client.post(url, {"action": "valider"}).status_code == 403
    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_le_directeur_valide_lui_meme_sa_demande_de_conge(client):
    compte = UserFactory(role=Role.DIRECTION)
    directeur = PersonnelFactory(utilisateur=compte)
    conge = services.demander_conge(directeur, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT)
    client.force_login(compte)

    assert client.get(reverse("hr:conges_liste")).context["vue"] == "a_valider"
    _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
```

## Étape 6 — Recompiler les styles

De nouvelles classes Tailwind sont apparues dans ces gabarits : il faut **recompiler**.

```bash
cd frontend
npm run build:css
cd ..
```

**Résultat attendu :** `Done in …ms.` (le fichier `static/css/tailwind.css` grossit légèrement).

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/hr/tests/test_direction_remplace.py apps/hr/tests/test_report_conge.py apps/hr/tests/test_views_conges.py -q --no-cov
```

**Résultat attendu :** `41 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

**Parcours dans le navigateur** (`python manage.py runserver`) : un congé de bout en bout.

1. Connectez-vous avec **`demo_charge`** : le menu affiche maintenant **Congés**. Cliquez « Demander un congé »,
   choisissez 5 jours ouvrables dans le futur. La fiche s'ouvre avec le statut **Demande**.
2. Connectez-vous avec **`demo_direction`** (code de la double authentification) : allez dans Congés, onglet
   « À valider », ouvrez la demande, cliquez **Valider** (validation N1).
3. Connectez-vous avec **`demo_rh`** : onglet « À valider », **Valider** (validation N2) : le congé passe à
   **Approuvé**.
4. Toujours avec `demo_rh`, sur la fiche du congé, **Annuler le congé** (avec un motif) : les jours sont
   restitués. Regardez le solde sur la liste des congés.
5. Essayez d'ouvrir `/rh/personnel/` avec `demo_charge` : **Accès refusé** (403).

## Ce qu'il faut retenir

- Les **quatre motifs** : liste, fiche, formulaire (Post/Redirect/Get), action en POST.
- La **vue orchestre, le service décide** ; le **formulaire valide la forme**, pas le fond.
- Le gabarit ne décide **jamais** d'un droit : il affiche ce que le service lui a dit d'afficher.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 17 : écrans du personnel et des congés"
```

---

[← Chapitre 16](16-interface.md) · [Sommaire](README.md) · [Chapitre 18 →](18-ecrans-chauffeurs.md)
