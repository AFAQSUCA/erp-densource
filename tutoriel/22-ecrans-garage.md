# Chapitre 22 — Écrans : garage, incidents et check-lists

> 14 fichier(s) dans ce chapitre, 1463 lignes de code.

## Ce que vous allez construire

Les **écrans du garage** (Parc Auto : gestion ; Direction : lecture seule).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| **Ordres de réparation** (liste, fiche, ouverture, clôture) | `/garage/`, `/garage/<id>/`, `/garage/nouveau/`, `/garage/<id>/cloturer/` | ouvrir un OR depuis la fiche d'un camion, clôturer en saisissant la main-d'œuvre |
| **Incidents** signalés par les chauffeurs | `/garage/incidents/`, `/garage/incidents/<id>/` | prendre en compte, clore avec la suite donnée |
| **Check-lists** des chauffeurs | `/garage/checklists/` | consulter les points KO |
| Actions sur un camion | `/garage/camions/<id>/immobiliser/`… | immobiliser, mettre hors service, remettre en service |
| **Bloc « Maintenance »** | dans la fiche d'un camion (`/flotte/<id>/`) | historique des OR, boutons d'action |

## Prérequis

- Chapitres 1 à 21 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le bloc qu'on attendait** : c'est ici que `_maintenance_vehicule.html` existe enfin. Dès que ce fichier est
  créé, la fiche d'un camion (chapitre 20) affiche **automatiquement** le bloc « Maintenance » : `fleet` n'a pas
  changé d'une ligne. C'est la force des registres.
- **Deux fichiers de vues** : `views.py` (gestion des OR et du statut des camions) et `views_terrain.py` (ce qui
  vient du terrain : incidents et check-lists). Même chose pour les formulaires : `forms.py` et
  `forms_terrain.py`.
- **Des actions manuelles gardées** : immobiliser, mettre hors service, remettre en service passent par une classe
  mère (`StatutVehiculeView`) qui appelle le service correspondant.

## Étape 1 — Formulaires

#### `apps/garage/forms.py`

*38 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin
from apps.fleet import services as fleet_services

from .models import LieuReparation, TypeOr


class OrForm(StyleTailwindMixin, forms.Form):
    """Ouverture d'un ordre de réparation (cahier-des-charges.md:163-165)."""

    vehicule = forms.ModelChoiceField(label="Camion", queryset=None)
    type_or = forms.ChoiceField(label="Type d'intervention", choices=TypeOr.choices)
    lieu = forms.ChoiceField(label="Lieu de la réparation", choices=LieuReparation.choices)
    motif = forms.CharField(
        label="Motif / symptômes", widget=forms.Textarea(attrs={"rows": 4})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.get_statut_display()})"
        )


class ClotureForm(StyleTailwindMixin, forms.Form):
    """Clôture : saisie de la main-d'œuvre (les pièces se déduisent du stock)."""

    cout_main_oeuvre = forms.DecimalField(
        label="Coût de la main-d'œuvre (FCFA)",
        min_value=0,
        decimal_places=2,
        max_digits=12,
        initial=0,
    )
```

#### `apps/garage/forms_terrain.py`

*56 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import GraviteIncident, StatutIncident

ACTION_PRENDRE, ACTION_CLORE = "prendre", "clore"


class FiltreIncidentsForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False)
    statut = forms.ChoiceField(
        label="Statut", choices=[("", "Tous les statuts")] + StatutIncident.choices, required=False
    )
    gravite = forms.ChoiceField(
        label="Gravité", choices=[("", "Toutes")] + GraviteIncident.choices, required=False
    )

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q") or "",
            "statut": donnees.get("statut") or "",
            "gravite": donnees.get("gravite") or "",
        }


class TraitementIncidentForm(StyleTailwindMixin, forms.Form):
    """Prise en compte ou clôture d'un incident, avec la suite donnée."""

    action = forms.ChoiceField(
        choices=[(ACTION_PRENDRE, "Prendre en compte"), (ACTION_CLORE, "Clore")],
        widget=forms.HiddenInput,
    )
    note = forms.CharField(
        label="Suite donnée", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("action") == ACTION_CLORE and not donnees.get("note", "").strip():
            self.add_error("note", "Indiquez la suite donnée pour clore l'incident.")
        return donnees


class FiltreChecklistsForm(StyleTailwindMixin, forms.Form):
    q = forms.CharField(label="Rechercher", required=False)
    anomalies = forms.BooleanField(label="Avec points KO seulement", required=False)

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {"recherche": donnees.get("q") or "", "avec_anomalies": bool(donnees.get("anomalies"))}
```

## Étape 2 — Vues et adresses

#### `apps/garage/views.py`

*157 lignes* — Écrans du garage : liste et fiche des OR, ouverture, clôture, statut des camions.

