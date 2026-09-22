# Chapitre 23 — Écrans : stock de pièces

> 11 fichier(s) dans ce chapitre, 1821 lignes de code.

## Ce que vous allez construire

Les **écrans du stock de pièces** (Parc Auto : gestion ; Direction : lecture seule).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des articles | `/stock/` | recherche, catégorie, filtre « sous le seuil », **valeur totale du stock au PUMP** |
| Fiche d'un article | `/stock/articles/<id>/` | derniers mouvements, entrée d'achat, ajustement |
| Créer / modifier | `/stock/articles/nouveau/`, `…/<id>/modifier/` | la référence ne change plus après création |
| **Entrée** (achat) | `/stock/articles/<id>/entree/` (POST) | recalcule le PUMP |
| **Ajustement** (inventaire) | `/stock/articles/<id>/ajustement/` (POST) | **motif obligatoire** |
| Journal des mouvements | `/stock/mouvements/` | filtrable |
| **Sortie pour un OR** | `/stock/or/<id>/sortie/` (POST) | depuis la fiche d'un OR |
| Bloc « **Pièces utilisées** » | dans la fiche d'un OR (`/garage/<id>/`) | pièces, coût des pièces, coût total |

## Prérequis

- Chapitres 1 à 22 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le second bloc attendu** : `_pieces_or.html` est enfin créé. La fiche d'un OR (chapitre 22) affiche
  automatiquement les pièces utilisées, avec leur formulaire de sortie, sans modification de `garage`.
- **Un message d'alerte** quand une sortie ou un ajustement fait atteindre le seuil minimal : `services` renvoie
  l'information, la vue en fait un `messages.warning`.
- **Le journal comme écran de lecture** : pas de formulaire, seulement filtres et liste.
- Les formulaires (`SortieForm`, `ArticleForm`, `EntreeForm`, `AjustementForm`) existent déjà (chapitre 11) : ce
  chapitre ne présente que les **vues, adresses et gabarits**.

## Étape 1 — Vues et adresses

#### `apps/inventory/views.py`

*247 lignes* — Écrans du stock : articles, fiche, entrées, ajustements, journal, sorties pour OR.

```python
"""Écrans du stock : articles, fiche, entrées, ajustements, journal, sorties pour OR.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import PaginationTolerante
from apps.garage import services as garage_services

from . import permissions, services
from .exceptions import StockError
from .forms import (
    AjustementForm,
    ArticleCreationForm,
    ArticleForm,
    EntreeForm,
    SortieForm,
)
from .models import TypeMouvement


def _alerter_si_seuil_bas(request, article) -> None:
    """Rend l'alerte de seuil visible (cahier-des-charges.md:337-338)."""
    if article.sous_seuil:
        messages.warning(
            request,
            f"Stock bas : il reste {article.quantite} x {article.reference} "
            f"(seuil minimal {article.seuil_minimal}). Pensez à réapprovisionner.",
        )


def _erreurs_du_formulaire(request, form) -> None:
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


class ArticleListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "inventory/article_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_articles(
            recherche=self.request.GET.get("q", ""),
            categorie=self.request.GET.get("categorie", ""),
            sous_seuil=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            recherche=self.request.GET.get("q", ""),
            categorie_choisie=self.request.GET.get("categorie", ""),
            alerte=self.request.GET.get("alerte") == "1",
            categories=services.categories_articles(),
            valeur_totale=services.valeur_totale_stock(),
            nombre_sous_seuil=services.articles_sous_seuil().count(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class ArticleDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "inventory/article_detail.html"
    context_object_name = "article"

    def get_queryset(self):
        return services.rechercher_articles()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            mouvements=services.mouvements_de_l_article(self.object),
            peut_modifier=peut_modifier,
            form_entree=EntreeForm() if peut_modifier else None,
            form_ajustement=AjustementForm() if peut_modifier else None,
        )
        return contexte


class ArticleCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ArticleCreationForm
    template_name = "inventory/article_form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(titre="Nouvel article", bouton="Créer l'article")
        return contexte

    def form_valid(self, form):
        try:
            article = services.creer_article(**form.cleaned_data)
        except StockError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Article {article.reference} créé. Son stock est à 0 : enregistrez une entrée d'achat.",
        )
        return redirect("inventory:article_detail", pk=article.pk)


class ArticleUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ArticleForm
    template_name = "inventory/article_form.html"

    @property
    def article(self):
        if not hasattr(self, "_article"):
            self._article = get_object_or_404(services.rechercher_articles(), pk=self.kwargs["pk"])
        return self._article

    def get_initial(self):
        a = self.article
        return {
            "designation": a.designation,
            "categorie": a.categorie,
            "emplacement": a.emplacement,
            "seuil_minimal": a.seuil_minimal,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            titre=f"Modifier {self.article.reference}", bouton="Enregistrer", article=self.article
        )
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_article(self.article, **form.cleaned_data)
        except StockError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Article {self.article.reference} mis à jour.")
        return redirect("inventory:article_detail", pk=self.article.pk)


class EntreeView(RoleRequiredMixin, View):
    """Enregistre une entrée d'achat (POST) : le PUMP est recalculé."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(services.rechercher_articles(), pk=pk)
        form = EntreeForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("inventory:article_detail", pk=article.pk)
        try:
            services.enregistrer_entree(article, acteur=request.user, **form.cleaned_data)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Entrée de {form.cleaned_data['quantite']} x {article.reference} enregistrée. "
                f"Stock : {article.quantite}, PUMP : {nombre(article.pump)} FCFA.",
            )
        return redirect("inventory:article_detail", pk=article.pk)


class AjustementView(RoleRequiredMixin, View):
    """Enregistre un ajustement d'inventaire (POST), toujours justifié."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        article = get_object_or_404(services.rechercher_articles(), pk=pk)
        form = AjustementForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("inventory:article_detail", pk=article.pk)
        try:
            services.ajuster_stock(article, acteur=request.user, **form.cleaned_data)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Ajustement de {form.cleaned_data['variation']:+d} enregistré : "
                f"{article.quantite} x {article.reference} en stock.",
            )
            _alerter_si_seuil_bas(request, article)
        return redirect("inventory:article_detail", pk=article.pk)


class MouvementListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "inventory/mouvement_list.html"
    context_object_name = "mouvements"
    paginate_by = 30

    def get_queryset(self):
        return services.rechercher_mouvements(
            type_mouvement=self.request.GET.get("type"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            types=TypeMouvement.choices,
            type_choisi=self.request.GET.get("type", ""),
            recherche=self.request.GET.get("q", ""),
        )
        return contexte


class SortieOrView(RoleRequiredMixin, View):
    """Sort des pièces du stock pour un OR ouvert (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(garage_services.ordres_queryset(), pk=pk)
        form = SortieForm(request.POST)
        if not form.is_valid():
            _erreurs_du_formulaire(request, form)
            return redirect("garage:detail", pk=ordre.pk)
        article, quantite = form.cleaned_data["article"], form.cleaned_data["quantite"]
        try:
            services.sortir_pour_or(article, quantite=quantite, ordre=ordre, acteur=request.user)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{quantite} x {article.reference} sortie(s) pour l'OR {ordre.numero}."
            )
            _alerter_si_seuil_bas(request, article)
        return redirect("garage:detail", pk=ordre.pk)
```

