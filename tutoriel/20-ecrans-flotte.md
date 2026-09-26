# Chapitre 20 — Écrans : flotte

> 8 fichier(s) dans ce chapitre, 1166 lignes de code.

## Ce que vous allez construire

Les **écrans de la flotte**, accessibles à l'ADMIN, à la DIRECTION et au PARCAUTO.

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des camions | `/flotte/` | filtrer par statut, texte, « documents à renouveler » |
| Fiche d'un camion | `/flotte/<id>/` | caractéristiques, **état des 4 documents**, statut, blocs fournis par d'autres apps |
| Créer / modifier | `/flotte/nouveau/`, `/flotte/<id>/modifier/` | fiche du camion |
| Enregistrer / renouveler un document | `/flotte/<id>/document/` (POST) | carte grise, assurance, visite technique, patente |

Le **statut** est affiché mais **jamais modifiable** dans un formulaire : il se calcule (chapitre 8).

## Prérequis

- Chapitres 1 à 19 terminés.

## Ce que ce chapitre apporte de nouveau

- **Une fiche qui héberge des blocs** : `sections=sections.DETAIL_VEHICULE.sections(self.object, self.request.user)`
  dans la vue, `{% for section in sections %}{% include section.template %}{% endfor %}` dans le gabarit. Le bloc
  « Maintenance » de `garage` s'y affichera dès le chapitre 22, **sans qu'une ligne de `fleet` ne change**.
- **Un formulaire à deux visages** : `VehiculeForm` sert à la création et à la modification ; le service refuse un
  compteur qui reculerait.
- **Un formulaire secondaire sur une fiche** (`DocumentForm`) qui poste vers une vue dédiée.

## Étape 1 — Formulaires, vues, adresses

#### `apps/fleet/forms.py`

*49 lignes*

```python
from datetime import date

from django import forms
from django.core.validators import MaxValueValidator

from apps.core.forms import StyleTailwindMixin
from apps.drivers import services as drivers_services

from .models import TypeDocument


class VehiculeForm(StyleTailwindMixin, forms.Form):
    """Fiche véhicule (cahier-des-charges.md:88-90)."""

    immatriculation = forms.CharField(label="Immatriculation", max_length=20)
    marque = forms.CharField(label="Marque", max_length=50)
    modele = forms.CharField(label="Modèle", max_length=50)
    annee = forms.IntegerField(label="Année", min_value=1950)
    vin = forms.CharField(label="N° de châssis (VIN)", max_length=17)
    kilometrage = forms.IntegerField(label="Kilométrage du compteur", min_value=0, initial=0)
    capacite_charge_t = forms.DecimalField(
        label="Capacité de charge (tonnes)", min_value=0, decimal_places=2, max_digits=6
    )
    reservoir_l = forms.IntegerField(label="Réservoir (litres)", min_value=1)
    chauffeur_habituel = forms.ModelChoiceField(
        label="Chauffeur habituel", queryset=None, required=False, empty_label="Aucun"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        annee_max = date.today().year + 1
        self.fields["annee"].validators.append(MaxValueValidator(annee_max))
        self.fields["annee"].widget.attrs["max"] = annee_max
        self.fields["chauffeur_habituel"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur_habituel"].label_from_instance = lambda c: (
            f"{c.personnel.prenom} {c.personnel.nom} ({c.personnel.matricule})"
        )


class DocumentForm(StyleTailwindMixin, forms.Form):
    """Enregistrement ou renouvellement d'un document réglementaire."""

    type_document = forms.ChoiceField(label="Document", choices=TypeDocument.choices)
    date_delivrance = forms.DateField(
        label="Date de délivrance", widget=forms.DateInput(attrs={"type": "date"})
    )
    date_expiration = forms.DateField(
        label="Date d'expiration", widget=forms.DateInput(attrs={"type": "date"})
    )
```

#### `apps/fleet/views.py`