```python
"""Écrans du garage : liste et fiche des OR, ouverture, clôture, statut des camions.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante
from apps.fleet import services as fleet_services

from . import permissions, sections, services
from .exceptions import GarageError
from .forms import ClotureForm, OrForm
from .models import LieuReparation, StatutOr, TypeOr


class OrListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/or_list.html"
    context_object_name = "ordres"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_ordres(
            statut=self.request.GET.get("statut"),
            type_or=self.request.GET.get("type"),
            lieu=self.request.GET.get("lieu"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutOr.choices,
            types=TypeOr.choices,
            lieux=LieuReparation.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            type_choisi=self.request.GET.get("type", ""),
            lieu_choisi=self.request.GET.get("lieu", ""),
            recherche=self.request.GET.get("q", ""),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class OrDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "garage/or_detail.html"
    context_object_name = "ordre"

    def get_queryset(self):
        return services.ordres_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        ordre = self.object
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            sections=sections.DETAIL_OR.sections(ordre, self.request.user),
            peut_cloturer=peut_modifier and ordre.statut == StatutOr.OUVERT,
            form_cloture=ClotureForm()
            if peut_modifier and ordre.statut == StatutOr.OUVERT
            else None,
        )
        return contexte


class OrCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = OrForm
    template_name = "garage/or_form.html"

    def get_initial(self):
        # Prérempli depuis la fiche d'un camion : /garage/nouveau/?vehicule=<pk>
        try:
            return {"vehicule": int(self.request.GET.get("vehicule", ""))}
        except ValueError:
            return {}

    def form_valid(self, form):
        try:
            ordre = services.ouvrir_or(**form.cleaned_data)
        except GarageError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"OR {ordre.numero} ouvert : le camion {ordre.vehicule.immatriculation} "
            "est « En maintenance ».",
        )
        return redirect("garage:detail", pk=ordre.pk)


class OrCloturerView(RoleRequiredMixin, View):
    """Clôture un OR (POST) : main-d'œuvre saisie, statut du camion recalculé."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(services.ordres_queryset(), pk=pk)
        form = ClotureForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("garage:detail", pk=ordre.pk)
        try:
            services.cloturer_or(ordre, cout_main_oeuvre=form.cleaned_data["cout_main_oeuvre"])
        except GarageError as erreur:
            messages.error(request, str(erreur))
        else:
            ordre.vehicule.refresh_from_db()
            messages.success(
                request,
                f"OR {ordre.numero} clôturé : le camion {ordre.vehicule.immatriculation} "
                f"est « {ordre.vehicule.get_statut_display()} ».",
            )
        return redirect("garage:detail", pk=ordre.pk)


class StatutVehiculeView(RoleRequiredMixin, View):
    """Immobilise, met hors service ou remet en service un camion (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]
    action = None  # nom de la fonction de services.py

    def post(self, request, pk):
        vehicule = get_object_or_404(fleet_services.vehicules_queryset(), pk=pk)
        try:
            getattr(services, self.action)(vehicule)
        except GarageError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Camion {vehicule.immatriculation} : statut « {vehicule.get_statut_display()} ».",
            )
        return redirect("fleet:detail", pk=vehicule.pk)


class ImmobiliserView(StatutVehiculeView):
    action = "immobiliser_vehicule"


class HorsServiceView(StatutVehiculeView):
    action = "mettre_hors_service"


class RemiseEnServiceView(StatutVehiculeView):
    action = "remettre_en_service"
```

#### `apps/garage/views_terrain.py`

*120 lignes* — Écrans du Parc Auto pour les signalements du chauffeur : incidents et check-lists.

```python
"""Écrans du Parc Auto pour les signalements du chauffeur : incidents et check-lists.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``terrain.py`` (conventions.md:19-23). Ils sont alimentés par l'espace mobile du chauffeur.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante

from . import permissions, terrain
from .exceptions import GarageError
from .forms_terrain import (
    ACTION_PRENDRE,
    FiltreChecklistsForm,
    FiltreIncidentsForm,
    TraitementIncidentForm,
)
from .models import Incident, StatutIncident


class IncidentListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreIncidentsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return terrain.rechercher_incidents(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            a_traiter=terrain.incidents_a_traiter().count(),
        )
        return contexte


class IncidentDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "garage/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        return terrain.incidents_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        incident = self.object
        peut_traiter = (
            self.request.user.role_effectif in permissions.MODIFICATION
            and incident.statut != StatutIncident.CLOS
        )
        contexte.update(
            peut_traiter=peut_traiter,
            peut_prendre_en_compte=peut_traiter and incident.statut == StatutIncident.SIGNALE,
            form_traitement=TraitementIncidentForm() if peut_traiter else None,
        )
        return contexte


class IncidentTraiterView(RoleRequiredMixin, View):
    """Prend un incident en compte ou le clôt (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        form = TraitementIncidentForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("garage:incident", pk=incident.pk)
        note = form.cleaned_data["note"]
        try:
            if form.cleaned_data["action"] == ACTION_PRENDRE:
                terrain.prendre_en_compte(incident, request.user, note=note)
                messages.success(request, "Incident pris en compte.")
            else:
                terrain.clore_incident(incident, request.user, note=note)
                messages.success(request, "Incident clos.")
        except GarageError as erreur:
            messages.error(request, str(erreur))
        return redirect("garage:incident", pk=incident.pk)


class ChecklistListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/checklist_list.html"
    context_object_name = "checklists"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreChecklistsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return terrain.rechercher_checklists(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
        )
        return contexte
```

#### `apps/garage/urls.py`

*27 lignes*

```python
from django.urls import path

from . import views, views_terrain

app_name = "garage"

urlpatterns = [
    path("", views.OrListView.as_view(), name="liste"),
    path("nouveau/", views.OrCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.OrDetailView.as_view(), name="detail"),
    path("<int:pk>/cloturer/", views.OrCloturerView.as_view(), name="cloturer"),
    path("incidents/", views_terrain.IncidentListView.as_view(), name="incidents"),
    path("incidents/<int:pk>/", views_terrain.IncidentDetailView.as_view(), name="incident"),
    path(
        "incidents/<int:pk>/traiter/",
        views_terrain.IncidentTraiterView.as_view(),
        name="incident_traiter",
    ),
    path("checklists/", views_terrain.ChecklistListView.as_view(), name="checklists"),
    path("camions/<int:pk>/immobiliser/", views.ImmobiliserView.as_view(), name="immobiliser"),
    path("camions/<int:pk>/hors-service/", views.HorsServiceView.as_view(), name="hors_service"),
    path(
        "camions/<int:pk>/remise-en-service/",
        views.RemiseEnServiceView.as_view(),
        name="remise_en_service",
    ),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -21,4 +21,5 @@
     path("rh/", include("apps.hr.urls")),
     path("chauffeurs/", include("apps.drivers.urls")),
+    path("garage/", include("apps.garage.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
```

## Étape 3 — Gabarits

```bash
mkdir -p apps/garage/templates/garage
```