#### `apps/inventory/urls.py`

*16 lignes*

```python
from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.ArticleListView.as_view(), name="articles"),
    path("articles/nouveau/", views.ArticleCreateView.as_view(), name="article_creer"),
    path("articles/<int:pk>/", views.ArticleDetailView.as_view(), name="article_detail"),
    path("articles/<int:pk>/modifier/", views.ArticleUpdateView.as_view(), name="article_modifier"),
    path("articles/<int:pk>/entree/", views.EntreeView.as_view(), name="entree"),
    path("articles/<int:pk>/ajustement/", views.AjustementView.as_view(), name="ajustement"),
    path("mouvements/", views.MouvementListView.as_view(), name="mouvements"),
    path("or/<int:pk>/sortie/", views.SortieOrView.as_view(), name="sortie_or"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -22,4 +22,5 @@
     path("chauffeurs/", include("apps.drivers.urls")),
     path("garage/", include("apps.garage.urls")),
+    path("stock/", include("apps.inventory.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/inventory/templates/inventory
```

#### `apps/inventory/templates/inventory/article_list.html`

*118 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Stock{% endblock %}
{% block entete %}Stock{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Stock de pièces détachées</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} article{{ paginator.count|pluralize }}</p>
    </div>
    <div class="flex flex-wrap gap-3">
      <a href="{% url 'inventory:mouvements' %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-clock-rotate-left" aria-hidden="true"></i> Journal des mouvements
      </a>
      {% if peut_modifier %}
        <a href="{% url 'inventory:article_creer' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvel article
        </a>
      {% endif %}
    </div>
  </div>

  <dl class="mt-5 grid gap-4 sm:grid-cols-2">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <dt class="text-sm text-slate-600">Valeur du stock (au PUMP)</dt>
      <dd class="mt-1 text-2xl font-bold text-slate-900">{{ valeur_totale|floatformat:0|intcomma }} FCFA</dd>
    </div>
    <div class="rounded-xl border p-4 shadow-sm {% if nombre_sous_seuil %}border-amber-300 bg-amber-50{% else %}border-slate-200 bg-white{% endif %}">
      <dt class="text-sm {% if nombre_sous_seuil %}text-amber-900{% else %}text-slate-600{% endif %}">Articles à réapprovisionner</dt>
      <dd class="mt-1 flex items-center gap-3 text-2xl font-bold text-slate-900">
        {{ nombre_sous_seuil }}
        {% if nombre_sous_seuil %}<a href="?alerte=1" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir la liste</a>{% endif %}
      </dd>
    </div>
  </dl>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="Référence, désignation, emplacement…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="categorie" class="block text-sm font-medium text-slate-800">Catégorie</label>
      <select id="categorie" name="categorie" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Toutes</option>
        {% for c in categories %}<option value="{{ c }}" {% if c == categorie_choisie %}selected{% endif %}>{{ c }}</option>{% endfor %}
      </select>
    </div>
    <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
      <input type="checkbox" name="alerte" value="1" {% if alerte %}checked{% endif %}
             class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
      Sous le seuil
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or categorie_choisie or alerte %}
      <a href="{% url 'inventory:articles' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if articles %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des articles en stock</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Référence</th>
            <th scope="col" class="px-4 py-3">Désignation</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Catégorie</th>
            <th scope="col" class="hidden px-4 py-3 2xl:table-cell">Emplacement</th>
            <th scope="col" class="px-4 py-3 text-right">Quantité</th>
            <th scope="col" class="px-4 py-3 text-right">Seuil</th>
            <th scope="col" class="px-4 py-3 text-right">PUMP</th>
            <th scope="col" class="px-4 py-3 text-right">Valeur</th>
            <th scope="col" class="px-4 py-3">Alerte</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for article in articles %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'inventory:article_detail' article.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ article.reference }}</a>
              </td>
              <td class="px-4 py-3 text-slate-800">{{ article.designation }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ article.categorie|default:"—" }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 2xl:table-cell">{{ article.emplacement|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">{{ article.quantite }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{% if article.seuil_minimal %}{{ article.seuil_minimal }}{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ article.pump|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-800">{{ article.valeur_stock|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                {% if article.sous_seuil %}
                  {% if article.quantite == 0 %}{% badge "RUPTURE" "Rupture" %}{% else %}{% badge "STOCK_BAS" "Stock bas" %}{% endif %}
                {% endif %}
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
        <i class="fa-solid fa-boxes-stacked" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucun article trouvé</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or categorie_choisie or alerte %}Aucun résultat pour ces critères.{% else %}Les articles du magasin apparaîtront ici.{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/inventory/templates/inventory/article_detail.html`

*116 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}{{ article.reference }}{% endblock %}
{% block entete %}Stock{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'inventory:articles' %}" class="underline-offset-2 hover:underline">Stock</a>
    <span aria-hidden="true">/</span> {{ article.reference }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{{ article.reference }}</h1>
      {% if article.sous_seuil %}
        {% if article.quantite == 0 %}{% badge "RUPTURE" "Rupture" %}{% else %}{% badge "STOCK_BAS" "Stock bas" %}{% endif %}
      {% endif %}
    </div>
    {% if peut_modifier %}
      <a href="{% url 'inventory:article_modifier' article.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ article.designation }}</p>

  <dl class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">En stock</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ article.quantite }}</dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Seuil minimal</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{% if article.seuil_minimal %}{{ article.seuil_minimal }}{% else %}<span class="text-base font-medium text-slate-600">Aucun</span>{% endif %}</dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">PUMP</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ article.pump|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Valeur</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ article.valeur_stock|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
  </dl>

  <div class="mt-6 grid gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-fiche">
        <h2 id="titre-fiche" class="text-base font-semibold text-slate-900">Fiche</h2>
        <dl class="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Catégorie</dt><dd class="mt-0.5 font-medium text-slate-900">{{ article.categorie|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Emplacement</dt><dd class="mt-0.5 font-medium text-slate-900">{{ article.emplacement|default:"—" }}</dd></div>
        </dl>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-journal">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 id="titre-journal" class="text-base font-semibold text-slate-900">Derniers mouvements</h2>
          <a href="{% url 'inventory:mouvements' %}?q={{ article.reference|urlencode }}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Tout le journal</a>
        </div>
        {% if mouvements %}
          <div class="mt-4 overflow-x-auto">
            <table class="min-w-full divide-y divide-slate-200 text-sm">
              <caption class="sr-only">Derniers mouvements de l'article</caption>
              <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                <tr>
                  <th scope="col" class="py-2 pr-4">Date</th>
                  <th scope="col" class="px-4 py-2">Type</th>
                  <th scope="col" class="px-4 py-2 text-right">Variation</th>
                  <th scope="col" class="px-4 py-2 text-right">Stock après</th>
                  <th scope="col" class="px-4 py-2">Détail</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                {% for m in mouvements %}
                  <tr>
                    <td class="whitespace-nowrap py-2 pr-4 text-slate-700">{{ m.date_mouvement|date:"d/m/Y H:i" }}</td>
                    <td class="whitespace-nowrap px-4 py-2">{% badge m.type_mouvement m.get_type_mouvement_display %}</td>
                    <td class="whitespace-nowrap px-4 py-2 text-right font-medium {% if m.variation > 0 %}text-emerald-800{% else %}text-slate-900{% endif %}">{{ m.variation|stringformat:"+d" }}</td>
                    <td class="whitespace-nowrap px-4 py-2 text-right text-slate-700">{{ m.quantite_apres }}</td>
                    <td class="px-4 py-2 text-slate-700">
                      {% if m.ordre_reparation %}<a href="{% url 'garage:detail' m.ordre_reparation.pk %}" class="font-medium text-marque-700 underline-offset-2 hover:underline">{{ m.ordre_reparation.numero }}</a>{% endif %}
                      {% if m.motif %}{{ m.motif }}{% endif %}
                      {% if m.type_mouvement == "ENTREE" %}achat à {{ m.prix_unitaire|floatformat:0|intcomma }} FCFA{% endif %}
                      {% if m.acteur %}<span class="text-xs text-slate-500">· {{ m.acteur.get_full_name|default:m.acteur.username }}</span>{% endif %}
                    </td>
                  </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        {% else %}
          <p class="mt-3 text-sm text-slate-700">Aucun mouvement pour cet article. Enregistrez une entrée d'achat pour alimenter le stock.</p>
        {% endif %}
      </section>
    </div>

    {% if peut_modifier %}
      <div class="space-y-6">
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-entree">
          <h2 id="titre-entree" class="text-base font-semibold text-slate-900">Entrée d'achat</h2>
          <p class="mt-1 text-xs text-slate-600">Le prix moyen pondéré (PUMP) est recalculé avec ce prix d'achat.</p>
          <form method="post" action="{% url 'inventory:entree' article.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_entree.quantite %}
            {% include "components/_champ.html" with champ=form_entree.prix_unitaire %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer l'entrée</button>
          </form>
        </section>

        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-ajustement">
          <h2 id="titre-ajustement" class="text-base font-semibold text-slate-900">Ajustement d'inventaire</h2>
          <p class="mt-1 text-xs text-slate-600">Corrige le stock après comptage. Le PUMP ne change pas.</p>
          <form method="post" action="{% url 'inventory:ajustement' article.pk %}" class="mt-4 space-y-4"
                data-confirm="Enregistrer cet ajustement de stock ? Il sera tracé dans le journal.">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_ajustement.variation %}
            {% include "components/_champ.html" with champ=form_ajustement.motif %}
            <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Enregistrer l'ajustement</button>
          </form>
        </section>
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

#### `apps/inventory/templates/inventory/article_form.html`

*38 lignes*

```django
{% extends "base.html" %}
{% block titre %}{{ titre }}{% endblock %}
{% block entete %}Stock{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'inventory:articles' %}" class="underline-offset-2 hover:underline">Stock</a>
    {% if article %}<span aria-hidden="true">/</span> <a href="{% url 'inventory:article_detail' article.pk %}" class="underline-offset-2 hover:underline">{{ article.reference }}</a>{% endif %}
    <span aria-hidden="true">/</span> {% if article %}Modifier{% else %}Nouvel article{% endif %}
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">{{ titre }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    {% if article %}La référence, la quantité et le PUMP ne se modifient pas ici : ils viennent de l'identité de l'article et des mouvements de stock.
    {% else %}L'article est créé avec un stock à 0 ; enregistrez ensuite une entrée d'achat pour l'alimenter.{% endif %}
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}
    <div class="grid gap-5 sm:grid-cols-2">
      {% if form.reference %}{% include "components/_champ.html" with champ=form.reference %}{% endif %}
      <div class="{% if not form.reference %}sm:col-span-2{% endif %}">{% include "components/_champ.html" with champ=form.designation %}</div>
      {% include "components/_champ.html" with champ=form.categorie %}
      {% include "components/_champ.html" with champ=form.emplacement %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.seuil_minimal %}</div>
    </div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% if article %}{% url 'inventory:article_detail' article.pk %}{% else %}{% url 'inventory:articles' %}{% endif %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">{{ bouton }}</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/inventory/templates/inventory/mouvement_list.html`

*78 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Journal des mouvements{% endblock %}
{% block entete %}Stock{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'inventory:articles' %}" class="underline-offset-2 hover:underline">Stock</a>
    <span aria-hidden="true">/</span> Journal des mouvements
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Journal des mouvements</h1>
  <p class="mt-1 text-sm text-slate-600">
    {{ paginator.count|default:0 }} mouvement{{ paginator.count|pluralize }} · le journal est immuable : une erreur se corrige par un ajustement.
  </p>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="Article, n° d'OR, motif…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="type" class="block text-sm font-medium text-slate-800">Type</label>
      <select id="type" name="type" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous</option>
        {% for code, libelle in types %}<option value="{{ code }}" {% if code == type_choisi %}selected{% endif %}>{{ libelle }}</option>{% endfor %}
      </select>
    </div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or type_choisi %}
      <a href="{% url 'inventory:mouvements' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if mouvements %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Journal des mouvements de stock</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Date</th>
            <th scope="col" class="px-4 py-3">Article</th>
            <th scope="col" class="px-4 py-3">Type</th>
            <th scope="col" class="px-4 py-3 text-right">Variation</th>
            <th scope="col" class="px-4 py-3 text-right">Stock après</th>
            <th scope="col" class="px-4 py-3 text-right">Prix unit.</th>
            <th scope="col" class="px-4 py-3">Détail</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for m in mouvements %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ m.date_mouvement|date:"d/m/Y H:i" }}</td>
              <td class="px-4 py-3"><a href="{% url 'inventory:article_detail' m.article.pk %}" class="font-semibold text-marque-700 underline-offset-2 hover:underline">{{ m.article.reference }}</a> <span class="text-slate-700">{{ m.article.designation }}</span></td>
              <td class="whitespace-nowrap px-4 py-3">{% badge m.type_mouvement m.get_type_mouvement_display %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium {% if m.variation > 0 %}text-emerald-800{% else %}text-slate-900{% endif %}">{{ m.variation|stringformat:"+d" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ m.quantite_apres }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ m.prix_unitaire|floatformat:0|intcomma }}</td>
              <td class="px-4 py-3 text-slate-700">
                {% if m.ordre_reparation %}<a href="{% url 'garage:detail' m.ordre_reparation.pk %}" class="font-medium text-marque-700 underline-offset-2 hover:underline">{{ m.ordre_reparation.numero }}</a>{% endif %}
                {% if m.motif %}{{ m.motif }}{% endif %}
                {% if m.acteur %}<span class="text-xs text-slate-500">· {{ m.acteur.get_full_name|default:m.acteur.username }}</span>{% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="font-semibold text-slate-900">Aucun mouvement trouvé</p>
      <p class="mt-1 text-sm text-slate-600">{% if recherche or type_choisi %}Aucun résultat pour ces critères.{% else %}Les entrées, sorties et ajustements apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/inventory/templates/inventory/_pieces_or.html`

*50 lignes*

```django
{% load humanize %}
<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-pieces">
  <h2 id="titre-pieces" class="text-base font-semibold text-slate-900">Pièces utilisées</h2>
  <p class="mt-1 text-xs text-slate-600">Chaque sortie est valorisée au prix moyen pondéré (PUMP) du moment.</p>

  {% if section.contexte.lignes %}
    <div class="mt-4 overflow-x-auto">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Pièces sorties du stock pour cet OR</caption>
        <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="py-2 pr-4">Pièce</th>
            <th scope="col" class="px-4 py-2 text-right">Quantité</th>
            <th scope="col" class="px-4 py-2 text-right">PUMP</th>
            <th scope="col" class="py-2 pl-4 text-right">Montant</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for ligne in section.contexte.lignes %}
            <tr>
              <td class="py-2 pr-4 text-slate-900"><span class="font-medium">{{ ligne.article.reference }}</span> · {{ ligne.article.designation }}</td>
              <td class="whitespace-nowrap px-4 py-2 text-right text-slate-700">{{ ligne.quantite }}</td>
              <td class="whitespace-nowrap px-4 py-2 text-right text-slate-700">{{ ligne.prix_unitaire|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap py-2 pl-4 text-right text-slate-900">{{ ligne.montant|floatformat:0|intcomma }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <p class="mt-3 text-sm text-slate-700">Aucune pièce sortie du stock pour cet OR.</p>
  {% endif %}

  <dl class="mt-4 space-y-1 border-t border-slate-100 pt-4 text-sm">
    <div class="flex justify-between"><dt class="text-slate-600">Pièces</dt><dd class="font-medium text-slate-900">{{ section.contexte.cout_pieces|floatformat:0|intcomma }} FCFA</dd></div>
    <div class="flex justify-between"><dt class="text-slate-600">Main-d'œuvre</dt><dd class="font-medium text-slate-900">{{ ordre.cout_main_oeuvre|floatformat:0|intcomma }} FCFA</dd></div>
    <div class="flex justify-between text-base"><dt class="font-semibold text-slate-900">Coût total</dt><dd class="font-bold text-slate-900">{{ section.contexte.cout_total|floatformat:0|intcomma }} FCFA</dd></div>
  </dl>

  {% if section.contexte.form_sortie %}
    <form method="post" action="{% url 'inventory:sortie_or' ordre.pk %}" class="mt-5 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-3">
      {% csrf_token %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=section.contexte.form_sortie.article %}</div>
      {% include "components/_champ.html" with champ=section.contexte.form_sortie.quantite %}
      <div class="sm:col-span-3 flex justify-end">
        <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Sortir du stock</button>
      </div>
    </form>
  {% endif %}
</section>
```

## Étape 3 — Tests et compilation des styles

#### `apps/inventory/tests/test_stock_views.py`

*549 lignes* — Écrans du stock : articles, fiche, entrées, ajustements, journal.

```python
"""Écrans du stock : articles, fiche, entrées, ajustements, journal."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.garage import services as garage_services
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services
from apps.inventory.models import Article, MouvementStock, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [(m.level_tag, str(m)) for m in reponse.context["messages"]]


def _approvisionne(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


def _ordre():
    from apps.fleet.tests.factories import VehiculeFactory

    return garage_services.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )


def _detail(article):
    return reverse("inventory:article_detail", args=[article.pk])


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_stock_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)
    article = ArticleFactory()

    assert client.get(reverse("inventory:articles")).status_code == 200
    assert client.get(_detail(article)).status_code == 200
    assert client.get(reverse("inventory:mouvements")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_stock_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)
    article = ArticleFactory()

    for nom, args in (
        ("inventory:articles", []),
        ("inventory:article_detail", [article.pk]),
        ("inventory:article_creer", []),
        ("inventory:article_modifier", [article.pk]),
        ("inventory:mouvements", []),
    ):
        assert client.get(reverse(nom, args=args)).status_code == 403, nom


def test_la_direction_est_en_lecture_seule_sur_le_stock(client):
    _connecte(client, Role.DIRECTION)
    article = _approvisionne(10)

    assert client.get(reverse("inventory:article_creer")).status_code == 403
    assert client.get(reverse("inventory:article_modifier", args=[article.pk])).status_code == 403
    assert client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "5", "prix_unitaire": "900"}
    ).status_code == 403
    assert client.post(
        reverse("inventory:ajustement", args=[article.pk]), {"variation": "-3", "motif": "x"}
    ).status_code == 403
    article.refresh_from_db()
    assert article.quantite == 10


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("inventory:articles"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_stock_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/stock/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/stock/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_articles_et_les_indicateurs(client):
    _connecte(client, Role.PARCAUTO)
    _approvisionne(10, "1000", reference="FR-1", designation="Plaquettes", categorie="Freinage")
    _approvisionne(4, "2500", reference="FI-2", designation="Filtre", seuil_minimal=5)

    reponse = client.get(reverse("inventory:articles"))
    contenu = reponse.content.decode().replace("\xa0", " ").replace(" ", " ")

    assert "FR-1" in contenu and "Plaquettes" in contenu and "Freinage" in contenu
    assert reponse.context["valeur_totale"] == Decimal("20000.00")
    assert "20 000 FCFA" in contenu
    assert reponse.context["nombre_sous_seuil"] == 1
    assert "Stock bas" in contenu


def test_la_liste_distingue_rupture_et_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    epuise = _approvisionne(2, seuil_minimal=3)
    services.ajuster_stock(epuise, variation=-2, motif="Vol")
    _approvisionne(3, seuil_minimal=5)

    contenu = client.get(reverse("inventory:articles")).content.decode()

    assert "Rupture" in contenu and "Stock bas" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun article trouvé" in client.get(reverse("inventory:articles")).content.decode()


def test_la_liste_filtre_par_texte_categorie_et_seuil(client):
    _connecte(client, Role.PARCAUTO)
    moteur = _approvisionne(10, reference="MO-1", categorie="Moteur")
    bas = _approvisionne(1, reference="FR-1", categorie="Freinage", seuil_minimal=5)

    par_texte = client.get(reverse("inventory:articles"), {"q": "mo-1"})
    par_categorie = client.get(reverse("inventory:articles"), {"categorie": "Moteur"})
    sous_seuil = client.get(reverse("inventory:articles"), {"alerte": "1"})

    assert list(par_texte.context["articles"]) == [moteur]
    assert list(par_categorie.context["articles"]) == [moteur]
    assert list(sous_seuil.context["articles"]) == [bas]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        ArticleFactory()

    assert len(client.get(reverse("inventory:articles"), {"page": 2}).context["articles"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_article(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        ArticleFactory()

    with django_assert_max_num_queries(12):
        client.get(reverse("inventory:articles"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="<script>alert(1)</script>")

    for url in (reverse("inventory:articles"), _detail(article)):
        contenu = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in contenu
        assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_les_indicateurs_et_le_journal(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000", reference="PLQ-1", emplacement="Rayon A2")
    ordre = _ordre()
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    services.ajuster_stock(article, variation=-1, motif="Pièce cassée")

    reponse = client.get(_detail(article))
    contenu = reponse.content.decode()

    assert "Rayon A2" in contenu
    assert ordre.numero in contenu and reverse("garage:detail", args=[ordre.pk]) in contenu
    assert "Pièce cassée" in contenu
    assert "achat à" in contenu
    assert [m.variation for m in reponse.context["mouvements"]] == [-1, -3, 10]


def test_la_fiche_propose_les_formulaires_au_parc_auto_seulement(client):
    article = _approvisionne(10)
    _connecte(client, Role.PARCAUTO)
    page = client.get(_detail(article)).content.decode()
    assert reverse("inventory:entree", args=[article.pk]) in page
    assert reverse("inventory:ajustement", args=[article.pk]) in page

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    page = direction.get(_detail(article)).content.decode()
    assert reverse("inventory:entree", args=[article.pk]) not in page
    assert reverse("inventory:article_modifier", args=[article.pk]) not in page


def test_la_fiche_d_un_article_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("inventory:article_detail", args=[999999])).status_code == 404


def test_la_fiche_sans_mouvement_invite_a_enregistrer_une_entree(client):
    _connecte(client, Role.PARCAUTO)

    assert "entrée d'achat" in client.get(_detail(ArticleFactory())).content.decode()


# --- création et modification ---


def _donnees_article(**surcharges):
    donnees = {
        "reference": "fr-0012",
        "designation": "Plaquettes de frein",
        "categorie": "Freinage",
        "emplacement": "Rayon A1",
        "seuil_minimal": "4",
    }
    donnees.update(surcharges)
    return donnees


def test_creer_un_article(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article(), follow=True)

    article = Article.objects.get()
    assert reponse.redirect_chain[-1][0] == _detail(article)
    assert (article.reference, article.seuil_minimal, article.quantite) == ("FR-0012", 4, 0)
    assert any("FR-0012" in texte and "entrée d'achat" in texte for _, texte in _messages(reponse))


def test_creer_un_doublon_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.PARCAUTO)
    ArticleFactory(reference="FR-0012")

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article())

    assert reponse.status_code == 200
    assert "déjà utilisée" in reponse.content.decode()
    assert Article.objects.count() == 1


@pytest.mark.parametrize(
    "champ", [{"reference": ""}, {"designation": ""}, {"seuil_minimal": "-1"}, {"seuil_minimal": "abc"}]
)
def test_creer_avec_des_donnees_invalides_est_refuse(client, champ):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("inventory:article_creer"), _donnees_article(**champ))

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert Article.objects.count() == 0


def test_le_formulaire_de_modification_est_prerempli_sans_la_reference(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="Ancien", seuil_minimal=7)

    reponse = client.get(reverse("inventory:article_modifier", args=[article.pk]))

    assert reponse.context["form"].initial["designation"] == "Ancien"
    assert "reference" not in reponse.context["form"].fields


def test_modifier_un_article(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    client.post(
        reverse("inventory:article_modifier", args=[article.pk]),
        {"designation": "Disques", "categorie": "Freinage", "emplacement": "B1", "seuil_minimal": "2"},
    )

    article.refresh_from_db()
    assert (article.designation, article.seuil_minimal) == ("Disques", 2)
    assert (article.quantite, article.pump) == (10, Decimal("1000.00"))


def test_modifier_avec_une_designation_vide_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = ArticleFactory(designation="Ancien")

    reponse = client.post(
        reverse("inventory:article_modifier", args=[article.pk]),
        {"designation": "", "seuil_minimal": "0"},
    )

    article.refresh_from_db()
    assert reponse.context["form"].errors and article.designation == "Ancien"


def test_modifier_un_article_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("inventory:article_modifier", args=[999999])).status_code == 404


# --- entrée d'achat ---


def test_enregistrer_une_entree_recalcule_le_pump_et_le_dit(client):
    utilisateur = _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]),
        {"quantite": "10", "prix_unitaire": "2000"},
        follow=True,
    )

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (20, Decimal("1500.00"))
    dernier = MouvementStock.objects.filter(type_mouvement=TypeMouvement.ENTREE).latest("pk")
    assert dernier.acteur == utilisateur
    assert any(
        "Stock : 20" in texte and "1 500 FCFA" in texte.replace(" ", " ")
        for _, texte in _messages(reponse)
    )


@pytest.mark.parametrize(
    "donnees",
    [
        {"quantite": "0", "prix_unitaire": "100"},
        {"quantite": "-3", "prix_unitaire": "100"},
        {"quantite": "x", "prix_unitaire": "100"},
        {"quantite": "1", "prix_unitaire": ""},
        {"quantite": "1", "prix_unitaire": "-5"},
    ],
)
def test_une_entree_invalide_est_refusee_par_le_formulaire(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    client.post(reverse("inventory:entree", args=[article.pk]), donnees)

    article.refresh_from_db()
    assert article.quantite == 10


def test_un_prix_d_achat_nul_est_refuse_par_le_service_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]),
        {"quantite": "1", "prix_unitaire": "0"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 10
    assert any("strictement positif" in texte for _, texte in _messages(reponse))


# --- ajustement d'inventaire ---


def test_ajuster_le_stock_a_la_hausse(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, "1000")

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "3", "motif": "Comptage annuel"},
        follow=True,
    )

    article.refresh_from_db()
    assert (article.quantite, article.pump) == (13, Decimal("1000.00"))
    assert any("+3" in texte for _, texte in _messages(reponse))
    assert MouvementStock.objects.filter(motif="Comptage annuel").exists()


def test_un_ajustement_qui_atteint_le_seuil_affiche_l_alerte_de_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "-5", "motif": "Pièces cassées"},
        follow=True,
    )

    niveaux = _messages(reponse)
    assert any(niveau == "warning" and "Stock bas" in texte for niveau, texte in niveaux)


@pytest.mark.parametrize(
    "donnees",
    [
        {"variation": "0", "motif": "x"},
        {"variation": "5", "motif": ""},
        {"variation": "5", "motif": "   "},
        {"variation": "abc", "motif": "x"},
    ],
)
def test_un_ajustement_invalide_est_refuse(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    client.post(reverse("inventory:ajustement", args=[article.pk]), donnees)

    article.refresh_from_db()
    assert article.quantite == 10
    assert MouvementStock.objects.filter(type_mouvement=TypeMouvement.AJUSTEMENT).count() == 0


def test_un_ajustement_qui_rendrait_le_stock_negatif_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(2)

    reponse = client.post(
        reverse("inventory:ajustement", args=[article.pk]),
        {"variation": "-3", "motif": "Erreur"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 2
    assert any("négatif" in texte for _, texte in _messages(reponse))


def test_les_actions_de_stock_refusent_le_get_et_un_article_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10)

    assert client.get(reverse("inventory:entree", args=[article.pk])).status_code == 405
    assert client.get(reverse("inventory:ajustement", args=[article.pk])).status_code == 405
    assert client.post(reverse("inventory:entree", args=[999999]), {}).status_code == 404
    assert client.post(reverse("inventory:ajustement", args=[999999]), {}).status_code == 404


# --- alerte de seuil à la sortie de pièces ---


def test_une_sortie_qui_atteint_le_seuil_affiche_l_alerte_de_stock_bas(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "5"},
        follow=True,
    )

    assert any(niveau == "warning" and article.reference in texte for niveau, texte in _messages(reponse))


def test_une_sortie_au_dessus_du_seuil_n_affiche_pas_d_alerte(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(10, seuil_minimal=5)

    reponse = client.post(
        reverse("inventory:sortie_or", args=[_ordre().pk]),
        {"article": article.pk, "quantite": "2"},
        follow=True,
    )

    assert not any(niveau == "warning" for niveau, _ in _messages(reponse))


# --- journal ---


def test_le_journal_liste_et_filtre_les_mouvements(client):
    _connecte(client, Role.DIRECTION)
    article = _approvisionne(10, reference="PLQ-7")
    services.sortir_pour_or(article, quantite=2, ordre=_ordre())
    services.ajuster_stock(article, variation=-1, motif="Casse")

    tous = client.get(reverse("inventory:mouvements"))
    sorties = client.get(reverse("inventory:mouvements"), {"type": "SORTIE"})
    par_motif = client.get(reverse("inventory:mouvements"), {"q": "casse"})

    assert len(tous.context["mouvements"]) == 3
    assert [m.type_mouvement for m in sorties.context["mouvements"]] == ["SORTIE"]
    assert [m.motif for m in par_motif.context["mouvements"]] == ["Casse"]


def test_le_journal_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun mouvement trouvé" in client.get(reverse("inventory:mouvements")).content.decode()


def test_le_journal_est_pagine_par_30(client):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(1)
    for _ in range(30):
        services.ajuster_stock(article, variation=1, motif="Comptage")

    page2 = client.get(reverse("inventory:mouvements"), {"page": 2})

    assert len(page2.context["mouvements"]) == 1


def test_le_journal_n_effectue_pas_une_requete_par_mouvement(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    article = _approvisionne(1)
    ordre = _ordre()
    for _ in range(10):
        services.ajuster_stock(article, variation=1, motif="Comptage")
    services.sortir_pour_or(article, quantite=2, ordre=ordre)

    with django_assert_max_num_queries(10):
        client.get(reverse("inventory:mouvements"))


def test_les_formulaires_du_stock_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    article = _approvisionne(10)

    assert client.post(reverse("inventory:article_creer"), _donnees_article()).status_code == 403
    assert client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "5", "prix_unitaire": "900"}
    ).status_code == 403
    assert client.post(
        reverse("inventory:ajustement", args=[article.pk]), {"variation": "-3", "motif": "x"}
    ).status_code == 403
    article.refresh_from_db()
    assert article.quantite == 10 and Article.objects.count() == 1
```

#### `apps/inventory/tests/test_views.py`

*251 lignes* — Bloc « Pièces utilisées » de la fiche d'un OR et sortie de pièces par l'écran.

```python
"""Bloc « Pièces utilisées » de la fiche d'un OR et sortie de pièces par l'écran."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.garage import services as garage_services
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services
from apps.inventory.models import MouvementStock, TypeMouvement

from .factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _ordre():
    from apps.fleet.tests.factories import VehiculeFactory

    return garage_services.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )


def _article(quantite=10, prix="1000", **surcharges):
    article = ArticleFactory(**surcharges)
    services.enregistrer_entree(article, quantite=quantite, prix_unitaire=Decimal(prix))
    return article


def _detail(client, ordre):
    return client.get(reverse("garage:detail", args=[ordre.pk]))


# --- lecture ---


def test_articles_en_stock_exclut_les_articles_epuises_et_est_trie():
    b, a = _article(reference="B-1"), _article(reference="A-1")
    ArticleFactory(reference="Z-0")  # jamais approvisionné

    assert list(services.articles_en_stock()) == [a, b]


def test_sorties_de_l_or_ne_liste_que_les_sorties_de_cet_or():
    article = _article()
    ordre, autre = _ordre(), _ordre()
    services.sortir_pour_or(article, quantite=2, ordre=ordre)
    services.sortir_pour_or(article, quantite=1, ordre=autre)
    services.ajuster_stock(article, variation=-1, motif="Casse")

    sorties = list(services.sorties_de_l_or(ordre))

    assert len(sorties) == 1 and sorties[0].variation == -2


# --- bloc dans la fiche de l'OR ---


def test_la_fiche_de_l_or_affiche_les_pieces_et_le_cout_total(client):
    _connecte(client, Role.PARCAUTO)
    article = _article(10, "1000", reference="PLQ-01", designation="Plaquettes de frein")
    ordre = _ordre()
    services.sortir_pour_or(article, quantite=3, ordre=ordre)
    garage_services.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    reponse = _detail(client, ordre)
    # Les espaces insécables des séparateurs de milliers sont normalisées.
    contenu = reponse.content.decode().replace(" ", " ").replace(" ", " ")

    assert "Pièces utilisées" in contenu
    assert "PLQ-01" in contenu and "Plaquettes de frein" in contenu
    assert "3 000" in contenu  # 3 x 1000 : montant de la ligne et total des pièces
    assert "45 000" in contenu  # main-d'œuvre
    assert "48 000" in contenu  # coût total
    bloc = reponse.context["sections"][0]["contexte"]
    assert bloc["cout_pieces"] == Decimal("3000.00")
    assert bloc["cout_total"] == Decimal("48000.00")
    assert bloc["lignes"][0]["quantite"] == 3
    assert bloc["lignes"][0]["montant"] == Decimal("3000.00")


def test_la_fiche_sans_sortie_le_dit(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ordre()

    assert "Aucune pièce sortie du stock" in _detail(client, ordre).content.decode()


def test_le_formulaire_de_sortie_n_est_propose_qu_au_parc_auto_sur_un_or_ouvert(client):
    ordre = _ordre()
    _article()
    _connecte(client, Role.PARCAUTO)
    url = reverse("inventory:sortie_or", args=[ordre.pk])
    assert url in _detail(client, ordre).content.decode()

    direction = Client()
    _connecte(direction, Role.DIRECTION)
    assert url not in _detail(direction, ordre).content.decode()
    assert "Pièces utilisées" in _detail(direction, ordre).content.decode()  # lecture seule

    garage_services.cloturer_or(ordre)
    assert url not in _detail(client, ordre).content.decode()


def test_le_choix_des_pieces_ne_propose_que_les_articles_en_stock(client):
    _connecte(client, Role.PARCAUTO)
    _article(reference="EN-STOCK")
    ArticleFactory(reference="EPUISE")
    ordre = _ordre()

    contenu = _detail(client, ordre).content.decode()

    assert "EN-STOCK" in contenu and "EPUISE" not in contenu


# --- sortie de pièces ---


def test_sortir_des_pieces_par_l_ecran(client):
    utilisateur = _connecte(client, Role.PARCAUTO)
    article = _article(10, "1000")
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "4"},
        follow=True,
    )

    article.refresh_from_db()
    mouvement = MouvementStock.objects.get(type_mouvement=TypeMouvement.SORTIE)
    assert article.quantite == 6
    assert (mouvement.variation, mouvement.ordre_reparation, mouvement.acteur) == (-4, ordre, utilisateur)
    assert reponse.redirect_chain[-1][0] == reverse("garage:detail", args=[ordre.pk])
    assert any(article.reference in m for m in _messages(reponse))


def test_sortir_plus_que_le_stock_est_refuse_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    article = _article(3)
    ordre = _ordre()

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "4"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 3
    assert any("Stock insuffisant" in m for m in _messages(reponse))


def test_sortir_sur_un_or_cloture_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    article = _article()
    ordre = _ordre()
    garage_services.cloturer_or(ordre)

    reponse = client.post(
        reverse("inventory:sortie_or", args=[ordre.pk]),
        {"article": article.pk, "quantite": "1"},
        follow=True,
    )

    article.refresh_from_db()
    assert article.quantite == 10
    assert any("clôturé" in m for m in _messages(reponse))


@pytest.mark.parametrize("donnees", [{"quantite": "0"}, {"quantite": "-2"}, {"quantite": "x"}, {"article": ""}])
def test_une_sortie_invalide_est_refusee_par_le_formulaire(client, donnees):
    _connecte(client, Role.PARCAUTO)
    article = _article()
    ordre = _ordre()
    envoi = {"article": article.pk, "quantite": "1"}
    envoi.update(donnees)

    client.post(reverse("inventory:sortie_or", args=[ordre.pk]), envoi)

    article.refresh_from_db()
    assert article.quantite == 10


def test_un_article_epuise_ne_peut_pas_etre_sorti(client):
    _connecte(client, Role.PARCAUTO)
    epuise = ArticleFactory()
    ordre = _ordre()

    client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": epuise.pk, "quantite": "1"})

    assert MouvementStock.objects.count() == 0


@pytest.mark.parametrize("role", [Role.DIRECTION, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_sortie_est_interdite_hors_parc_auto(client, role):
    _connecte(client, role)
    article = _article()
    ordre = _ordre()

    reponse = client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": article.pk, "quantite": "1"})

    article.refresh_from_db()
    assert reponse.status_code == 403 and article.quantite == 10


def test_la_sortie_refuse_le_get_et_un_or_inconnu(client):
    _connecte(client, Role.PARCAUTO)
    ordre = _ordre()

    assert client.get(reverse("inventory:sortie_or", args=[ordre.pk])).status_code == 405
    assert client.post(reverse("inventory:sortie_or", args=[999999]), {}).status_code == 404


def test_la_sortie_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    article = _article()
    ordre = _ordre()

    reponse = client.post(reverse("inventory:sortie_or", args=[ordre.pk]), {"article": article.pk, "quantite": "1"})

    article.refresh_from_db()
    assert reponse.status_code == 403 and article.quantite == 10


# --- gardes des blocs (défense en profondeur) ---


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_bloc_pieces_n_est_jamais_fourni_aux_roles_sans_acces(role):
    from types import SimpleNamespace

    from apps.inventory import sections

    assert sections.section_pieces(_ordre(), SimpleNamespace(role_effectif=role)) is None
```

#### `apps/notifications/tests/test_services.py`

*169 lignes* — Envoi, dédoublonnage et lecture des notifications.

```python
"""Envoi, dédoublonnage et lecture des notifications."""

import pytest
from django.core import mail

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import services
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _notifier(destinataires, **surcharges):
    donnees = dict(categorie=CategorieNotification.STOCK, titre="Stock bas", message="Détail")
    donnees.update(surcharges)
    return services.notifier(destinataires, **donnees)


def test_une_notification_par_destinataire_avec_valeurs_par_defaut():
    a, b = UserFactory(), UserFactory()

    creees = _notifier([a, b], url="/stock/")

    assert {n.destinataire for n in creees} == {a, b}
    notification = Notification.objects.get(destinataire=a)
    assert notification.niveau == NiveauNotification.INFO
    assert notification.lue_le is None and not notification.est_lue
    assert notification.url == "/stock/"


def test_les_doublons_les_vides_et_les_inactifs_sont_ignores():
    actif = UserFactory()
    inactif = UserFactory(is_active=False)

    creees = _notifier([actif, actif, None, inactif])

    assert [n.destinataire for n in creees] == [actif]
    assert Notification.objects.count() == 1


def test_le_titre_est_tronque_a_la_longueur_du_champ():
    creees = _notifier([UserFactory()], titre="x" * 500)

    assert len(creees[0].titre) == 200


def test_une_cle_d_unicite_n_envoie_qu_une_fois_par_destinataire():
    a, b = UserFactory(), UserFactory()

    premiere = _notifier([a], cle="doc:1")
    deuxieme = _notifier([a, b], cle="doc:1")

    assert len(premiere) == 1
    assert [n.destinataire for n in deuxieme] == [b]  # a l'a déjà reçue
    assert Notification.objects.filter(cle_unicite="doc:1").count() == 2


def test_sans_cle_chaque_appel_cree_une_notification():
    a = UserFactory()

    _notifier([a])
    _notifier([a])

    assert Notification.objects.filter(destinataire=a).count() == 2


def test_utilisateurs_du_role_ne_liste_que_les_comptes_actifs():
    rh = UserFactory(role=Role.RH)
    UserFactory(role=Role.RH, is_active=False)
    UserFactory(role=Role.FINANCES)

    assert list(services.utilisateurs_du_role(Role.RH)) == [rh]
    assert services.utilisateurs_du_role(Role.RH, Role.FINANCES).count() == 2


# --- lecture ---


def test_comptage_et_marquage_de_lecture():
    a, b = UserFactory(), UserFactory()
    _notifier([a])
    _notifier([a])
    _notifier([b])

    assert services.nombre_non_lues(a) == 2
    premiere = services.notifications_de(a).first()
    services.marquer_lue(premiere)
    assert services.nombre_non_lues(a) == 1
    premiere.refresh_from_db()
    assert premiere.est_lue
    ancienne_date = premiere.lue_le
    services.marquer_lue(premiere)  # idempotent
    premiere.refresh_from_db()
    assert premiere.lue_le == ancienne_date

    assert services.marquer_toutes_lues(a) == 1
    assert services.nombre_non_lues(a) == 0
    assert services.nombre_non_lues(b) == 1  # celles des autres sont intactes


def test_le_filtre_non_lues():
    a = UserFactory()
    _notifier([a])
    _notifier([a])
    services.marquer_lue(services.notifications_de(a).first())

    assert services.notifications_de(a).count() == 2
    assert services.notifications_de(a, non_lues=True).count() == 1


# --- e-mail ---


def test_l_email_n_est_pas_envoye_quand_il_est_desactive(settings, django_capture_on_commit_callbacks):
    settings.NOTIFICATIONS_EMAIL = False

    with django_capture_on_commit_callbacks(execute=True):
        _notifier([UserFactory(email="a@ex.ci")])

    assert mail.outbox == []


def test_l_email_est_envoye_apres_validation_avec_le_lien_absolu(
    settings, django_capture_on_commit_callbacks
):
    settings.NOTIFICATIONS_EMAIL = True
    settings.NOTIFICATIONS_URL_BASE = "https://erp.example.ci/"
    destinataire = UserFactory(email="awa@example.ci")

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([destinataire], titre="Stock bas : frein", url="/stock/articles/3/")
        assert mail.outbox == []  # jamais avant la validation de la transaction

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["awa@example.ci"] and message.subject == "Stock bas : frein"
    assert "Ouvrir : https://erp.example.ci/stock/articles/3/" in message.body
    creees[0].refresh_from_db()
    assert creees[0].email_envoye


def test_pas_d_email_sans_adresse(settings, django_capture_on_commit_callbacks):
    settings.NOTIFICATIONS_EMAIL = True

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([UserFactory(email="")])

    assert mail.outbox == []
    assert not creees[0].email_envoye


def test_un_email_en_echec_ne_fait_pas_echouer_l_operation(
    settings, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    settings.NOTIFICATIONS_EMAIL = True

    def panne(*args, **kwargs):
        raise OSError("serveur SMTP injoignable")

    monkeypatch.setattr(services, "send_mail", panne)

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([UserFactory(email="a@ex.ci")])

    assert Notification.objects.count() == 1  # la notification reste dans l'application
    creees[0].refresh_from_db()
    assert not creees[0].email_envoye
    assert "par e-mail impossible" in caplog.text
```

#### `apps/notifications/tests/test_views.py`

*178 lignes* — Page « Notifications » et cloche de l'en-tête.

```python
"""Page « Notifications » et cloche de l'en-tête."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import services
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _notifier(utilisateur, titre="Stock bas", **surcharges):
    donnees = dict(categorie=CategorieNotification.STOCK, titre=titre, message="Détail")
    donnees.update(surcharges)
    return services.notifier([utilisateur], **donnees)[0]


@pytest.mark.parametrize("role", list(Role.values))
def test_tous_les_roles_ont_leur_page_de_notifications(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("notifications:liste")).status_code == 200


def test_la_page_exige_la_connexion(client):
    assert client.get(reverse("notifications:liste")).status_code == 302


def test_chacun_ne_voit_que_ses_notifications(client):
    moi, autre = UserFactory(), UserFactory()
    _notifier(moi, "Pour moi")
    _notifier(autre, "Pour un autre")
    client.force_login(moi)

    texte = client.get(reverse("notifications:liste")).content.decode()

    assert "Pour moi" in texte and "Pour un autre" not in texte


def test_le_filtre_non_lues(client):
    moi = UserFactory()
    lue = _notifier(moi, "Déjà lue")
    _notifier(moi, "Nouvelle")
    services.marquer_lue(lue)
    client.force_login(moi)

    toutes = client.get(reverse("notifications:liste")).content.decode()
    non_lues = client.get(reverse("notifications:liste"), {"non_lues": "1"}).content.decode()

    assert "Déjà lue" in toutes and "Nouvelle" in toutes
    assert "Déjà lue" not in non_lues and "Nouvelle" in non_lues


def test_la_page_vide_est_expliquee(client):
    client.force_login(UserFactory())

    assert "Aucune notification" in client.get(reverse("notifications:liste")).content.decode()


def test_ouvrir_une_notification_la_marque_lue_et_redirige_vers_son_lien(client):
    moi = UserFactory()
    notification = _notifier(moi, url="/stock/articles/3/")
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse.status_code == 302 and reponse["Location"] == "/stock/articles/3/"
    notification.refresh_from_db()
    assert notification.est_lue


def test_sans_lien_on_revient_a_la_liste(client):
    moi = UserFactory()
    notification = _notifier(moi)
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse["Location"] == reverse("notifications:liste")


@pytest.mark.parametrize("lien", ["https://pirate.example/", "//pirate.example/", "javascript:alert(1)"])
def test_un_lien_externe_n_est_jamais_suivi(client, lien):
    moi = UserFactory()
    notification = _notifier(moi, url=lien)
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse["Location"] == reverse("notifications:liste")


def test_on_ne_peut_pas_lire_la_notification_d_un_autre(client):
    autre = UserFactory()
    notification = _notifier(autre)
    client.force_login(UserFactory())

    assert client.post(reverse("notifications:lire", args=[notification.pk])).status_code == 404
    notification.refresh_from_db()
    assert not notification.est_lue


def test_tout_marquer_comme_lu_ne_touche_que_mes_notifications(client):
    moi, autre = UserFactory(), UserFactory()
    _notifier(moi)
    _notifier(moi)
    _notifier(autre)
    client.force_login(moi)

    client.post(reverse("notifications:tout_lire"))

    assert services.nombre_non_lues(moi) == 0
    assert services.nombre_non_lues(autre) == 1


def test_les_actions_sont_en_post_avec_csrf():
    moi = UserFactory()
    notification = _notifier(moi)
    client = Client(enforce_csrf_checks=True)
    client.force_login(moi)

    assert client.get(reverse("notifications:tout_lire")).status_code == 405
    assert client.get(reverse("notifications:lire", args=[notification.pk])).status_code == 405
    assert client.post(reverse("notifications:tout_lire")).status_code == 403
    assert client.post(reverse("notifications:lire", args=[notification.pk])).status_code == 403
    assert services.nombre_non_lues(moi) == 1


def test_les_textes_sont_echappes(client):
    moi = UserFactory()
    _notifier(moi, "<script>alert(1)</script>", message="<img src=x onerror=alert(2)>")
    client.force_login(moi)

    texte = client.get(reverse("notifications:liste")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte


def test_les_pages_du_site_affichent_le_nombre_de_notifications_non_lues(client):
    moi = UserFactory(role=Role.DIRECTION)
    _notifier(moi)
    _notifier(moi)
    client.force_login(moi)

    texte = client.get(reverse("home")).content.decode()

    assert "Notifications : 2 non lues" in texte


def test_la_cloche_disparait_de_la_page_de_connexion_sans_erreur(client):
    assert client.get(reverse("accounts:login")).status_code == 200


def test_la_liste_est_paginee_et_tolere_une_page_invalide(client):
    moi = UserFactory()
    for i in range(25):
        _notifier(moi, f"Notification {i}")
    client.force_login(moi)

    page_1 = client.get(reverse("notifications:liste"))
    inconnue = client.get(reverse("notifications:liste"), {"page": 99})

    assert len(page_1.context["notifications"]) == 20
    assert inconnue.status_code == 200 and inconnue.context["page_obj"].number == 2


def test_la_liste_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    moi = UserFactory()
    for i in range(15):
        _notifier(moi, f"Notification {i}")
    client.force_login(moi)

    with django_assert_max_num_queries(8):
        assert client.get(reverse("notifications:liste")).status_code == 200
    assert Notification.objects.count() == 15
```

Trois fichiers de `notifications` (`test_services.py`, `test_views.py`) sont aussi présentés ici : la cloche et la
page des notifications se testent sur des pages complètes, et ces pages ont besoin du stock.

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
python -m pytest apps/inventory/tests/test_stock_views.py apps/inventory/tests/test_views.py apps/notifications/tests/test_services.py apps/notifications/tests/test_views.py -q --no-cov
```

**Résultat attendu :** `114 passed` (pour les 4 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur :**

1. **`demo_parcauto`** : le menu affiche **Stock**. « Nouvel article » : référence `PN-0455`, désignation « Pneu
   315/80 R22.5 », **seuil 4** (si vous avez fait l'essai du chapitre 11, il existe déjà).
2. Sur la fiche, **Entrée d'achat** : 10 pièces à 1 000, puis 10 à 2 000 : le **PUMP** passe à 1 500 et la valeur
   totale du stock s'affiche sur la liste.
3. Ouvrez un **OR ouvert** (chapitre 22) : le bloc **Pièces utilisées** est apparu. Faites une **sortie de 17
   pièces** : il reste 3 pièces, **sous le seuil de 4** : un message d'alerte s'affiche et la **cloche de
   `demo_parcauto`** compte une notification.
4. Faites un **ajustement** sans motif : refusé (« motif obligatoire »). Avec un motif : accepté et tracé dans le
   journal des mouvements.
5. Essayez de faire une sortie sur un OR **clôturé** : refusée.

## Ce qu'il faut retenir

- Les **blocs fournis à d'autres pages** s'activent par simple présence du gabarit.
- Un service peut **renvoyer un avertissement** à la vue sans lever d'erreur : l'action a réussi, mais l'utilisateur
  doit le savoir.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 23 : écrans du stock (articles, mouvements, pièces d'un OR)"
```

---

[← Chapitre 22](22-ecrans-garage.md) · [Sommaire](README.md) · [Chapitre 24 →](24-ecrans-carburant.md)
