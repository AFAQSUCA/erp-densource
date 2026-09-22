# Chapitre 18 — Écrans : chauffeurs

> 7 fichier(s) dans ce chapitre, 785 lignes de code.

## Ce que vous allez construire

Les **écrans des chauffeurs**, réservés à l'ADMIN, à la DIRECTION et à la RH.

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste | `/chauffeurs/` | filtrer par statut, par texte, ou par « permis / visite à renouveler » |
| Fiche | `/chauffeurs/<id>/` | voir l'état du **permis** et de la **visite médicale** (alerte à 30 jours), le statut, les congés |
| Modifier | `/chauffeurs/<id>/modifier/` | téléphone, contact d'urgence, permis, catégories, dates d'expiration |
| Changer le statut | `/chauffeurs/<id>/statut/` (POST) | **suspendre**, **désactiver** ou **réactiver** |

Deux règles à retrouver dans l'interface : « En mission » et « En congé » **ne se choisissent pas à la main**
(le système les pose), et le matricule, le nom et le prénom **ne se modifient pas ici** (ils viennent de la
fiche du personnel).

## Prérequis

- Chapitres 1 à 17 terminés.

## Ce que ce chapitre réutilise

Rien de nouveau côté technique : les **quatre motifs** du chapitre 17 (liste, fiche, formulaire, action POST).
Regardez comment ils s'appliquent ici :

- `ChauffeurListView` : liste filtrée, en appelant `services.rechercher_chauffeurs`.
- `ChauffeurDetailView` : `services.etat_echeances` calcule l'état du permis et de la visite.
- `ChauffeurUpdateView` : formulaire qui appelle `services.modifier_chauffeur`.
- `StatutView` : **action POST** qui appelle `services.changer_statut_manuel` ; son formulaire de confirmation
  porte `data-confirm`.

## Étape 1 — Formulaires, vues, adresses

#### `apps/drivers/forms.py`

*53 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import CategoriePermis, StatutChauffeur