#### `apps/garage/templates/garage/or_list.html`

*99 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Garage{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Ordres de réparation</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} ordre{{ paginator.count|pluralize }} de réparation</p>
    </div>
    {% if peut_modifier %}
      <a href="{% url 'garage:creer' %}"
         class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvel OR
      </a>
    {% endif %}
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="N° d'OR, immatriculation, motif…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="statut" class="block text-sm font-medium text-slate-800">Statut</label>
      <select id="statut" name="statut" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous</option>
        {% for code, libelle in statuts %}<option value="{{ code }}" {% if code == statut_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
      </select>
    </div>
    <div>
      <label for="type" class="block text-sm font-medium text-slate-800">Type</label>
      <select id="type" name="type" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous</option>
        {% for code, libelle in types %}<option value="{{ code }}" {% if code == type_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
      </select>
    </div>
    <div>
      <label for="lieu" class="block text-sm font-medium text-slate-800">Lieu</label>
      <select id="lieu" name="lieu" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous</option>
        {% for code, libelle in lieux %}<option value="{{ code }}" {% if code == lieu_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
      </select>
    </div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or statut_choisi or type_choisi or lieu_choisi %}
      <a href="{% url 'garage:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if ordres %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des ordres de réparation</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">N°</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3">Type</th>
            <th scope="col" class="px-4 py-3">Lieu</th>
            <th scope="col" class="px-4 py-3">Motif</th>
            <th scope="col" class="px-4 py-3">Ouvert le</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for ordre in ordres %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'garage:detail' ordre.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ ordre.numero }}</a>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-800">{{ ordre.vehicule.immatriculation }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ ordre.get_type_or_display }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ ordre.get_lieu_display }}</td>
              <td class="max-w-xs truncate px-4 py-3 text-slate-700" title="{{ ordre.motif }}">{{ ordre.motif }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ ordre.date_ouverture|date:"d/m/Y" }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge ordre.statut ordre.get_statut_display %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <i class="fa-solid fa-screwdriver-wrench" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucun ordre de réparation trouvé</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or statut_choisi or type_choisi or lieu_choisi %}Aucun résultat pour ces critères.{% else %}Les OR ouverts apparaîtront ici.{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/garage/templates/garage/or_form.html`

*36 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvel ordre de réparation{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'garage:liste' %}" class="underline-offset-2 hover:underline">Garage</a>
    <span aria-hidden="true">/</span> Nouvel OR
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvel ordre de réparation</h1>
  <p class="mt-1 text-sm text-slate-600">
    L'OR reçoit son numéro à l'ouverture et le camion passe « En maintenance ». Si le camion est en mission,
    c'est l'enregistrement d'une panne en route : la mission continue et le statut sera recalculé à la clôture.
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}
    <div class="grid gap-5 sm:grid-cols-2">
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.vehicule %}</div>
      {% include "components/_champ.html" with champ=form.type_or %}
      {% include "components/_champ.html" with champ=form.lieu %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.motif %}</div>
    </div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'garage:liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Ouvrir l'OR</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/garage/templates/garage/or_detail.html`

*65 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}{{ ordre.numero }}{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'garage:liste' %}" class="underline-offset-2 hover:underline">Garage</a>
    <span aria-hidden="true">/</span> {{ ordre.numero }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ ordre.numero }}</h1>
    {% badge ordre.statut ordre.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">
    Camion
    <a href="{% url 'fleet:detail' ordre.vehicule.pk %}" class="font-medium text-marque-700 underline-offset-2 hover:underline">{{ ordre.vehicule.immatriculation }}</a>
    · {{ ordre.vehicule.marque }} {{ ordre.vehicule.modele }}
    · statut actuel : {% badge ordre.vehicule.statut ordre.vehicule.get_statut_display %}
  </p>

  <div class="mt-6 grid gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-intervention">
        <h2 id="titre-intervention" class="text-base font-semibold text-slate-900">Intervention</h2>
        <dl class="mt-4 grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Type</dt><dd class="mt-0.5 font-medium text-slate-900">{{ ordre.get_type_or_display }}</dd></div>
          <div><dt class="text-slate-600">Lieu</dt><dd class="mt-0.5 font-medium text-slate-900">{{ ordre.get_lieu_display }}</dd></div>
          <div><dt class="text-slate-600">Ouvert le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ ordre.date_ouverture|date:"d/m/Y H:i" }}</dd></div>
          <div><dt class="text-slate-600">Clôturé le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ ordre.date_cloture|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div class="sm:col-span-2"><dt class="text-slate-600">Motif / symptômes</dt><dd class="mt-0.5 whitespace-pre-line font-medium text-slate-900">{{ ordre.motif }}</dd></div>
        </dl>
      </section>

      {% for section in sections %}{% include section.template %}{% endfor %}
    </div>

    <div class="space-y-6">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-cout">
        <h2 id="titre-cout" class="text-base font-semibold text-slate-900">Main-d'œuvre</h2>
        <p class="mt-3 text-2xl font-bold text-slate-900">
          {% if ordre.statut == "CLOTURE" %}{{ ordre.cout_main_oeuvre|floatformat:0|intcomma }} FCFA{% else %}<span class="text-base font-medium text-slate-600">Saisie à la clôture</span>{% endif %}
        </p>
      </section>

      {% if form_cloture %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-cloture">
          <h2 id="titre-cloture" class="text-base font-semibold text-slate-900">Clôturer l'OR</h2>
          <p class="mt-1 text-xs text-slate-600">
            Le statut du camion sera recalculé : d'autres OR ouverts, une mission, puis un éventuel statut Immobilisé / Hors service.
          </p>
          <form method="post" action="{% url 'garage:cloturer' ordre.pk %}" class="mt-4 space-y-4"
                data-confirm="Clôturer cet ordre de réparation ? Les sorties de pièces ne seront plus possibles.">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_cloture.cout_main_oeuvre %}
            <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Clôturer l'OR</button>
          </form>
        </section>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/garage/templates/garage/_maintenance_vehicule.html`

*54 lignes*

```django
{% load ui %}
<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-maintenance">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 id="titre-maintenance" class="text-base font-semibold text-slate-900">Maintenance</h2>
    {% if section.contexte.peut_modifier %}
      <a href="{% url 'garage:creer' %}?vehicule={{ vehicule.pk }}"
         class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-screwdriver-wrench" aria-hidden="true"></i> Ouvrir un OR
      </a>
    {% endif %}
  </div>

  {% if section.contexte.ordres %}
    <ul class="mt-4 divide-y divide-slate-100 text-sm">
      {% for o in section.contexte.ordres %}
        <li class="flex flex-wrap items-center justify-between gap-2 py-2">
          <span>
            <a href="{% url 'garage:detail' o.pk %}" class="font-semibold text-marque-700 underline-offset-2 hover:underline">{{ o.numero }}</a>
            <span class="text-slate-700">· {{ o.get_type_or_display }} · {{ o.date_ouverture|date:"d/m/Y" }}</span>
          </span>
          {% badge o.statut o.get_statut_display %}
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="mt-3 text-sm text-slate-700">Aucun ordre de réparation pour ce camion.</p>
  {% endif %}

  {% if section.contexte.peut_immobiliser or section.contexte.peut_mettre_hors_service or section.contexte.peut_remettre_en_service %}
    <div class="mt-5 flex flex-wrap gap-3 border-t border-slate-100 pt-4">
      {% if section.contexte.peut_immobiliser %}
        <form method="post" action="{% url 'garage:immobiliser' vehicule.pk %}"
              data-confirm="Immobiliser ce camion ? Il ne pourra plus être affecté à une mission.">
          {% csrf_token %}
          <button type="submit" class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Immobiliser</button>
        </form>
      {% endif %}
      {% if section.contexte.peut_mettre_hors_service %}
        <form method="post" action="{% url 'garage:hors_service' vehicule.pk %}"
              data-confirm="Mettre ce camion hors service ?">
          {% csrf_token %}
          <button type="submit" class="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-600">Mettre hors service</button>
        </form>
      {% endif %}
      {% if section.contexte.peut_remettre_en_service %}
        <form method="post" action="{% url 'garage:remise_en_service' vehicule.pk %}"
              data-confirm="Remettre ce camion en service ? Son statut sera recalculé.">
          {% csrf_token %}
          <button type="submit" class="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">Remettre en service</button>
        </form>
      {% endif %}
    </div>
  {% endif %}
