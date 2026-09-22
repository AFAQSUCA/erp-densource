# Chapitre 19 — Écrans : clients

> 8 fichier(s) dans ce chapitre, 793 lignes de code.

## Ce que vous allez construire

Les **écrans du portefeuille clients**.

| Écran | Adresse | Qui |
|---|---|---|
| Portefeuille (liste) | `/clients/` | ADMIN et CHARGE_CLIENTELE gèrent ; DIRECTION lit |
| Fiche client (avec historique commercial) | `/clients/<id>/` | idem |
| Créer / modifier | `/clients/nouveau/`, `/clients/<id>/modifier/` | ADMIN, CHARGE_CLIENTELE |
| Ajouter une interaction (appel, mail, réunion, devis, réclamation) | `/clients/<id>/interactions/` (POST) | ADMIN, CHARGE_CLIENTELE |

Fonctions à retrouver : filtres **« Mon portefeuille »** (les clients dont je suis le chargé attitré) et
**« Exonérés de TVA »**, dernière interaction et nombre de **réclamations** affichés dans la liste.

## Prérequis

- Chapitres 1 à 18 terminés.

## Ce que ce chapitre apporte de nouveau

Un **formulaire de filtre** (`FiltreClientsForm`) : plutôt que de lire `request.GET` à la main, on valide les
paramètres de l'adresse avec un vrai formulaire, ce qui ignore proprement une valeur inutilisable.

Et une page qui **héberge les blocs d'une autre app** : la fiche client affiche
`{% for section in sections %}…` : les **missions du client** seront fournies par `missions` au chapitre 21 (le
registre `DETAIL_CLIENT` du chapitre 7). Tant que ce chapitre n'existe pas, la fiche s'affiche sans ce bloc.

## Étape 1 — Formulaires, vues, adresses

#### `apps/customers/forms.py`

*92 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import DELAI_PAIEMENT_DEFAUT, TVA_DEFAUT, MotifExoneration, TypeInteraction


def _libelle_compte(u) -> str:
    return u.get_full_name() or u.username


class ClientForm(StyleTailwindMixin, forms.Form):
    """Fiche client (cahier-des-charges.md:119-122)."""

    raison_sociale = forms.CharField(label="Raison sociale", max_length=200)
    ncc_nif = forms.CharField(label="NCC / NIF", max_length=50)
    contact_principal = forms.CharField(label="Contact principal", max_length=150)
    telephone = forms.CharField(label="Téléphone", max_length=20)
    email = forms.EmailField(label="Email", required=False)
    adresse = forms.CharField(label="Adresse / siège", widget=forms.Textarea(attrs={"rows": 2}))
    charge_clientele = forms.ModelChoiceField(
        label="Chargé clientèle attitré", queryset=None, required=False
    )
    taux_tva = forms.DecimalField(
        label="Taux de TVA (%)",
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        initial=TVA_DEFAUT,
        help_text="18 % par défaut ; 0 % pour un client exonéré (motif obligatoire).",
    )
    motif_exoneration = forms.ChoiceField(
        label="Motif d'exonération",
        choices=[("", "—")] + MotifExoneration.choices,
        required=False,
    )

    delai_paiement_jours = forms.IntegerField(
        label="Délai de paiement (jours)",
        min_value=1,
        max_value=365,
        initial=DELAI_PAIEMENT_DEFAUT,
        help_text="L'échéance de ses factures = date d'émission + ce délai.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["charge_clientele"].queryset = services.charges_clientele()
        self.fields["charge_clientele"].label_from_instance = _libelle_compte

    def clean(self):
        donnees = super().clean()
        taux = donnees.get("taux_tva")
        if taux is not None and taux == 0 and not donnees.get("motif_exoneration"):
            self.add_error("motif_exoneration", "Motif obligatoire quand la TVA est à 0 %.")
        return donnees


class InteractionForm(StyleTailwindMixin, forms.Form):
    """Interaction commerciale : appel, mail, réunion, devis, réclamation."""

    type_interaction = forms.ChoiceField(label="Type", choices=TypeInteraction.choices)
    date_interaction = forms.DateTimeField(
        label="Date et heure",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
    )
    resume = forms.CharField(label="Résumé de l'échange", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_interaction"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")


class FiltreClientsForm(forms.Form):
    """Filtres de la liste ; les paramètres invalides sont ignorés."""

    q = forms.CharField(required=False)
    mes_clients = forms.BooleanField(required=False)
    exonere = forms.BooleanField(required=False)

    def criteres(self, utilisateur) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q", ""),
            "charge_clientele": utilisateur if donnees.get("mes_clients") else None,
            "exonere": bool(donnees.get("exonere")),
        }