*189 lignes* — Écrans de la flotte : liste, fiche, création, modification, documents.

```python
"""Écrans de la flotte : liste, fiche, création, modification, documents.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, sections, services
from .exceptions import FlotteError
from .forms import DocumentForm, VehiculeForm
from .models import StatutVehicule, TypeDocument


class VehiculeListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "fleet/vehicule_list.html"
    context_object_name = "vehicules"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_vehicules(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
            documents_a_renouveler=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutVehicule.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            alerte=self.request.GET.get("alerte") == "1",
            vehicules_en_alerte=services.vehicules_avec_documents_a_renouveler(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class VehiculeImprimerView(ImpressionListeMixin, VehiculeListView):
    """Rapport imprimable des camions (mêmes recherche, statut et alerte que la liste)."""

    titre_impression = "Flotte"
    colonnes = (
        ("Immatriculation", "immatriculation"), ("Marque", "marque"), ("Modèle", "modele"),
        ("Année", "annee"), ("Statut", "get_statut_display"), ("Kilométrage", lambda v: f"{v.kilometrage:,} km".replace(",", " ")),
        ("Chauffeur habituel", lambda v: f"{v.chauffeur_habituel.prenom} {v.chauffeur_habituel.nom}" if v.chauffeur_habituel_id else "—"),
    )

    def get_sous_titre_impression(self):
        morceaux = []
        statut = self.request.GET.get("statut", "")
        if statut in StatutVehicule.values:
            morceaux.append(f"statut : {StatutVehicule(statut).label}")
        if self.request.GET.get("alerte") == "1":
            morceaux.append("documents à renouveler")
        if self.request.GET.get("q", ""):
            morceaux.append(f"recherche : « {self.request.GET['q']} »")
        return " · ".join(morceaux)


class VehiculeDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "fleet/vehicule_detail.html"
    context_object_name = "vehicule"

    def get_queryset(self):
        return services.vehicules_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        type_choisi = self.request.GET.get("document")
        contexte.update(
            documents=services.etat_documents(self.object),
            sections=sections.DETAIL_VEHICULE.sections(self.object, self.request.user),
            peut_modifier=peut_modifier,
            form_document=(
                DocumentForm(
                    initial={
                        "type_document": type_choisi
                        if type_choisi in TypeDocument.values
                        else None
                    }
                )
                if peut_modifier
                else None
            ),
        )
        return contexte


class VehiculeCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = VehiculeForm
    template_name = "fleet/vehicule_form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(titre="Nouveau camion", bouton="Créer le camion")
        return contexte

    def form_valid(self, form):
        try:
            vehicule = services.creer_vehicule(**form.cleaned_data)
        except FlotteError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Camion {vehicule.immatriculation} créé.")
        return redirect("fleet:detail", pk=vehicule.pk)


class VehiculeUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = VehiculeForm
    template_name = "fleet/vehicule_form.html"

    @property
    def vehicule(self):
        if not hasattr(self, "_vehicule"):
            self._vehicule = get_object_or_404(
                services.vehicules_queryset(), pk=self.kwargs["pk"]
            )
        return self._vehicule

    def get_initial(self):
        v = self.vehicule
        return {
            "immatriculation": v.immatriculation,
            "marque": v.marque,
            "modele": v.modele,
            "annee": v.annee,
            "vin": v.vin,
            "kilometrage": v.kilometrage,
            "capacite_charge_t": v.capacite_charge_t,
            "reservoir_l": v.reservoir_l,
            "chauffeur_habituel": v.chauffeur_habituel,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            titre=f"Modifier {self.vehicule.immatriculation}",
            bouton="Enregistrer",
            vehicule=self.vehicule,
        )
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_vehicule(self.vehicule, **form.cleaned_data)
        except FlotteError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Camion {self.vehicule.immatriculation} mis à jour.")
        return redirect("fleet:detail", pk=self.vehicule.pk)


class DocumentView(RoleRequiredMixin, View):
    """Enregistre ou renouvelle un document réglementaire (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        vehicule = get_object_or_404(services.vehicules_queryset(), pk=pk)
        form = DocumentForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("fleet:detail", pk=vehicule.pk)
        try:
            document, cree = services.enregistrer_document(vehicule, **form.cleaned_data)
        except FlotteError as erreur:
            messages.error(request, str(erreur))
        else:
            action = "enregistré" if cree else "renouvelé"
            messages.success(
                request, f"{document.get_type_document_display()} {action}."
            )
        return redirect("fleet:detail", pk=vehicule.pk)
```