</section>
```

#### `apps/garage/templates/garage/incident_list.html`

*59 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Incidents{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Incidents signalés par les chauffeurs</h1>
      <p class="mt-1 text-sm text-slate-600">
        {{ paginator.count|default:0 }} incident{{ paginator.count|pluralize }}
        {% if a_traiter %}· <strong class="text-red-800">{{ a_traiter }} à traiter</strong>{% endif %}
      </p>
    </div>
    <a href="{% url 'garage:checklists' %}" class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-list-check" aria-hidden="true"></i> Check-lists
    </a>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.statut %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.gravite %}</div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'garage:incidents' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if incidents %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des incidents</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr><th scope="col" class="px-4 py-3">Date</th><th scope="col" class="px-4 py-3">Camion</th><th scope="col" class="px-4 py-3">Incident</th><th scope="col" class="px-4 py-3">Gravité</th><th scope="col" class="px-4 py-3">Statut</th><th scope="col" class="hidden px-4 py-3 xl:table-cell">Chauffeur</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for i in incidents %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ i.created_at|date:"d/m/Y H:i" }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-semibold"><a href="{% url 'garage:incident' i.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ i.vehicule.immatriculation }}</a></td>
              <td class="px-4 py-3 text-slate-900">{{ i.get_type_incident_display }}<span class="block max-w-xs truncate text-xs text-slate-600">{{ i.description }}</span></td>
              <td class="whitespace-nowrap px-4 py-3">{% badge i.gravite i.get_gravite_display %}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge i.statut i.get_statut_display %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{% if i.chauffeur %}{{ i.chauffeur.personnel.prenom }} {{ i.chauffeur.personnel.nom }}{% else %}—{% endif %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun incident</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Les pannes et incidents signalés depuis l'espace mobile apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/garage/templates/garage/incident_detail.html`