```

#### `apps/customers/views.py`

*146 lignes* — Écrans des clients : portefeuille, fiche, création, modification, interactions.

```python
"""Écrans des clients : portefeuille, fiche, création, modification, interactions.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role
from apps.core.views import PaginationTolerante

from . import permissions, sections, services
from .exceptions import ClientError
from .forms import ClientForm, FiltreClientsForm, InteractionForm
from .models import Client


class ClientListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "customers/client_list.html"
    context_object_name = "clients"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreClientsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_clients(**self.get_filtre().criteres(self.request.user))

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        criteres = self.get_filtre().criteres(self.request.user)
        utilisateur = self.request.user
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(criteres.values()),
            peut_modifier=utilisateur.role_effectif in permissions.MODIFICATION,
            a_un_portefeuille=utilisateur.role == Role.CHARGE_CLIENTELE,
        )
        return contexte


class ClientDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "customers/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return services.clients_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        client, utilisateur = self.object, self.request.user
        peut_modifier = utilisateur.role_effectif in permissions.MODIFICATION
        contexte.update(
            peut_modifier=peut_modifier,
            interactions=services.interactions_du_client(client)[:50],
            form_interaction=InteractionForm() if peut_modifier else None,
            sections=sections.DETAIL_CLIENT.sections(client, utilisateur),
        )
        return contexte


class ClientCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ClientForm
    template_name = "customers/client_form.html"

    def form_valid(self, form):
        try:
            client = services.creer_client(**form.cleaned_data)
        except ClientError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Client « {client.raison_sociale} » créé.")
        return redirect("customers:detail", pk=client.pk)


class ClientUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ClientForm
    template_name = "customers/client_form.html"

    @property
    def client(self):
        if not hasattr(self, "_client"):
            self._client = get_object_or_404(Client, pk=self.kwargs["pk"])
        return self._client

    def get_initial(self):
        c = self.client
        return {
            "raison_sociale": c.raison_sociale,
            "ncc_nif": c.ncc_nif,
            "contact_principal": c.contact_principal,
            "telephone": c.telephone,
            "email": c.email,
            "adresse": c.adresse,
            "charge_clientele": c.charge_clientele,
            "taux_tva": c.taux_tva,
            "motif_exoneration": c.motif_exoneration,
            "delai_paiement_jours": c.delai_paiement_jours,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["client"] = self.client
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_client(self.client, **form.cleaned_data)
        except ClientError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de « {self.client.raison_sociale} » mise à jour.")
        return redirect("customers:detail", pk=self.client.pk)


class InteractionCreateView(RoleRequiredMixin, View):
    """Ajoute une interaction à l'historique du client (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = InteractionForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("customers:detail", pk=client.pk)
        try:
            services.enregistrer_interaction(client, request.user, **form.cleaned_data)
        except ClientError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Interaction ajoutée à l'historique.")
        return redirect("customers:detail", pk=client.pk)