class ChauffeurForm(StyleTailwindMixin, forms.Form):
    """Informations propres au chauffeur (cahier-des-charges.md:109-111).

    Matricule, nom et prénom viennent de la fiche du personnel : ils ne sont pas
    modifiables ici.
    """

    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)
    contact_urgence = forms.CharField(label="Contact d'urgence", max_length=150, required=False)
    numero_permis = forms.CharField(label="N° de permis", max_length=50, required=False)
    categories_permis = forms.MultipleChoiceField(
        label="Catégories de permis",
        choices=CategoriePermis.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    date_expiration_permis = forms.DateField(
        label="Expiration du permis",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_expiration_visite_medicale = forms.DateField(
        label="Expiration de la visite médicale",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories_permis"].widget.attrs["class"] = (
            "h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600"
        )


class StatutForm(StyleTailwindMixin, forms.Form):
    """Statuts qui se posent à la main (les autres viennent des missions et congés)."""

    statut = forms.ChoiceField(
        label="Nouveau statut",
        choices=[
            (code, libelle)
            for code, libelle in StatutChauffeur.choices
            if code in services.STATUTS_MANUELS
        ],
    )
```

#### `apps/drivers/views.py`

*133 lignes* — Écrans des chauffeurs : liste, fiche, modification, changement de statut.

```python
"""Écrans des chauffeurs : liste, fiche, modification, changement de statut.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import ChauffeurError
from .forms import ChauffeurForm, StatutForm
from .models import StatutChauffeur


class ChauffeurListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "drivers/chauffeur_list.html"
    context_object_name = "chauffeurs"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_chauffeurs(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
            a_renouveler=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutChauffeur.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            alerte=self.request.GET.get("alerte") == "1",
            lignes=[
                {"chauffeur": c, "echeances": services.etat_echeances(c)}
                for c in contexte["page_obj"]
            ],
        )
        return contexte


class ChauffeurDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "drivers/chauffeur_detail.html"
    context_object_name = "chauffeur"

    def get_queryset(self):
        return services.chauffeurs_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        chauffeur = self.object
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            echeances=services.etat_echeances(chauffeur),
            peut_modifier=peut_modifier,
            statut_verrouille=chauffeur.statut in services.STATUTS_VERROUILLES,
            form_statut=StatutForm(initial={"statut": chauffeur.statut})
            if peut_modifier
            else None,
        )
        return contexte


class ChauffeurUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ChauffeurForm
    template_name = "drivers/chauffeur_form.html"

    @property
    def chauffeur(self):
        if not hasattr(self, "_chauffeur"):
            self._chauffeur = get_object_or_404(
                services.chauffeurs_queryset(), pk=self.kwargs["pk"]
            )
        return self._chauffeur

    def get_initial(self):
        c = self.chauffeur
        return {
            "telephone": c.telephone,
            "contact_urgence": c.contact_urgence,
            "numero_permis": c.numero_permis,
            "categories_permis": c.categories_permis,
            "date_expiration_permis": c.date_expiration_permis,
            "date_expiration_visite_medicale": c.date_expiration_visite_medicale,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["chauffeur"] = self.chauffeur
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_chauffeur(self.chauffeur, **form.cleaned_data)
        except ChauffeurError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de {self.chauffeur} mise à jour.")
        return redirect("drivers:detail", pk=self.chauffeur.pk)


class StatutView(RoleRequiredMixin, View):
    """Suspend, désactive ou réactive un chauffeur (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        chauffeur = get_object_or_404(services.chauffeurs_queryset(), pk=pk)
        form = StatutForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("drivers:detail", pk=chauffeur.pk)
        try:
            services.changer_statut_manuel(chauffeur, form.cleaned_data["statut"])
        except ChauffeurError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{chauffeur} est maintenant « {chauffeur.get_statut_display()} »."
            )
        return redirect("drivers:detail", pk=chauffeur.pk)
```

#### `apps/drivers/urls.py`

*12 lignes*

```python
from django.urls import path

from . import views

app_name = "drivers"

urlpatterns = [
    path("", views.ChauffeurListView.as_view(), name="liste"),
    path("<int:pk>/", views.ChauffeurDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ChauffeurUpdateView.as_view(), name="modifier"),
    path("<int:pk>/statut/", views.StatutView.as_view(), name="statut"),
]
```

Montez les adresses :

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -17,4 +17,5 @@
     path("", include("apps.accounts.urls")),
     path("rh/", include("apps.hr.urls")),
+    path("chauffeurs/", include("apps.drivers.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/drivers/templates/drivers
```

#### `apps/drivers/templates/drivers/chauffeur_list.html`

*94 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Chauffeurs{% endblock %}
{% block entete %}Chauffeurs{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div>
    <h1 class="text-2xl font-bold text-slate-900">Chauffeurs</h1>
    <p class="mt-1 text-sm text-slate-600">
      {{ paginator.count|default:0 }} chauffeur{{ paginator.count|pluralize }}
      · les fiches sont créées automatiquement pour les employés au poste « Chauffeur ».
    </p>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="Nom, prénom, matricule, n° de permis…"
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
      Permis ou visite à renouveler
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or statut_choisi or alerte %}
      <a href="{% url 'drivers:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if lignes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des chauffeurs</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Matricule</th>
            <th scope="col" class="px-4 py-3">Chauffeur</th>
            <th scope="col" class="px-4 py-3">Téléphone</th>
            <th scope="col" class="px-4 py-3">Permis</th>
            <th scope="col" class="px-4 py-3">Visite médicale</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for ligne in lignes %}
            {% with c=ligne.chauffeur %}
              <tr class="hover:bg-slate-50">
                <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ c.personnel.matricule }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-semibold">
                  <a href="{% url 'drivers:detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ c.personnel.prenom }} {{ c.personnel.nom }}</a>
                </td>
                <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ c.telephone|default:"—" }}</td>
                {% for e in ligne.echeances %}
                  <td class="whitespace-nowrap px-4 py-3">
                    {% if e.etat == "VALIDE" %}<span class="text-slate-700">{{ e.date_expiration|date:"d/m/Y" }}</span>
                    {% elif e.etat == "MANQUANT" %}{% badge e.etat "Non renseigné" %}
                    {% elif e.etat == "EXPIRE" %}{% badge e.etat "Expiré" %}
                    {% else %}{% badge e.etat "À renouveler" %}{% endif %}
                  </td>
                {% endfor %}
                <td class="whitespace-nowrap px-4 py-3">{% badge c.statut c.get_statut_display %}</td>
              </tr>
            {% endwith %}
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <i class="fa-solid fa-id-card" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucun chauffeur trouvé</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or statut_choisi or alerte %}Aucun résultat pour ces critères.{% else %}Les chauffeurs apparaîtront ici dès qu'un employé sera recruté au poste « Chauffeur ».{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/drivers/templates/drivers/chauffeur_detail.html`