*57 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Incident {{ incident.vehicule.immatriculation }}{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'garage:incidents' %}" class="underline-offset-2 hover:underline">Incidents</a>
    <span aria-hidden="true">/</span> {{ incident.vehicule.immatriculation }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ incident.get_type_incident_display }} : {{ incident.vehicule.immatriculation }}</h1>
    {% badge incident.gravite incident.get_gravite_display %}
    {% badge incident.statut incident.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">Signalé le {{ incident.created_at|date:"d/m/Y à H:i" }}{% if incident.chauffeur %} par {{ incident.chauffeur.personnel.prenom }} {{ incident.chauffeur.personnel.nom }}{% endif %}</p>

  <div class="mt-6 grid gap-6 lg:grid-cols-3">
    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2" aria-labelledby="titre-incident">
      <h2 id="titre-incident" class="text-base font-semibold text-slate-900">Description</h2>
      <p class="mt-3 whitespace-pre-line text-sm text-slate-900">{{ incident.description }}</p>
      <dl class="mt-4 space-y-2 text-sm">
        <div><dt class="text-slate-600">Lieu</dt><dd class="font-medium text-slate-900">{{ incident.lieu|default:"Non précisé" }}</dd></div>
        <div><dt class="text-slate-600">Mission</dt><dd class="font-medium text-slate-900">{{ incident.mission.numero|default:"Aucune" }}</dd></div>
        <div><dt class="text-slate-600">Camion</dt><dd class="font-medium text-slate-900"><a href="{% url 'fleet:detail' incident.vehicule.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ incident.vehicule.immatriculation }}</a> · {{ incident.vehicule.marque }} {{ incident.vehicule.modele }} · {{ incident.vehicule.get_statut_display }}</dd></div>
      </dl>
      {% if incident.note_traitement %}
        <div class="mt-4 rounded-lg bg-slate-50 p-3 text-sm"><p class="font-semibold text-slate-900">Suite donnée</p><p class="mt-1 whitespace-pre-line text-slate-800">{{ incident.note_traitement }}</p><p class="mt-1 text-xs text-slate-600">{{ incident.traite_par|default:"—" }} · {{ incident.date_traitement|date:"d/m/Y à H:i" }}</p></div>
      {% endif %}
    </section>

    <section class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-suite">
      <h2 id="titre-suite" class="text-base font-semibold text-slate-900">Suite</h2>
      {% if peut_traiter %}
        <a href="{% url 'garage:creer' %}?vehicule={{ incident.vehicule.pk }}" class="flex items-center justify-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2"><i class="fa-solid fa-screwdriver-wrench" aria-hidden="true"></i> Ouvrir un OR</a>
        <p class="text-xs text-slate-600">L'ouverture d'un OR passe le camion « En maintenance ». Aucune action n'est automatique.</p>
        {% if peut_prendre_en_compte %}
          <form method="post" action="{% url 'garage:incident_traiter' incident.pk %}">{% csrf_token %}
            <input type="hidden" name="action" value="prendre">
            <button type="submit" class="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Prendre en compte</button>
          </form>
        {% endif %}
        <form method="post" action="{% url 'garage:incident_traiter' incident.pk %}" class="space-y-2 border-t border-slate-100 pt-4">{% csrf_token %}
          <input type="hidden" name="action" value="clore">
          <label for="note-cloture" class="block text-sm font-medium text-slate-800">Suite donnée <span class="text-red-700" aria-hidden="true">*</span></label>
          <textarea id="note-cloture" name="note" rows="3" required class="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
          <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Clore l'incident</button>
        </form>
      {% else %}
        <p class="text-sm text-slate-700">{% if incident.statut == "CLOS" %}Incident clos.{% else %}Le Parc Auto traite cet incident.{% endif %}</p>
      {% endif %}
    </section>
  </div>
</div>
{% endblock %}
```

#### `apps/garage/templates/garage/checklist_list.html`

*51 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Check-lists{% endblock %}
{% block entete %}Garage{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'garage:incidents' %}" class="underline-offset-2 hover:underline">Incidents</a>
    <span aria-hidden="true">/</span> Check-lists
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Check-lists des véhicules</h1>
  <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} check-list{{ paginator.count|pluralize }}, remplies par les chauffeurs avant le départ.</p>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
      <input type="checkbox" name="anomalies" value="on" {% if filtre.anomalies.value %}checked{% endif %} class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
      Avec points KO seulement
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'garage:checklists' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if checklists %}
    <ul class="mt-5 space-y-3">
      {% for c in checklists %}
        <li class="rounded-xl border bg-white p-4 shadow-sm {% if c.nb_anomalies %}border-amber-300{% else %}border-slate-200{% endif %}">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="font-semibold text-slate-900">{{ c.vehicule.immatriculation }} · mission {{ c.mission.numero }}
              <span class="font-normal text-slate-600">· {{ c.chauffeur.personnel.prenom }} {{ c.chauffeur.personnel.nom }} · {{ c.created_at|date:"d/m/Y H:i" }}</span></p>
            {% if c.nb_anomalies %}{% badge "ATTENTION" c.nb_anomalies|stringformat:"s"|add:" point(s) KO" %}{% else %}{% badge "VALIDE" "Tout est OK" %}{% endif %}
          </div>
          {% if c.nb_anomalies %}
            <ul class="mt-2 space-y-1 text-sm">
              {% for p in c.points %}{% if not p.ok %}<li><strong class="text-red-800">{{ p.libelle }}</strong> : {{ p.remarque }}</li>{% endif %}{% endfor %}
            </ul>
          {% endif %}
          {% if c.remarque %}<p class="mt-2 text-sm text-slate-700">Remarque : {{ c.remarque }}</p>{% endif %}
        </li>
      {% endfor %}
    </ul>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="font-semibold text-slate-900">Aucune check-list</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Les check-lists remplies depuis l'espace mobile apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

## Étape 4 — Tests et compilation des styles

#### `apps/garage/tests/test_views.py`

*431 lignes* — Écrans du garage : accès par rôle, OR, blocs dans la fiche d'un camion.

```python
"""Écrans du garage : accès par rôle, OR, blocs dans la fiche d'un camion."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import services
from apps.garage.models import LieuReparation, OrdreReparation, StatutOr, TypeOr
from apps.missions.tests.test_services import _affectee

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _ouvrir(camion=None, **surcharges):
    donnees = dict(type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Fuite d'huile")
    donnees.update(surcharges)
    return services.ouvrir_or(camion or VehiculeFactory(), **donnees)


def _statut(camion):
    camion.refresh_from_db()
    return camion.statut


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_garage_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)
    ordre = _ouvrir()

    assert client.get(reverse("garage:liste")).status_code == 200
    assert client.get(reverse("garage:detail", args=[ordre.pk])).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_garage_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)
    ordre = _ouvrir()

    assert client.get(reverse("garage:liste")).status_code == 403
    assert client.get(reverse("garage:detail", args=[ordre.pk])).status_code == 403
    assert client.get(reverse("garage:creer")).status_code == 403


def test_la_direction_est_en_lecture_seule_sur_le_garage(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()
    ordre = _ouvrir()

    assert client.get(reverse("garage:creer")).status_code == 403
    assert client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"}).status_code == 403
    assert client.post(reverse("garage:immobiliser", args=[camion.pk])).status_code == 403
    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("garage:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_garage_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/garage/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/garage/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_ordres(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir(VehiculeFactory(immatriculation="7777 GH 01"), motif="Freins")

    contenu = client.get(reverse("garage:liste")).content.decode()

    assert ordre.numero in contenu and "7777 GH 01" in contenu and "Freins" in contenu
    assert "Ouvert" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun ordre de réparation trouvé" in client.get(reverse("garage:liste")).content.decode()


def test_la_liste_filtre(client):
    _connecte(client, Role.PARCAUTO)
    cible = _ouvrir(type_or=TypeOr.PNEUMATIQUES, lieu=LieuReparation.EXTERNE, motif="Crevaison")
    autre = _ouvrir()
    services.cloturer_or(autre)

    par_type = client.get(reverse("garage:liste"), {"type": "PNEUMATIQUES"})
    par_statut = client.get(reverse("garage:liste"), {"statut": "CLOTURE"})
    par_texte = client.get(reverse("garage:liste"), {"q": "crevaison"})

    assert list(par_type.context["ordres"]) == [cible]
    assert list(par_statut.context["ordres"]) == [autre]
    assert list(par_texte.context["ordres"]) == [cible]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        _ouvrir()

    assert len(client.get(reverse("garage:liste"), {"page": 2}).context["ordres"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_ordre(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        _ouvrir()

    with django_assert_max_num_queries(10):
        client.get(reverse("garage:liste"))


def test_le_motif_saisi_est_echappe_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir(motif="<script>alert(1)</script>")

    for url in (reverse("garage:liste"), reverse("garage:detail", args=[ordre.pk])):
        contenu = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in contenu
        assert "&lt;script&gt;" in contenu


# --- fiche d'un OR ---


def test_la_fiche_affiche_l_intervention_et_le_camion(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(immatriculation="4444 KL 01")
    ordre = _ouvrir(camion, lieu=LieuReparation.EXTERNE, motif="Bruit moteur")

    contenu = client.get(reverse("garage:detail", args=[ordre.pk])).content.decode()

    assert ordre.numero in contenu and "4444 KL 01" in contenu
    assert "Prestataire externe" in contenu and "Bruit moteur" in contenu
    assert reverse("fleet:detail", args=[camion.pk]) in contenu
    assert "En maintenance" in contenu  # statut actuel du camion


def test_la_fiche_d_un_or_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("garage:detail", args=[999999])).status_code == 404


def test_la_fiche_propose_la_cloture_au_parc_auto_seulement_tant_que_l_or_est_ouvert(client):
    ordre = _ouvrir()
    _connecte(client, Role.PARCAUTO)
    assert reverse("garage:cloturer", args=[ordre.pk]) in client.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    assert reverse("garage:cloturer", args=[ordre.pk]) not in direction.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()

    services.cloturer_or(ordre)
    assert reverse("garage:cloturer", args=[ordre.pk]) not in client.get(
        reverse("garage:detail", args=[ordre.pk])
    ).content.decode()


# --- ouverture ---


def test_le_formulaire_d_ouverture_s_affiche_et_se_prerempli_depuis_un_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("garage:creer"), {"vehicule": camion.pk})

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["vehicule"] == camion.pk


def test_un_parametre_vehicule_invalide_est_ignore(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("garage:creer"), {"vehicule": "abc"})

    assert reponse.status_code == 200 and reponse.context["form"].initial == {}


def test_ouvrir_un_or(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("garage:creer"),
        {"vehicule": camion.pk, "type_or": "PREVENTIF", "lieu": "INTERNE", "motif": "Vidange"},
        follow=True,
    )

    ordre = OrdreReparation.objects.get()
    assert reponse.redirect_chain[-1][0] == reverse("garage:detail", args=[ordre.pk])
    assert (ordre.type_or, ordre.lieu, ordre.motif) == ("PREVENTIF", "INTERNE", "Vidange")
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE
    assert any(ordre.numero in m and "En maintenance" in m for m in _messages(reponse))


def test_ouvrir_un_or_sur_un_camion_en_mission_signale_une_panne(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule

    client.post(
        reverse("garage:creer"),
        {"vehicule": camion.pk, "type_or": "CURATIF", "lieu": "EXTERNE", "motif": "Panne"},
    )

    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


@pytest.mark.parametrize(
    "champ", [{"motif": ""}, {"type_or": "PEINTURE"}, {"lieu": "MAISON"}, {"vehicule": ""}]
)
def test_ouvrir_avec_des_donnees_invalides_est_refuse(client, champ):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    donnees = {"vehicule": camion.pk, "type_or": "CURATIF", "lieu": "INTERNE", "motif": "x"}
    donnees.update(champ)

    reponse = client.post(reverse("garage:creer"), donnees)

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert OrdreReparation.objects.count() == 0
    assert _statut(camion) == StatutVehicule.DISPONIBLE


# --- clôture ---


def test_cloturer_un_or_recalcule_le_statut_du_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    reponse = client.post(
        reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "45000"}, follow=True
    )

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.CLOTURE and ordre.cout_main_oeuvre == Decimal("45000.00")
    assert _statut(camion) == StatutVehicule.DISPONIBLE
    assert any("Disponible" in m for m in _messages(reponse))


def test_cloturer_un_or_d_un_camion_reserve_le_repasse_en_mission(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule
    ordre = _ouvrir(camion)

    client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"})

    assert _statut(camion) == StatutVehicule.EN_MISSION


def test_cloturer_avec_une_main_d_oeuvre_negative_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    client.post(reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "-5"})

    ordre.refresh_from_db()
    assert ordre.statut == StatutOr.OUVERT
    assert _statut(camion) == StatutVehicule.EN_MAINTENANCE


def test_cloturer_deux_fois_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir()
    services.cloturer_or(ordre)

    reponse = client.post(
        reverse("garage:cloturer", args=[ordre.pk]), {"cout_main_oeuvre": "0"}, follow=True
    )

    assert any("déjà clôturé" in m for m in _messages(reponse))


def test_la_cloture_refuse_le_get_et_un_or_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ouvrir()

    assert client.get(reverse("garage:cloturer", args=[ordre.pk])).status_code == 405
    assert client.post(reverse("garage:cloturer", args=[999999]), {"cout_main_oeuvre": "0"}).status_code == 404


# --- statut des camions ---


def test_immobiliser_puis_remettre_en_service_par_les_ecrans(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(reverse("garage:immobiliser", args=[camion.pk]), follow=True)
    assert _statut(camion) == StatutVehicule.IMMOBILISE
    assert reponse.redirect_chain[-1][0] == reverse("fleet:detail", args=[camion.pk])
    assert any("Immobilisé" in m for m in _messages(reponse))

    client.post(reverse("garage:remise_en_service", args=[camion.pk]))
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_mettre_hors_service_par_l_ecran(client):
    _connecte(client, Role.ADMIN)
    camion = VehiculeFactory()

    client.post(reverse("garage:hors_service", args=[camion.pk]))

    assert _statut(camion) == StatutVehicule.HORS_SERVICE


def test_immobiliser_un_camion_reserve_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    camion = _affectee().vehicule

    reponse = client.post(reverse("garage:immobiliser", args=[camion.pk]), follow=True)

    assert any("ouvrez un OR" in m for m in _messages(reponse))
    assert _statut(camion) == StatutVehicule.DISPONIBLE


def test_remettre_en_service_un_camion_disponible_affiche_l_erreur(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(reverse("garage:remise_en_service", args=[camion.pk]), follow=True)

    assert any("immobilisé ou hors service" in m for m in _messages(reponse))


def test_les_actions_de_statut_refusent_le_get_et_un_camion_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    assert client.get(reverse("garage:immobiliser", args=[camion.pk])).status_code == 405
    assert client.post(reverse("garage:immobiliser", args=[999999])).status_code == 404


# --- bloc « Maintenance » dans la fiche d'un camion ---


def test_la_fiche_du_camion_affiche_le_bloc_maintenance_et_l_historique(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert "Maintenance" in contenu and ordre.numero in contenu
    assert f"{reverse('garage:creer')}?vehicule={camion.pk}" in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) in contenu
    assert reverse("garage:remise_en_service", args=[camion.pk]) not in contenu


def test_le_bloc_propose_la_remise_en_service_d_un_camion_immobilise(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(statut=StatutVehicule.IMMOBILISE)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert reverse("garage:remise_en_service", args=[camion.pk]) in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) not in contenu


def test_la_direction_voit_l_historique_sans_les_boutons(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()
    ordre = _ouvrir(camion)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert ordre.numero in contenu
    assert reverse("garage:immobiliser", args=[camion.pk]) not in contenu
    assert f"{reverse('garage:creer')}?vehicule=" not in contenu


def test_les_formulaires_du_garage_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion = VehiculeFactory()

    assert client.post(reverse("garage:immobiliser", args=[camion.pk])).status_code == 403
    assert client.post(reverse("garage:creer"), {"vehicule": camion.pk}).status_code == 403
    assert _statut(camion) == StatutVehicule.DISPONIBLE


# --- gardes des blocs (défense en profondeur) ---


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_bloc_maintenance_n_est_jamais_fourni_aux_roles_sans_acces(role):
    from types import SimpleNamespace

    from apps.garage import sections

    camion = VehiculeFactory()

    assert sections.section_maintenance(camion, SimpleNamespace(role_effectif=role)) is None
```

#### `apps/garage/tests/test_views_terrain.py`

*199 lignes* — Écrans du Parc Auto : incidents et check-lists signalés par les chauffeurs.

```python
"""Écrans du Parc Auto : incidents et check-lists signalés par les chauffeurs."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage import terrain
from apps.garage.models import CODES_CHECKLIST, GraviteIncident, Incident, StatutIncident, TypeIncident
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _incident(**surcharges):
    chauffeur = ChauffeurFactory()
    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)
    donnees = dict(
        chauffeur=chauffeur, mission=mission, type_incident=TypeIncident.PANNE,
        gravite=GraviteIncident.MOYENNE, description="Moteur qui chauffe", lieu="Bouaké",
    )
    donnees.update(surcharges)
    return terrain.declarer_incident(**donnees)