```

#### `apps/customers/urls.py`

*13 lignes*

```python
from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.ClientListView.as_view(), name="liste"),
    path("nouveau/", views.ClientCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.ClientDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ClientUpdateView.as_view(), name="modifier"),
    path("<int:pk>/interactions/", views.InteractionCreateView.as_view(), name="interaction"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -16,4 +16,5 @@
     path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
     path("", include("apps.accounts.urls")),
+    path("clients/", include("apps.customers.urls")),
     path("rh/", include("apps.hr.urls")),
     path("chauffeurs/", include("apps.drivers.urls")),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/customers/templates/customers
```

#### `apps/customers/templates/customers/client_list.html`

*85 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Clients{% endblock %}
{% block entete %}Clients{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Clients</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} client{{ paginator.count|pluralize }}</p>
    </div>
    {% if peut_modifier %}
      <a href="{% url 'customers:creer' %}"
         class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouveau client
      </a>
    {% endif %}
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ filtre.q.value|default:'' }}" placeholder="Raison sociale, NCC / NIF, contact, téléphone…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    {% if a_un_portefeuille %}
      <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
        <input type="checkbox" name="mes_clients" value="on" {% if filtre.mes_clients.value %}checked{% endif %}
               class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
        Mon portefeuille
      </label>
    {% endif %}
    <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
      <input type="checkbox" name="exonere" value="on" {% if filtre.exonere.value %}checked{% endif %}
             class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
      Exonérés de TVA
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}
      <a href="{% url 'customers:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if clients %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des clients</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Client</th>
            <th scope="col" class="px-4 py-3">Contact</th>
            <th scope="col" class="px-4 py-3">Chargé clientèle</th>
            <th scope="col" class="px-4 py-3 text-right">TVA</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Dernière interaction</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Réclamations</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for c in clients %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'customers:detail' c.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ c.raison_sociale }}</a>
                <span class="block text-xs font-normal text-slate-600">{{ c.ncc_nif }}</span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ c.contact_principal }}<span class="block text-xs text-slate-600">{{ c.telephone }}</span></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{% if c.charge_clientele %}{{ c.charge_clientele }}{% else %}<span class="text-slate-500">Non attribué</span>{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{% if c.taux_tva == 0 %}<span class="font-semibold text-amber-900">Exonéré</span>{% else %}{{ c.taux_tva|floatformat:"-2" }} %{% endif %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{% if c.derniere_interaction %}{{ c.derniere_interaction|date:"d/m/Y" }}{% else %}—{% endif %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 xl:table-cell">{% if c.nb_reclamations %}{% badge "RECLAMATION" c.nb_reclamations %}{% else %}<span class="text-slate-500">0</span>{% endif %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-handshake" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun client trouvé</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Créez la fiche du premier client pour commencer.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/customers/templates/customers/client_detail.html`

*82 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}{{ client.raison_sociale }}{% endblock %}
{% block entete %}Clients{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'customers:liste' %}" class="underline-offset-2 hover:underline">Clients</a>
    <span aria-hidden="true">/</span> {{ client.raison_sociale }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ client.raison_sociale }}</h1>
    {% if peut_modifier %}
      <a href="{% url 'customers:modifier' client.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">NCC / NIF {{ client.ncc_nif }}</p>

  <div class="mt-6 grid gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-1">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-fiche">
        <h2 id="titre-fiche" class="text-base font-semibold text-slate-900">Fiche</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div><dt class="text-slate-600">Contact principal</dt><dd class="mt-0.5 font-medium text-slate-900">{{ client.contact_principal }}</dd></div>
          <div><dt class="text-slate-600">Téléphone</dt><dd class="mt-0.5 font-medium text-slate-900">{{ client.telephone }}</dd></div>
          <div><dt class="text-slate-600">Email</dt><dd class="mt-0.5 font-medium text-slate-900">{% if client.email %}<a href="mailto:{{ client.email }}" class="text-marque-700 underline-offset-2 hover:underline">{{ client.email }}</a>{% else %}Non renseigné{% endif %}</dd></div>
          <div><dt class="text-slate-600">Adresse / siège</dt><dd class="mt-0.5 whitespace-pre-line font-medium text-slate-900">{{ client.adresse }}</dd></div>
          <div><dt class="text-slate-600">Chargé clientèle attitré</dt><dd class="mt-0.5 font-medium text-slate-900">{{ client.charge_clientele|default:"Non attribué" }}</dd></div>
          <div><dt class="text-slate-600">TVA</dt><dd class="mt-0.5 font-medium text-slate-900">
            {% if client.taux_tva == 0 %}Exonéré : {{ client.get_motif_exoneration_display }}{% else %}{{ client.taux_tva|floatformat:"-2" }} %{% endif %}</dd></div>
          <div><dt class="text-slate-600">Délai de paiement</dt><dd class="mt-0.5 font-medium text-slate-900">{{ client.delai_paiement_jours }} jours</dd></div>
        </dl>
      </section>
    </div>

    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-historique">
        <h2 id="titre-historique" class="text-base font-semibold text-slate-900">Historique commercial ({{ client.nb_interactions }})</h2>

        {% if form_interaction %}
          <form method="post" action="{% url 'customers:interaction' client.pk %}" class="mt-4 space-y-4 rounded-lg bg-slate-50 p-4">
            {% csrf_token %}
            <h3 class="text-sm font-semibold text-slate-900">Ajouter une interaction</h3>
            <div class="grid gap-4 sm:grid-cols-2">
              {% include "components/_champ.html" with champ=form_interaction.type_interaction %}
              {% include "components/_champ.html" with champ=form_interaction.date_interaction %}
            </div>
            {% include "components/_champ.html" with champ=form_interaction.resume %}
            <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer l'interaction</button>
          </form>
        {% endif %}

        {% if interactions %}
          <ol class="mt-5 space-y-4 text-sm">
            {% for i in interactions %}
              <li class="flex gap-3">
                <span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full {% if i.type_interaction == 'RECLAMATION' %}bg-red-600{% else %}bg-slate-400{% endif %}" aria-hidden="true"></span>
                <div>
                  <p class="flex flex-wrap items-center gap-2">
                    {% if i.type_interaction == "RECLAMATION" %}{% badge "RECLAMATION" i.get_type_interaction_display %}{% else %}<strong class="text-slate-900">{{ i.get_type_interaction_display }}</strong>{% endif %}
                    <span class="text-slate-600">{{ i.date_interaction|date:"d/m/Y à H:i" }}{% if i.auteur %} · {{ i.auteur }}{% endif %}</span>
                  </p>
                  <p class="mt-1 whitespace-pre-line text-slate-800">{{ i.resume }}</p>
                </div>
              </li>
            {% endfor %}
          </ol>
        {% else %}
          <p class="mt-4 text-sm text-slate-600">Aucune interaction enregistrée.</p>
        {% endif %}
      </section>

      {% for section in sections %}{% include section.template with section=section %}{% endfor %}
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/customers/templates/customers/client_form.html`

*68 lignes*

```django
{% extends "base.html" %}
{% block titre %}{% if client %}Modifier {{ client.raison_sociale }}{% else %}Nouveau client{% endif %}{% endblock %}
{% block entete %}Clients{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl" x-data="{ tva: '' }" x-init="tva = $refs.taux.value">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'customers:liste' %}" class="underline-offset-2 hover:underline">Clients</a>
    <span aria-hidden="true">/</span>
    {% if client %}
      <a href="{% url 'customers:detail' client.pk %}" class="underline-offset-2 hover:underline">{{ client.raison_sociale }}</a>
      <span aria-hidden="true">/</span> Modifier
    {% else %}Nouveau client{% endif %}
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">{% if client %}Modifier {{ client.raison_sociale }}{% else %}Nouveau client{% endif %}</h1>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <fieldset>
      <legend class="text-sm font-semibold text-slate-900">Société</legend>
      <div class="mt-3 grid gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.raison_sociale %}
        {% include "components/_champ.html" with champ=form.ncc_nif %}
      </div>
      <div class="mt-5">{% include "components/_champ.html" with champ=form.adresse %}</div>
    </fieldset>

    <fieldset class="border-t border-slate-100 pt-5">
      <legend class="text-sm font-semibold text-slate-900">Contact</legend>
      <div class="mt-3 grid gap-5 sm:grid-cols-2">
        {% include "components/_champ.html" with champ=form.contact_principal %}
        {% include "components/_champ.html" with champ=form.telephone %}
        {% include "components/_champ.html" with champ=form.email %}
        {% include "components/_champ.html" with champ=form.charge_clientele %}
      </div>
    </fieldset>

    <fieldset class="border-t border-slate-100 pt-5">
      <legend class="text-sm font-semibold text-slate-900">TVA</legend>
      <div class="mt-3 grid gap-5 sm:grid-cols-2">
        <div>
          <label for="{{ form.taux_tva.id_for_label }}" class="block text-sm font-medium text-slate-800">{{ form.taux_tva.label }}<span class="text-red-700" aria-hidden="true"> *</span></label>
          <div class="mt-1"><input type="number" name="taux_tva" id="{{ form.taux_tva.id_for_label }}" step="0.01" min="0" max="100" required
                 value="{{ form.taux_tva.value|default:'18' }}" x-ref="taux" @input="tva = $event.target.value"
                 class="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></div>
          <p class="mt-1 text-xs text-slate-600">{{ form.taux_tva.help_text }}</p>
          {% for erreur in form.taux_tva.errors %}<p class="mt-1 text-xs font-medium text-red-700" role="alert">{{ erreur }}</p>{% endfor %}
        </div>
        <div x-show="parseFloat(tva) === 0" x-cloak>
          {% include "components/_champ.html" with champ=form.motif_exoneration %}
        </div>
        {% include "components/_champ.html" with champ=form.delai_paiement_jours %}
      </div>
    </fieldset>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% if client %}{% url 'customers:detail' client.pk %}{% else %}{% url 'customers:liste' %}{% endif %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">{% if client %}Enregistrer{% else %}Créer le client{% endif %}</button>
    </div>
  </form>
</div>
{% endblock %}
```

## Étape 3 — Tests et compilation des styles

Ce chapitre présente les tests de `customers` laissés de côté au chapitre 7 (ils ouvrent des pages).

#### `apps/customers/tests/test_models.py`

*79 lignes*

```python
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.customers.models import MotifExoneration, TypeInteraction

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def test_tva_par_defaut_est_18_pourcent():
    assert ClientFactory().taux_tva == Decimal("18.00")


def test_tva_zero_sans_motif_refusee_par_la_validation():
    client = ClientFactory.build(taux_tva=Decimal("0"), motif_exoneration="")

    with pytest.raises(ValidationError):
        client.clean()


def test_tva_zero_sans_motif_refusee_par_la_base_de_donnees():
    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(taux_tva=Decimal("0"), motif_exoneration="")


def test_tva_zero_avec_motif_acceptee():
    client = ClientFactory(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.ONG)

    client.full_clean()


def test_taux_tva_superieur_a_100_refuse_par_la_base_de_donnees():
    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(taux_tva=Decimal("101"))


def test_ncc_nif_unique():
    ClientFactory(ncc_nif="CI-0001A")

    with pytest.raises(IntegrityError), transaction.atomic():
        ClientFactory(ncc_nif="CI-0001A")


def test_interaction_rattachee_au_client_et_triee_par_date_decroissante():
    from django.utils import timezone

    client = ClientFactory()
    ancienne = client.interactions.create(
        type_interaction=TypeInteraction.APPEL,
        resume="Premier appel",
        date_interaction=timezone.now() - timezone.timedelta(days=2),
    )
    recente = client.interactions.create(
        type_interaction=TypeInteraction.RECLAMATION, resume="Retard livraison"
    )

    assert list(client.interactions.all()) == [recente, ancienne]


def test_creation_client_est_auditee():
    from apps.audit.models import AuditLog

    client = ClientFactory()

    entree = AuditLog.objects.get(entite="Client", entite_id=client.pk)
    assert entree.module == "CLIENTELE"


def test_clients_pour_selection_est_trie_par_raison_sociale():
    from apps.customers import services

    b = ClientFactory(raison_sociale="Bolloré")
    a = ClientFactory(raison_sociale="Abidjan Cargo")

    assert list(services.clients_pour_selection()) == [a, b]
```

#### `apps/customers/tests/test_services.py`

*220 lignes* — Services clients : fiche, TVA, portefeuille, historique commercial.

```python
"""Services clients : fiche, TVA, portefeuille, historique commercial."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services
from apps.customers.exceptions import ClientError
from apps.customers.models import Client, Interaction, MotifExoneration, TypeInteraction

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def _champs(**surcharges):
    champs = dict(
        raison_sociale="Cimaf CI",
        ncc_nif="CI-1234567A",
        contact_principal="Awa Coulibaly",
        telephone="+2250700000000",
        adresse="Abidjan, Plateau",
    )
    champs.update(surcharges)
    return champs


# --- création et modification ---


def test_creer_client_applique_la_tva_par_defaut_de_18_pourcent():
    client = services.creer_client(**_champs())

    assert client.taux_tva == Decimal("18.00")
    assert client.motif_exoneration == "" and client.charge_clientele is None


def test_creer_client_exonere_exige_un_motif():
    with pytest.raises(ClientError, match="motif d'exonération"):
        services.creer_client(**_champs(taux_tva=Decimal("0")))

    client = services.creer_client(
        **_champs(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.ONG)
    )
    assert client.motif_exoneration == MotifExoneration.ONG


def test_le_motif_est_efface_quand_la_tva_redevient_positive():
    client = services.creer_client(
        **_champs(taux_tva=Decimal("0"), motif_exoneration=MotifExoneration.EXPORT)
    )

    services.modifier_client(client, taux_tva=Decimal("18"))

    client.refresh_from_db()
    assert client.motif_exoneration == ""


@pytest.mark.parametrize("taux", [Decimal("-1"), Decimal("100.01")])
def test_le_taux_de_tva_doit_etre_entre_0_et_100(taux):
    with pytest.raises(ClientError, match="entre 0 et 100"):
        services.creer_client(**_champs(taux_tva=taux, motif_exoneration="AUTRE"))


def test_le_ncc_nif_est_unique_meme_parmi_les_clients_supprimes():
    ancien = ClientFactory(ncc_nif="CI-1234567A")

    with pytest.raises(ClientError, match="déjà utilisé"):
        services.creer_client(**_champs())
    ancien.delete()
    with pytest.raises(ClientError, match="déjà utilisé"):
        services.creer_client(**_champs())


def test_le_charge_clientele_doit_avoir_le_bon_role_et_etre_actif():
    with pytest.raises(ClientError, match="chargé clientèle"):
        services.creer_client(**_champs(charge_clientele=UserFactory(role=Role.FINANCES)))
    with pytest.raises(ClientError, match="chargé clientèle"):
        services.creer_client(
            **_champs(charge_clientele=UserFactory(role=Role.CHARGE_CLIENTELE, is_active=False))
        )

    charge = UserFactory(role=Role.CHARGE_CLIENTELE)
    assert services.creer_client(**_champs(charge_clientele=charge)).charge_clientele == charge


def test_modifier_client_ne_change_que_les_champs_fournis_et_garde_son_propre_nif():
    client = ClientFactory(ncc_nif="CI-0000001A", telephone="0100000000")

    services.modifier_client(client, raison_sociale="Nouveau nom", ncc_nif="CI-0000001A")

    client.refresh_from_db()
    assert client.raison_sociale == "Nouveau nom" and client.telephone == "0100000000"


def test_modifier_client_refuse_le_nif_d_un_autre_client():
    ClientFactory(ncc_nif="CI-0000002A")
    client = ClientFactory()

    with pytest.raises(ClientError, match="déjà utilisé"):
        services.modifier_client(client, ncc_nif="CI-0000002A")


# --- recherche ---


def test_rechercher_clients_par_texte_portefeuille_et_exoneration():
    charge = UserFactory(role=Role.CHARGE_CLIENTELE)
    a = ClientFactory(raison_sociale="Cimaf", charge_clientele=charge, contact_principal="Koffi")
    b = ClientFactory(raison_sociale="Solibra", taux_tva=Decimal("0"), motif_exoneration="ONG")

    assert list(services.rechercher_clients(recherche="cim")) == [a]
    assert list(services.rechercher_clients(recherche="koffi")) == [a]
    assert list(services.rechercher_clients(charge_clientele=charge)) == [a]
    assert list(services.rechercher_clients(exonere=True)) == [b]
    assert services.rechercher_clients().count() == 2


def test_la_liste_compte_interactions_et_reclamations_sans_doublons():
    client = ClientFactory()
    auteur = UserFactory(role=Role.CHARGE_CLIENTELE)
    for type_interaction in (TypeInteraction.APPEL, TypeInteraction.RECLAMATION, TypeInteraction.RECLAMATION):
        services.enregistrer_interaction(client, auteur, type_interaction=type_interaction, resume="x")
    supprimee = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.RECLAMATION, resume="à ignorer"
    )
    supprimee.delete()

    ligne = services.clients_queryset().get(pk=client.pk)

    assert (ligne.nb_interactions, ligne.nb_reclamations) == (3, 2)
    assert ligne.derniere_interaction is not None


def test_un_client_sans_interaction_a_des_compteurs_a_zero():
    ligne = services.clients_queryset().get(pk=ClientFactory().pk)

    assert (ligne.nb_interactions, ligne.nb_reclamations, ligne.derniere_interaction) == (0, 0, None)


def test_charges_clientele_ne_liste_que_les_comptes_actifs_de_ce_role():
    bon = UserFactory(role=Role.CHARGE_CLIENTELE)
    UserFactory(role=Role.CHARGE_CLIENTELE, is_active=False)
    UserFactory(role=Role.RH)

    assert list(services.charges_clientele()) == [bon]


# --- interactions ---


def test_enregistrer_interaction_par_defaut_a_l_instant_present():
    client, auteur = ClientFactory(), UserFactory(role=Role.CHARGE_CLIENTELE)

    interaction = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.DEMANDE_DEVIS, resume="Devis Abidjan-Bouaké"
    )

    assert interaction.auteur == auteur and interaction.client == client
    assert abs(timezone.now() - interaction.date_interaction) < timedelta(seconds=5)


def test_le_resume_d_une_interaction_est_obligatoire():
    with pytest.raises(ClientError, match="résumé"):
        services.enregistrer_interaction(
            ClientFactory(), UserFactory(), type_interaction=TypeInteraction.APPEL, resume="   "
        )
    assert not Interaction.objects.exists()


def test_une_interaction_ne_peut_pas_etre_datee_dans_le_futur():
    with pytest.raises(ClientError, match="futur"):
        services.enregistrer_interaction(
            ClientFactory(), UserFactory(), type_interaction=TypeInteraction.APPEL, resume="x",
            date_interaction=timezone.now() + timedelta(days=1),
        )


def test_les_interactions_sont_triees_de_la_plus_recente_a_la_plus_ancienne():
    client, auteur = ClientFactory(), UserFactory()
    ancienne = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.MAIL, resume="a",
        date_interaction=timezone.now() - timedelta(days=3),
    )
    recente = services.enregistrer_interaction(
        client, auteur, type_interaction=TypeInteraction.APPEL, resume="b"
    )

    assert list(services.interactions_du_client(client)) == [recente, ancienne]


def test_clients_pour_selection_est_trie_par_raison_sociale():
    ClientFactory(raison_sociale="Zeta")
    ClientFactory(raison_sociale="Alpha")

    assert [c.raison_sociale for c in services.clients_pour_selection()] == ["Alpha", "Zeta"]
    assert Client.objects.count() == 2


def test_le_delai_de_paiement_par_defaut_est_de_30_jours():
    assert services.creer_client(**_champs()).delai_paiement_jours == 30


@pytest.mark.parametrize("delai", [0, 366, -5])
def test_un_delai_de_paiement_hors_bornes_est_refuse(delai):
    with pytest.raises(ClientError, match="entre 1 et 365"):
        services.creer_client(**_champs(delai_paiement_jours=delai))


def test_modifier_le_delai_de_paiement():
    client = ClientFactory()

    services.modifier_client(client, delai_paiement_jours=60)

    client.refresh_from_db()
    assert client.delai_paiement_jours == 60
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
python -m pytest apps/customers/tests/test_models.py apps/customers/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `32 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur :**

1. Connectez-vous avec **`demo_charge`** : le menu affiche **Clients**.
2. « Nouveau client » : saisissez une **TVA à 0 %** **sans motif** : le formulaire refuse (le service lève
   `ClientError`, la vue l'affiche). Saisissez le motif « Export » : le client est créé.
3. Sur la fiche, **Ajouter une interaction** de type **Réclamation** : la liste affiche maintenant « 1
   réclamation » pour ce client.
4. Connectez-vous avec `demo_direction` : la fiche s'ouvre **sans** boutons de modification (lecture seule).

## Ce qu'il faut retenir

- On peut valider les **paramètres d'une adresse** (les filtres) avec un formulaire, comme n'importe quelle saisie.
- Une fiche peut afficher des blocs de **modules qu'elle ne connaît pas** grâce aux registres.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 19 : écrans des clients"
```

---

[← Chapitre 18](18-ecrans-chauffeurs.md) · [Sommaire](README.md) · [Chapitre 20 →](20-ecrans-flotte.md)