#### `apps/fleet/urls.py`

*14 lignes*

```python
from django.urls import path

from . import views

app_name = "fleet"

urlpatterns = [
    path("", views.VehiculeListView.as_view(), name="liste"),
    path("imprimer/", views.VehiculeImprimerView.as_view(), name="imprimer"),
    path("nouveau/", views.VehiculeCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.VehiculeDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.VehiculeUpdateView.as_view(), name="modifier"),
    path("<int:pk>/document/", views.DocumentView.as_view(), name="document"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -18,4 +18,5 @@
     path("", include("apps.accounts.urls")),
     path("clients/", include("apps.customers.urls")),
+    path("flotte/", include("apps.fleet.urls")),
     path("rh/", include("apps.hr.urls")),
     path("chauffeurs/", include("apps.drivers.urls")),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/fleet/templates/fleet
```

#### `apps/fleet/templates/fleet/vehicule_list.html`

*101 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Flotte{% endblock %}
{% block entete %}Flotte{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Flotte</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} camion{{ paginator.count|pluralize }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'fleet:imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_modifier %}
        <a href="{% url 'fleet:creer' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouveau camion
        </a>
      {% endif %}
    </div>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="Immatriculation, marque, modèle, VIN…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="statut" class="block text-sm font-medium text-slate-800">Statut</label>
      <select id="statut" name="statut"
              class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous les statuts</option>
        {% for code, libelle in statuts %}
          <option value="{{ code }}" {% if code == statut_choisi %}selected{% endif %}>{{ libelle }}</option>
        {% endfor %}
      </select>
    </div>
    <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
      <input type="checkbox" name="alerte" value="1" {% if alerte %}checked{% endif %}
             class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
      Documents à renouveler
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or statut_choisi or alerte %}
      <a href="{% url 'fleet:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if vehicules %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des camions</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Immatriculation</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3 text-right">Année</th>
            <th scope="col" class="px-4 py-3">Chauffeur habituel</th>
            <th scope="col" class="px-4 py-3 text-right">Kilométrage</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="px-4 py-3">Documents</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for vehicule in vehicules %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'fleet:detail' vehicule.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ vehicule.immatriculation }}</a>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-800">{{ vehicule.marque }} {{ vehicule.modele }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ vehicule.annee }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{% if vehicule.chauffeur_habituel %}{{ vehicule.chauffeur_habituel.personnel.prenom }} {{ vehicule.chauffeur_habituel.personnel.nom }}{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ vehicule.kilometrage|intcomma }} km</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge vehicule.statut vehicule.get_statut_display %}</td>
              <td class="whitespace-nowrap px-4 py-3">
                {% if vehicule.pk in vehicules_en_alerte %}{% badge "A_RENOUVELER" "À renouveler" %}{% else %}<span class="text-slate-600">À jour</span>{% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <i class="fa-solid fa-truck" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucun camion trouvé</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or statut_choisi or alerte %}Aucun résultat pour ces critères.{% else %}Les camions enregistrés apparaîtront ici.{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/fleet/templates/fleet/vehicule_detail.html`

*103 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}{{ vehicule.immatriculation }}{% endblock %}
{% block entete %}Flotte{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'fleet:liste' %}" class="underline-offset-2 hover:underline">Flotte</a>
    <span aria-hidden="true">/</span> {{ vehicule.immatriculation }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{{ vehicule.immatriculation }}</h1>
      {% badge vehicule.statut vehicule.get_statut_display %}
    </div>
    {% if peut_modifier %}
      <a href="{% url 'fleet:modifier' vehicule.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ vehicule.marque }} {{ vehicule.modele }} · {{ vehicule.annee }}</p>

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1" aria-labelledby="titre-fiche">
      <h2 id="titre-fiche" class="text-base font-semibold text-slate-900">Caractéristiques</h2>
      <dl class="mt-4 space-y-3 text-sm">
        <div><dt class="text-slate-600">N° de châssis (VIN)</dt><dd class="mt-0.5 break-all font-medium text-slate-900">{{ vehicule.vin }}</dd></div>
        <div><dt class="text-slate-600">Kilométrage</dt><dd class="mt-0.5 font-medium text-slate-900">{{ vehicule.kilometrage|intcomma }} km</dd></div>
        <div><dt class="text-slate-600">Capacité de charge</dt><dd class="mt-0.5 font-medium text-slate-900">{{ vehicule.capacite_charge_t|floatformat:"-2" }} t</dd></div>
        <div><dt class="text-slate-600">Réservoir</dt><dd class="mt-0.5 font-medium text-slate-900">{{ vehicule.reservoir_l }} L</dd></div>
        <div><dt class="text-slate-600">Chauffeur habituel</dt>
          <dd class="mt-0.5 font-medium text-slate-900">{% if vehicule.chauffeur_habituel %}{{ vehicule.chauffeur_habituel.personnel.prenom }} {{ vehicule.chauffeur_habituel.personnel.nom }}{% else %}Aucun{% endif %}</dd></div>
      </dl>
    </section>

    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-documents">
        <h2 id="titre-documents" class="text-base font-semibold text-slate-900">Documents réglementaires</h2>
        <p class="mt-1 text-xs text-slate-600">Une alerte apparaît 30 jours avant l'expiration.</p>
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <caption class="sr-only">Documents réglementaires du camion</caption>
            <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th scope="col" class="py-2 pr-4">Document</th>
                <th scope="col" class="px-4 py-2">Délivré le</th>
                <th scope="col" class="px-4 py-2">Expire le</th>
                <th scope="col" class="px-4 py-2">État</th>
                {% if peut_modifier %}<th scope="col" class="py-2 pl-4"><span class="sr-only">Action</span></th>{% endif %}
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              {% for d in documents %}
                <tr>
                  <th scope="row" class="whitespace-nowrap py-3 pr-4 text-left font-medium text-slate-900">{{ d.libelle }}</th>
                  <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.document.date_delivrance|date:"d/m/Y"|default:"—" }}</td>
                  <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.document.date_expiration|date:"d/m/Y"|default:"—" }}</td>
                  <td class="whitespace-nowrap px-4 py-3">
                    {% if d.etat == "EXPIRE" %}{% badge d.etat "Expiré" %}<span class="ml-2 text-xs text-slate-600">depuis {% widthratio d.jours_restants 1 -1 %} j</span>
                    {% elif d.etat == "A_RENOUVELER" %}{% badge d.etat "À renouveler" %}<span class="ml-2 text-xs text-slate-600">dans {{ d.jours_restants }} j</span>
                    {% elif d.etat == "VALIDE" %}{% badge d.etat "Valide" %}
                    {% else %}{% badge d.etat "Non enregistré" %}{% endif %}
                  </td>
                  {% if peut_modifier %}
                    <td class="whitespace-nowrap py-3 pl-4 text-right">
                      <a href="?document={{ d.code }}#nouveau-document" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">
                        {% if d.document %}Renouveler{% else %}Enregistrer{% endif %}<span class="sr-only"> {{ d.libelle }}</span>
                      </a>
                    </td>
                  {% endif %}
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      {% if form_document %}
        <section id="nouveau-document" class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-form-document">
          <h2 id="titre-form-document" class="text-base font-semibold text-slate-900">Enregistrer ou renouveler un document</h2>
          <p class="mt-1 text-xs text-slate-600">Un renouvellement remplace les dates ; les anciennes restent dans le journal d'audit.</p>
          <form method="post" action="{% url 'fleet:document' vehicule.pk %}" class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_document.type_document %}
            {% include "components/_champ.html" with champ=form_document.date_delivrance %}
            {% include "components/_champ.html" with champ=form_document.date_expiration %}
            <div class="sm:col-span-3 flex justify-end">
              <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer le document</button>
            </div>
          </form>
        </section>
      {% endif %}

      {# Blocs ajoutés par d'autres apps (ex. maintenance du garage) #}
      {% for section in sections %}{% include section.template %}{% endfor %}
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/fleet/templates/fleet/vehicule_form.html`

*45 lignes*

```django
{% extends "base.html" %}
{% block titre %}{{ titre }}{% endblock %}
{% block entete %}Flotte{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'fleet:liste' %}" class="underline-offset-2 hover:underline">Flotte</a>
    {% if vehicule %}<span aria-hidden="true">/</span> <a href="{% url 'fleet:detail' vehicule.pk %}" class="underline-offset-2 hover:underline">{{ vehicule.immatriculation }}</a>{% endif %}
    <span aria-hidden="true">/</span> {% if vehicule %}Modifier{% else %}Nouveau camion{% endif %}
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">{{ titre }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    Le statut du camion n'est pas saisi ici : il se calcule à partir des missions et des ordres de réparation.
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.immatriculation %}
      {% include "components/_champ.html" with champ=form.vin %}
      {% include "components/_champ.html" with champ=form.marque %}
      {% include "components/_champ.html" with champ=form.modele %}
      {% include "components/_champ.html" with champ=form.annee %}
      {% include "components/_champ.html" with champ=form.kilometrage %}
      {% include "components/_champ.html" with champ=form.capacite_charge_t %}
      {% include "components/_champ.html" with champ=form.reservoir_l %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.chauffeur_habituel %}</div>
    </div>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% if vehicule %}{% url 'fleet:detail' vehicule.pk %}{% else %}{% url 'fleet:liste' %}{% endif %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        {{ bouton }}
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

## Étape 3 — Tests et compilation des styles

#### `apps/fleet/tests/test_views.py`

*433 lignes* — Écrans de la flotte : accès par rôle, liste, fiche, création, documents.

```python
"""Écrans de la flotte : accès par rôle, liste, fiche, création, documents."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees_formulaire(**surcharges):
    donnees = {
        "immatriculation": "4321 CD 01",
        "marque": "Renault",
        "modele": "T480",
        "annee": "2022",
        "vin": "VF6T480000000001A",
        "kilometrage": "12000",
        "capacite_charge_t": "26.5",
        "reservoir_l": "700",
        "chauffeur_habituel": "",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_la_flotte_est_accessible_aux_roles_du_parc_auto(client, role):
    _connecte(client, role)

    assert client.get(reverse("fleet:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_la_flotte_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)
    camion = VehiculeFactory()

    assert client.get(reverse("fleet:liste")).status_code == 403
    assert client.get(reverse("fleet:detail", args=[camion.pk])).status_code == 403
    assert client.get(reverse("fleet:creer")).status_code == 403
    assert client.post(reverse("fleet:modifier", args=[camion.pk]), {}).status_code == 403
    assert client.post(reverse("fleet:document", args=[camion.pk]), {}).status_code == 403


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("fleet:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_flotte_est_visible_du_parc_auto_seulement(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/flotte/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.FINANCES)
    assert 'href="/flotte/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_camions(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(immatriculation="7777 GH 01", marque="DAF", modele="XF")

    contenu = client.get(reverse("fleet:liste")).content.decode()

    assert "7777 GH 01" in contenu and "DAF XF" in contenu
    assert "Disponible" in contenu
    assert reverse("fleet:detail", args=[camion.pk]) in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun camion trouvé" in client.get(reverse("fleet:liste")).content.decode()


def test_la_liste_filtre_par_statut_et_recherche(client):
    _connecte(client, Role.DIRECTION)
    libre = VehiculeFactory(immatriculation="1000 AA 01", marque="Volvo")
    VehiculeFactory(immatriculation="2000 BB 01", statut=StatutVehicule.EN_MISSION)

    par_statut = client.get(reverse("fleet:liste"), {"statut": "DISPONIBLE"})
    par_texte = client.get(reverse("fleet:liste"), {"q": "volvo"})

    assert list(par_statut.context["vehicules"]) == [libre]
    assert list(par_texte.context["vehicules"]) == [libre]


def test_la_liste_signale_les_documents_a_renouveler_et_filtre_dessus(client):
    _connecte(client, Role.PARCAUTO)
    aujourdhui = timezone.localdate()
    alerte = VehiculeFactory(immatriculation="1111 AA 01")
    DocumentReglementaireFactory(
        vehicule=alerte,
        date_delivrance=aujourdhui - timedelta(days=300),
        date_expiration=aujourdhui + timedelta(days=10),
    )
    VehiculeFactory(immatriculation="2222 BB 01")

    complet = client.get(reverse("fleet:liste"))
    filtre = client.get(reverse("fleet:liste"), {"alerte": "1"})

    assert "À renouveler" in complet.content.decode()
    assert list(filtre.context["vehicules"]) == [alerte]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        VehiculeFactory()

    page2 = client.get(reverse("fleet:liste"), {"page": 2})

    assert len(page2.context["vehicules"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_camion(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        VehiculeFactory(chauffeur_habituel=ChauffeurFactory())

    with django_assert_max_num_queries(10):
        client.get(reverse("fleet:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    VehiculeFactory(marque="<script>alert(1)</script>")

    contenu = client.get(reverse("fleet:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_les_caracteristiques_et_le_chauffeur_habituel(client):
    _connecte(client, Role.PARCAUTO)
    chauffeur = ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa")
    camion = VehiculeFactory(kilometrage=123456, chauffeur_habituel=chauffeur)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert camion.vin in contenu
    assert "Moussa Traoré" in contenu
    assert "123" in contenu and "456" in contenu  # séparateur de milliers selon la locale


def test_la_fiche_d_un_camion_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("fleet:detail", args=[999999])).status_code == 404


def test_la_fiche_montre_les_4_documents_avec_leur_etat(client):
    _connecte(client, Role.PARCAUTO)
    aujourdhui = timezone.localdate()
    camion = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=aujourdhui - timedelta(days=400),
        date_expiration=aujourdhui - timedelta(days=5),
    )
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.PATENTE,
        date_delivrance=aujourdhui - timedelta(days=100),
        date_expiration=aujourdhui + timedelta(days=12),
    )

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]))
    contenu = reponse.content.decode()

    etats = {d["code"]: d["etat"] for d in reponse.context["documents"]}
    assert etats == {
        "CARTE_GRISE": "MANQUANT",
        "ASSURANCE": "EXPIRE",
        "VISITE_TECHNIQUE": "MANQUANT",
        "PATENTE": "A_RENOUVELER",
    }
    assert "Expiré" in contenu and "depuis 5 j" in contenu
    assert "dans 12 j" in contenu
    assert "Non enregistré" in contenu


def test_le_formulaire_de_document_est_prerempli_par_le_lien_renouveler(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]), {"document": "PATENTE"})

    assert reponse.context["form_document"].initial["type_document"] == "PATENTE"


def test_un_type_de_document_inconnu_dans_l_url_est_ignore(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]), {"document": "<x>"})

    assert reponse.context["form_document"].initial["type_document"] is None


# --- création ---


def test_le_formulaire_de_creation_s_affiche(client):
    _connecte(client, Role.DIRECTION)

    reponse = client.get(reverse("fleet:creer"))

    assert reponse.status_code == 200
    assert "Nouveau camion" in reponse.content.decode()


def test_creer_un_camion_valide(client):
    _connecte(client, Role.PARCAUTO)
    chauffeur = ChauffeurFactory()

    reponse = client.post(
        reverse("fleet:creer"),
        _donnees_formulaire(chauffeur_habituel=chauffeur.pk),
        follow=True,
    )

    camion = Vehicule.objects.get()
    assert reponse.redirect_chain[-1][0] == reverse("fleet:detail", args=[camion.pk])
    assert (camion.immatriculation, camion.capacite_charge_t) == ("4321 CD 01", Decimal("26.50"))
    assert camion.chauffeur_habituel == chauffeur
    assert any("4321 CD 01" in m for m in _messages(reponse))


def test_creer_un_doublon_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.PARCAUTO)
    VehiculeFactory(immatriculation="4321 CD 01")

    reponse = client.post(reverse("fleet:creer"), _donnees_formulaire())

    assert reponse.status_code == 200
    assert "déjà utilisée" in reponse.content.decode()
    assert Vehicule.objects.count() == 1


@pytest.mark.parametrize(
    "champ", [{"annee": "1900"}, {"annee": "2999"}, {"reservoir_l": "0"}, {"kilometrage": "-1"}, {"marque": ""}]
)
def test_creer_avec_des_donnees_invalides_est_refuse_par_le_formulaire(client, champ):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("fleet:creer"), _donnees_formulaire(**champ))

    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert Vehicule.objects.count() == 0


def test_le_choix_du_chauffeur_habituel_exclut_les_inactifs(client):
    from apps.drivers.models import StatutChauffeur

    _connecte(client, Role.PARCAUTO)
    actif = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    reponse = client.get(reverse("fleet:creer"))

    assert list(reponse.context["form"].fields["chauffeur_habituel"].queryset) == [actif]


# --- modification ---


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(immatriculation="8888 KL 01", kilometrage=4000)

    reponse = client.get(reverse("fleet:modifier", args=[camion.pk]))

    assert reponse.context["form"].initial["immatriculation"] == "8888 KL 01"
    assert reponse.context["form"].initial["kilometrage"] == 4000


def test_modifier_un_camion(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(kilometrage=1000)

    client.post(
        reverse("fleet:modifier", args=[camion.pk]),
        _donnees_formulaire(marque="Volvo", kilometrage="1500"),
    )

    camion.refresh_from_db()
    assert (camion.marque, camion.kilometrage) == ("Volvo", 1500)


def test_modifier_avec_un_compteur_en_recul_affiche_l_erreur(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(kilometrage=9000)

    reponse = client.post(
        reverse("fleet:modifier", args=[camion.pk]), _donnees_formulaire(kilometrage="8000")
    )

    camion.refresh_from_db()
    assert camion.kilometrage == 9000
    assert "ne peut pas diminuer" in reponse.content.decode()


def test_modifier_un_camion_inconnu_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("fleet:modifier", args=[999999])).status_code == 404


# --- documents ---


def test_enregistrer_un_document_par_l_ecran(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "ASSURANCE",
            "date_delivrance": "2026-01-01",
            "date_expiration": "2027-01-01",
        },
        follow=True,
    )

    document = DocumentReglementaire.objects.get(vehicule=camion)
    assert str(document.date_expiration) == "2027-01-01"
    assert "Assurance enregistré." in _messages(reponse)


def test_renouveler_un_document_par_l_ecran(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ancien = DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=date(2026, 1, 1),
    )

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "ASSURANCE",
            "date_delivrance": "2026-01-01",
            "date_expiration": "2027-01-01",
        },
        follow=True,
    )

    ancien.refresh_from_db()
    assert str(ancien.date_expiration) == "2027-01-01"
    assert "Assurance renouvelé." in _messages(reponse)


def test_un_document_avec_des_dates_incoherentes_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "PATENTE",
            "date_delivrance": "2026-05-01",
            "date_expiration": "2026-04-01",
        },
        follow=True,
    )

    assert DocumentReglementaire.objects.count() == 0
    assert any("précéder" in m for m in _messages(reponse))


def test_un_document_incomplet_est_refuse_par_le_formulaire(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    client.post(reverse("fleet:document", args=[camion.pk]), {"type_document": "PATENTE"})

    assert DocumentReglementaire.objects.count() == 0


def test_l_enregistrement_d_un_document_refuse_le_get(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    assert client.get(reverse("fleet:document", args=[camion.pk])).status_code == 405


def test_les_formulaires_de_la_flotte_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert client.post(reverse("fleet:creer"), _donnees_formulaire()).status_code == 403
    assert Vehicule.objects.count() == 0
```

#### `apps/notifications/tests/test_taches.py`

*224 lignes* — Tâches quotidiennes : alertes d'échéances, rappels de validation, statuts des congés.

```python
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


def test_executer_taches_quotidiennes_expire_les_devis_envoyes_au_client():
    from apps.billing.tests.helpers import proforma_envoyee

    proforma_envoyee(aujourd_hui=AUJOURD_HUI)

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=AUJOURD_HUI + timedelta(days=31))

    assert resultat["proformas_expirees"] == 1


def test_la_commande_affiche_les_compteurs_et_est_rejouable():
    UserFactory(role=Role.PARCAUTO)
    DocumentReglementaireFactory(date_expiration=date.today() + timedelta(days=2))

    premiere, seconde = StringIO(), StringIO()
    call_command("taches_quotidiennes", stdout=premiere)
    call_command("taches_quotidiennes", stdout=seconde)

    assert re.search(r"documents vehicules\s+1", premiere.getvalue())
    assert re.search(r"documents vehicules\s+0", seconde.getvalue())
```

Le fichier `apps/notifications/tests/test_taches.py` teste les alertes du jour (documents à 30 jours…) : il a
besoin de la fiche d'un camion avec ses documents, donc de ces écrans.

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
python -m pytest apps/fleet/tests/test_views.py apps/notifications/tests/test_taches.py -q --no-cov
```

**Résultat attendu :** `53 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur :**

1. Connectez-vous avec **`demo_parcauto`** : le menu affiche **Flotte**. Le camion `1234 AB 01` (créé par
   l'essai du chapitre 8) apparaît. Si vous n'en avez pas, créez-en un : « Nouveau camion ».
2. Ouvrez sa fiche : les quatre documents sont **Manquants**. Enregistrez une **assurance expirant dans 15 jours**
   : elle passe à **À renouveler**, et la case « documents à renouveler » de la liste retrouve le camion.
3. Renouvelez-la avec une date lointaine : elle redevient **Valide**.
4. Remettez l'assurance à 15 jours, puis lancez `python manage.py taches_quotidiennes` : la ligne
   `documents vehicules` vaut `1` (une alerte est créée pour le Parc Auto). Relancez la commande : elle vaut `0`
   (**aucune alerte en double**). La cloche de `demo_parcauto` affiche l'alerte.

## Ce qu'il faut retenir

- Un registre permet à une fiche d'afficher des blocs d'un module **qu'elle ne connaît pas**.
- Une donnée **calculée** (le statut) s'affiche mais ne se saisit pas.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 20 : écrans de la flotte (camions et documents réglementaires)"
```

---

[← Chapitre 19](19-ecrans-clients.md) · [Sommaire](README.md) · [Chapitre 21 →](21-ecrans-missions.md)