def _checklist(anomalie=False):
    chauffeur = ChauffeurFactory()
    mission = MissionFactory(statut=StatutMission.AFFECTEE, vehicule=VehiculeFactory(), chauffeur=chauffeur)
    resultats = [{"code": c, "ok": True, "remarque": ""} for c in CODES_CHECKLIST]
    if anomalie:
        resultats[1].update(ok=False, remarque="Frein spongieux")
    return terrain.enregistrer_checklist(chauffeur=chauffeur, mission=mission, resultats=resultats)


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_incidents_et_checklists_sont_visibles_par_admin_direction_et_parc_auto(client, role):
    _connecte(client, role)
    incident = _incident()

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk]),
                reverse("garage:checklists")):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_incidents_et_checklists_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    incident = _incident()

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk]),
                reverse("garage:checklists")):
        assert client.get(url).status_code == 403, url


def test_la_liste_des_incidents_se_filtre_et_compte_ceux_a_traiter(client):
    _connecte(client, Role.PARCAUTO)
    grave = _incident(description="Crevaison pneu avant", gravite=GraviteIncident.GRAVE)
    _incident(description="Feu cassé")
    url = reverse("garage:incidents")

    assert client.get(url).context["a_traiter"] == 2
    assert [i.pk for i in client.get(url, {"q": "crevaison"}).context["incidents"]] == [grave.pk]
    assert [i.pk for i in client.get(url, {"gravite": "GRAVE"}).context["incidents"]] == [grave.pk]
    assert len(client.get(url, {"statut": "CLOS"}).context["incidents"]) == 0
    assert len(client.get(url, {"statut": "???", "page": "abc"}).context["incidents"]) == 2