*94 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}{{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}{% endblock %}
{% block entete %}Chauffeurs{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'drivers:liste' %}" class="underline-offset-2 hover:underline">Chauffeurs</a>
    <span aria-hidden="true">/</span> {{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}</h1>
      {% badge chauffeur.statut chauffeur.get_statut_display %}
    </div>
    {% if peut_modifier %}
      <a href="{% url 'drivers:modifier' chauffeur.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">Matricule {{ chauffeur.personnel.matricule }}</p>

  <div class="mt-6 grid gap-6 xl:grid-cols-3">
    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1" aria-labelledby="titre-contact">
      <h2 id="titre-contact" class="text-base font-semibold text-slate-900">Contact</h2>
      <dl class="mt-4 space-y-3 text-sm">
        <div><dt class="text-slate-600">Téléphone</dt><dd class="mt-0.5 font-medium text-slate-900">{{ chauffeur.telephone|default:"Non renseigné" }}</dd></div>
        <div><dt class="text-slate-600">Contact d'urgence</dt><dd class="mt-0.5 font-medium text-slate-900">{{ chauffeur.contact_urgence|default:"Non renseigné" }}</dd></div>
      </dl>
    </section>

    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-permis">
        <h2 id="titre-permis" class="text-base font-semibold text-slate-900">Permis et visite médicale</h2>
        <p class="mt-1 text-xs text-slate-600">Une alerte apparaît 30 jours avant l'expiration.</p>
        <dl class="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">N° de permis</dt><dd class="mt-0.5 font-medium text-slate-900">{{ chauffeur.numero_permis|default:"Non renseigné" }}</dd></div>
          <div><dt class="text-slate-600">Catégories</dt><dd class="mt-0.5 font-medium text-slate-900">{% if chauffeur.categories_permis %}{{ chauffeur.categories_permis|join:", " }}{% else %}Non renseignées{% endif %}</dd></div>
        </dl>
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <caption class="sr-only">Échéances du chauffeur</caption>
            <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th scope="col" class="py-2 pr-4">Document</th>
                <th scope="col" class="px-4 py-2">Expire le</th>
                <th scope="col" class="px-4 py-2">État</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              {% for e in echeances %}
                <tr>
                  <th scope="row" class="whitespace-nowrap py-3 pr-4 text-left font-medium text-slate-900">{{ e.libelle }}</th>
                  <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.date_expiration|date:"d/m/Y"|default:"—" }}</td>
                  <td class="whitespace-nowrap px-4 py-3">
                    {% if e.etat == "EXPIRE" %}{% badge e.etat "Expiré" %}<span class="ml-2 text-xs text-slate-600">depuis {% widthratio e.jours_restants 1 -1 %} j</span>
                    {% elif e.etat == "A_RENOUVELER" %}{% badge e.etat "À renouveler" %}<span class="ml-2 text-xs text-slate-600">dans {{ e.jours_restants }} j</span>
                    {% elif e.etat == "VALIDE" %}{% badge e.etat "Valide" %}
                    {% else %}{% badge e.etat "Non renseigné" %}{% endif %}
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      {% if form_statut %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-statut">
          <h2 id="titre-statut" class="text-base font-semibold text-slate-900">Statut</h2>
          {% if statut_verrouille %}
            <p class="mt-3 text-sm text-slate-700">
              Ce chauffeur est « {{ chauffeur.get_statut_display }} » : ce statut est géré automatiquement par les
              missions et les congés et ne peut pas être modifié à la main.
            </p>
          {% else %}
            <p class="mt-1 text-xs text-slate-600">Suspendre ou désactiver un chauffeur le rend indisponible pour toute nouvelle mission.</p>
            <form method="post" action="{% url 'drivers:statut' chauffeur.pk %}" class="mt-4 flex flex-wrap items-end gap-3"
                  data-confirm="Changer le statut de ce chauffeur ?">
              {% csrf_token %}
              <div class="min-w-[12rem]">{% include "components/_champ.html" with champ=form_statut.statut %}</div>
              <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Appliquer</button>
            </form>
          {% endif %}
        </section>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/drivers/templates/drivers/chauffeur_form.html`

*50 lignes*

```django
{% extends "base.html" %}
{% block titre %}Modifier {{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}{% endblock %}
{% block entete %}Chauffeurs{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'drivers:liste' %}" class="underline-offset-2 hover:underline">Chauffeurs</a>
    <span aria-hidden="true">/</span>
    <a href="{% url 'drivers:detail' chauffeur.pk %}" class="underline-offset-2 hover:underline">{{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}</a>
    <span aria-hidden="true">/</span> Modifier
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Modifier {{ chauffeur.personnel.prenom }} {{ chauffeur.personnel.nom }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    Le matricule ({{ chauffeur.personnel.matricule }}), le nom et le prénom viennent de la fiche du personnel et ne se modifient pas ici.
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <fieldset>
      <legend class="text-sm font-semibold text-slate-900">Contact</legend>
      <div class="mt-3 grid gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.telephone %}
        {% include "components/_champ.html" with champ=form.contact_urgence %}
      </div>
    </fieldset>

    <fieldset class="border-t border-slate-100 pt-5">
      <legend class="text-sm font-semibold text-slate-900">Permis et visite médicale</legend>
      <div class="mt-3 grid gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.numero_permis %}
        {% include "components/_champ.html" with champ=form.categories_permis %}
        {% include "components/_champ.html" with champ=form.date_expiration_permis %}
        {% include "components/_champ.html" with champ=form.date_expiration_visite_medicale %}
      </div>
    </fieldset>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'drivers:detail' chauffeur.pk %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer</button>
    </div>
  </form>
</div>
{% endblock %}
```

## Étape 3 — Tests et compilation des styles

#### `apps/hr/tests/test_views_personnel.py`

*342 lignes* — Écrans du personnel : liste, fiche, recrutement, modification, jours exceptionnels.

```python
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
        "matricule": "MAT-5001",
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
    del donnees["matricule"], donnees["date_embauche"]
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

    employe = Personnel.objects.get(matricule="MAT-5001")
    assert employe.superieur == chef and employe.type_contrat == "CDI"
    assert reponse.redirect_chain[-1][0] == reverse("hr:personnel_detail", args=[employe.pk])
    assert any("Issa Bamba" in m for m in _messages(reponse))


def test_recruter_un_chauffeur_cree_sa_fiche_et_le_dit(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(poste="Chauffeur"), follow=True)

    assert Chauffeur.objects.filter(personnel__matricule="MAT-5001").exists()
    assert any("fiche chauffeur" in m for m in _messages(reponse))


def test_un_matricule_deja_pris_est_refuse(client):
    _connecte(client, Role.RH)
    PersonnelFactory(matricule="MAT-5001")

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees())

    assert "MAT-5001 est déjà attribué" in reponse.content.decode()
    assert Personnel.objects.filter(matricule="MAT-5001").count() == 1


def test_un_recrutement_incomplet_reste_sur_le_formulaire(client):
    _connecte(client, Role.RH)

    reponse = client.post(reverse("hr:personnel_nouveau"), _donnees(nom="", salaire_base="-5"))

    assert reponse.status_code == 200
    assert not Personnel.objects.exists()


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
    assert not Personnel.objects.filter(matricule="MAT-5001").exists()


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
        _donnees_modification(poste="Chef comptable", superieur=chef.pk, utilisateur=compte.pk),
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
python -m pytest apps/hr/tests/test_views_personnel.py -q --no-cov
```

**Résultat attendu :** `29 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

Ce fichier de tests appartient à `hr` mais il ouvre aussi les pages des chauffeurs (la fiche d'un employé
chauffeur renvoie vers sa fiche chauffeur) : c'est pourquoi il n'apparaît qu'ici.

**Dans le navigateur** (`python manage.py runserver`) :

1. Connectez-vous avec **`demo_rh`** : le menu affiche **Personnel**, **Congés** et **Chauffeurs**.
2. Ouvrez **Chauffeurs**, cliquez sur `Moussa Ouattara`. Cliquez **Modifier** et saisissez une **date
   d'expiration du permis dans 10 jours** : la fiche affiche « À renouveler » en orange ; la case « permis ou
   visite à renouveler » de la liste retrouve le chauffeur.
3. Cliquez **Suspendre** : une confirmation s'affiche (`data-confirm`), puis le statut passe à **Suspendu**.
   « Réactiver » le remet **Disponible**.
4. Connectez-vous avec `demo_charge` et essayez `/chauffeurs/` : **Accès refusé**.

## Ce qu'il faut retenir

- Ce qu'on **ne doit pas pouvoir faire** (poser « En mission » à la main) se traduit par un formulaire qui
  **ne propose pas** ces choix *et* par un service qui les **refuse** : la vue n'est jamais la seule défense.
- Les mêmes quatre motifs suffisent : un nouvel écran est surtout une question d'assemblage.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 18 : écrans des chauffeurs"
```

---

[← Chapitre 17](17-ecrans-rh.md) · [Sommaire](README.md) · [Chapitre 19 →](19-ecrans-clients.md)