def test_liste_vide_des_incidents(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun incident" in client.get(reverse("garage:incidents")).content.decode()


def test_la_fiche_propose_le_traitement_au_parc_auto_pas_a_la_direction(client):
    incident = _incident()
    url = reverse("garage:incident", args=[incident.pk])

    _connecte(client, Role.PARCAUTO)
    texte = client.get(url).content.decode()
    assert "Ouvrir un OR" in texte and "Prendre en compte" in texte and "Clore l'incident" in texte
    assert f"{reverse('garage:creer')}?vehicule={incident.vehicule.pk}" in texte

    _connecte(client, Role.DIRECTION)
    assert "Prendre en compte" not in client.get(url).content.decode()


def test_prendre_en_compte_puis_clore(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()
    url = reverse("garage:incident_traiter", args=[incident.pk])

    reponse = client.post(url, {"action": "prendre", "note": "On s'en occupe"}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.PRIS_EN_COMPTE
    assert any("pris en compte" in m for m in _messages(reponse))

    client.post(url, {"action": "clore", "note": " "}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.PRIS_EN_COMPTE  # motif vide : rien ne change

    reponse = client.post(url, {"action": "clore", "note": "Courroie remplacée"}, follow=True)
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.CLOS and "Courroie remplacée" in reponse.content.decode()
    assert "Prendre en compte" not in reponse.content.decode()


def test_un_incident_clos_ne_se_retraite_pas(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()
    url = reverse("garage:incident_traiter", args=[incident.pk])
    client.post(url, {"action": "clore", "note": "Fausse alerte"})

    reponse = client.post(url, {"action": "clore", "note": "Encore"}, follow=True)

    assert any("déjà clos" in m for m in _messages(reponse))


def test_la_direction_ne_peut_pas_traiter_meme_en_postant(client):
    _connecte(client, Role.DIRECTION)
    incident = _incident()

    assert client.post(reverse("garage:incident_traiter", args=[incident.pk]),
                       {"action": "clore", "note": "x"}).status_code == 403
    incident.refresh_from_db()
    assert incident.statut == StatutIncident.SIGNALE


def test_action_inconnue_ou_incident_inexistant(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident()

    client.post(reverse("garage:incident_traiter", args=[incident.pk]), {"action": "supprimer"})
    assert Incident.objects.get(pk=incident.pk).statut == StatutIncident.SIGNALE
    assert client.post(reverse("garage:incident_traiter", args=[999]), {"action": "prendre"}).status_code == 404
    assert client.get(reverse("garage:incident", args=[999])).status_code == 404


def test_traitement_en_post_avec_csrf_seulement():
    incident = _incident()
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.PARCAUTO))
    url = reverse("garage:incident_traiter", args=[incident.pk])

    assert http.get(url).status_code == 405
    assert http.post(url, {"action": "prendre"}).status_code == 403


def test_les_textes_de_l_incident_sont_echappes(client):
    _connecte(client, Role.PARCAUTO)
    incident = _incident(description="<script>alert(1)</script>", lieu="<img src=x onerror=alert(2)>")

    for url in (reverse("garage:incidents"), reverse("garage:incident", args=[incident.pk])):
        texte = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte, url


def test_la_liste_des_checklists_montre_les_points_ko_et_se_filtre(client):
    _connecte(client, Role.PARCAUTO)
    _checklist()
    avec_ko = _checklist(anomalie=True)
    url = reverse("garage:checklists")

    reponse = client.get(url)
    assert len(reponse.context["checklists"]) == 2
    assert "Frein spongieux" in reponse.content.decode() and "Tout est OK" in reponse.content.decode()
    assert [c.pk for c in client.get(url, {"anomalies": "on"}).context["checklists"]] == [avec_ko.pk]
    assert len(client.get(url, {"q": avec_ko.mission.numero}).context["checklists"]) == 1


def test_le_menu_du_parc_auto_propose_les_incidents(client):
    _connecte(client, Role.PARCAUTO)

    assert 'href="/garage/incidents/"' in client.get(reverse("home")).content.decode()


def test_les_listes_du_terrain_sont_a_requetes_constantes(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(12):
        _incident()
        _checklist(anomalie=True)

    with django_assert_max_num_queries(12):
        assert client.get(reverse("garage:incidents")).status_code == 200
    with django_assert_max_num_queries(12):
        assert client.get(reverse("garage:checklists")).status_code == 200
```

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/garage/tests/test_views.py apps/garage/tests/test_views_terrain.py -q --no-cov
```

**Résultat attendu :** `64 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur :**

1. **`demo_parcauto`** : ouvrez la fiche du camion `1234 AB 01` : un bloc **Maintenance** est apparu (grâce au
   registre). Cliquez **Ouvrir un OR** : type Curatif, lieu interne, motif « Bruit au freinage ». Le camion passe
   **En maintenance**.
2. Ouvrez l'OR : le bloc « Pièces utilisées » **n'existe pas encore** (il viendra avec le stock, chapitre 23).
   **Clôturez** l'OR avec 45 000 de main-d'œuvre : le camion redevient **Disponible**.
3. **Immobilisez** le camion (confirmation) : statut **Immobilisé** ; « Remettre en service » le repasse Disponible.
4. **`demo_direction`** : le bloc Maintenance est visible mais **sans boutons** (lecture seule).

## Ce qu'il faut retenir

- Un fichier de gabarit **suffit** à activer un bloc pour une autre app : le couplage est dans les registres,
  pas dans les imports.
- On peut **scinder** vues et formulaires en plusieurs fichiers quand un module a deux visages (gestion / terrain).

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 22 : écrans du garage (OR, incidents, check-lists, bloc maintenance)"
```

---

[← Chapitre 21](21-ecrans-missions.md) · [Sommaire](README.md) · [Chapitre 23 →](23-ecrans-stock.md)
