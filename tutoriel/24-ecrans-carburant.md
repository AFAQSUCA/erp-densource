# Chapitre 24 — Écrans : carburant

> 9 fichier(s) dans ce chapitre, 1674 lignes de code.

## Ce que vous allez construire

Les **écrans du carburant** (Parc Auto et ADMIN : saisie ; Direction : lecture).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des pleins | `/carburant/` | filtres (camion, chauffeur, période, type d'alerte, texte), consommation moyenne, nombre de pleins à surveiller |
| **Saisir un plein** | `/carburant/nouveau/` | avec les alertes et la **confirmation d'une saisie suspecte** |
| **Analyse** | `/carburant/analyse/` | consommation par camion et par chauffeur |

## Prérequis

- Chapitres 1 à 23 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le dialogue de confirmation d'un service** : `services.enregistrer_plein` lève `SaisieSuspecte` (chapitre 12).
  La vue l'attrape, **réaffiche le formulaire avec les valeurs saisies** et un avertissement, et propose un
  bouton **« Confirmer »** qui renvoie le même formulaire avec `confirmer_alerte_saisie=True`. Rien n'est
  enregistré tant que la personne n'a pas corrigé ou confirmé.
- **Des messages selon le résultat** : après l'enregistrement, un message *warning* signale une alerte jaune ou
  rouge, une anomalie de consommation.
- **Des nombres à la française** dans les messages : `nombre(...)` et `pourcentage_signe(...)` (chapitre 2), jamais
  un `f"{valeur}"`.
- **Un formulaire de filtre à plusieurs champs**, dont des dates : une période inversée (fin avant début) est
  signalée plutôt qu'ignorée.

## Étape 1 — Formulaires, vues, adresses

#### `apps/fuel/forms.py`

*106 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin
from apps.drivers import services as drivers_services
from apps.fleet import services as fleet_services


def _libelle_camion(v):
    return f"{v.immatriculation} - {v.marque} {v.modele}"


def _libelle_chauffeur(c):
    return f"{c.personnel.prenom} {c.personnel.nom} ({c.personnel.matricule})"


class PleinForm(StyleTailwindMixin, forms.Form):
    """Saisie d'un plein (cahier-des-charges.md:148-150)."""

    vehicule = forms.ModelChoiceField(label="Camion", queryset=None)
    chauffeur = forms.ModelChoiceField(label="Chauffeur", queryset=None)
    date_plein = forms.DateField(
        label="Date du plein", widget=forms.DateInput(attrs={"type": "date"})
    )
    station = forms.CharField(label="Station", max_length=100)
    quantite_litres = forms.DecimalField(
        label="Quantité (litres)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_unitaire = forms.DecimalField(
        label="Prix unitaire (FCFA / litre)", min_value=0, decimal_places=2, max_digits=10
    )
    km_compteur = forms.IntegerField(label="Kilométrage du compteur", min_value=0)
    numero_ticket = forms.CharField(label="N° de ticket / reçu", max_length=50)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = _libelle_camion
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur"].label_from_instance = _libelle_chauffeur

    def clean_date_plein(self):
        date_plein = self.cleaned_data["date_plein"]
        if date_plein > timezone.localdate():
            raise forms.ValidationError("La date du plein ne peut pas être dans le futur.")
        return date_plein


class FiltrePleinsForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste (GET). Une valeur invalide est simplement ignorée."""

    ALERTES = [
        ("", "Toutes"),
        ("A_SURVEILLER", "À surveiller (toutes alertes)"),
        ("JAUNE", "Alerte jaune (> +20 %)"),
        ("ROUGE", "Alerte rouge (> +40 %)"),
        ("ANOMALIE", "Anomalie (> 45 ou < 20 L/100 km)"),
        ("SAISIE", "Saisie suspecte confirmée"),
    ]

    q = forms.CharField(label="Rechercher", required=False)
    vehicule = forms.ModelChoiceField(label="Camion", queryset=None, required=False, empty_label="Tous")
    chauffeur = forms.ModelChoiceField(label="Chauffeur", queryset=None, required=False, empty_label="Tous")
    date_debut = forms.DateField(
        label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_fin = forms.DateField(
        label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    alerte = forms.ChoiceField(label="Alerte", choices=ALERTES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = _libelle_camion
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur"].label_from_instance = _libelle_chauffeur

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and debut > fin:
            self.add_error("date_fin", "La date de fin précède la date de début : période ignorée.")
            donnees.pop("date_debut", None)
        return donnees

    def criteres(self) -> dict:
        """Critères prêts pour ``services.rechercher_pleins``.

        ``is_valid()`` remplit ``cleaned_data`` avec les seuls champs valides : un
        paramètre d'URL invalide est donc ignoré au lieu de faire échouer la page.
        """
        self.is_valid()
        donnees = self.cleaned_data
        return {
            "recherche": donnees.get("q") or "",
            "vehicule": donnees.get("vehicule"),
            "chauffeur": donnees.get("chauffeur"),
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
            "alerte": donnees.get("alerte") or "",
        }
```

#### `apps/fuel/views.py`

*146 lignes* — Écrans du carburant : liste des pleins, saisie, analyse.

```python
"""Écrans du carburant : liste des pleins, saisie, analyse.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre, pourcentage_signe
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, services
from .exceptions import CarburantError, SaisieSuspecte
from .forms import FiltrePleinsForm, PleinForm
from .models import NiveauAlerte


class PleinListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "fuel/plein_list.html"
    context_object_name = "pleins"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltrePleinsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_pleins(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        criteres = self.get_filtre().criteres()
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(criteres.values()),
            consommation_moyenne=services.consommation_moyenne(
                vehicule=criteres["vehicule"], chauffeur=criteres["chauffeur"]
            ),
            nombre_a_surveiller=services.pleins_a_surveiller().count(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class PleinImprimerView(ImpressionListeMixin, PleinListView):
    """Rapport imprimable des pleins (mêmes filtres que la liste)."""

    titre_impression = "Carburant"
    colonnes = (
        ("Date", lambda p: p.date_plein.strftime("%d/%m/%Y")), ("Camion", "vehicule.immatriculation"),
        ("Chauffeur", lambda p: f"{p.chauffeur.personnel.prenom} {p.chauffeur.personnel.nom}"),
        ("Station", "station"), ("Litres", lambda p: f"{nombre(p.quantite_litres, 2)} L"),
        ("Prix unitaire", lambda p: f"{nombre(p.prix_unitaire)} FCFA"),
        ("Montant", lambda p: f"{nombre(p.quantite_litres * p.prix_unitaire)} FCFA"),
        ("Consommation", lambda p: f"{nombre(p.consommation, 1)} L/100 km" if p.consommation is not None else "—"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("vehicule"):
            morceaux.append(f"camion : {criteres['vehicule'].immatriculation}")
        if criteres.get("chauffeur"):
            morceaux.append(f"chauffeur : {criteres['chauffeur'].personnel.nom}")
        if criteres.get("date_debut"):
            morceaux.append(f"du {criteres['date_debut'].strftime('%d/%m/%Y')}")
        if criteres.get("date_fin"):
            morceaux.append(f"au {criteres['date_fin'].strftime('%d/%m/%Y')}")
        return " · ".join(morceaux)


class PleinCreateView(RoleRequiredMixin, FormView):
    """Saisie d'un plein.

    Si l'écart dépasse ±60 %, rien n'est enregistré : la page se réaffiche avec
    l'avertissement et un bouton « Confirmer » qui renvoie les mêmes valeurs
    (cahier-des-charges.md:155).
    """

    roles = permissions.MODIFICATION
    form_class = PleinForm
    template_name = "fuel/plein_form.html"

    def get_initial(self):
        return {"date_plein": timezone.localdate()}

    def form_valid(self, form):
        confirmer = self.request.POST.get("confirmer") == "1"
        try:
            plein = services.enregistrer_plein(
                **form.cleaned_data, confirmer_alerte_saisie=confirmer
            )
        except SaisieSuspecte as avertissement:
            return self.render_to_response(
                self.get_context_data(form=form, saisie_suspecte=avertissement)
            )
        except CarburantError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)

        if plein.consommation is None:
            messages.success(
                self.request,
                "Premier plein de ce camion enregistré : la consommation sera calculée dès le suivant.",
            )
        else:
            messages.success(
                self.request,
                f"Plein enregistré : {nombre(plein.consommation, 1)} L/100 km.",
            )
        self._signaler_les_alertes(plein)
        return redirect("fuel:liste")

    def _signaler_les_alertes(self, plein) -> None:
        if plein.niveau_alerte != NiveauAlerte.AUCUNE:
            messages.warning(
                self.request,
                f"Surconsommation {plein.get_niveau_alerte_display()} : "
                f"{pourcentage_signe(plein.ecart_pct)} % par rapport à la moyenne des derniers "
                f"pleins ({nombre(plein.moyenne_reference, 1)} L/100 km).",
            )
        if plein.anomalie:
            messages.warning(
                self.request,
                f"Anomalie : {nombre(plein.consommation, 1)} L/100 km est hors de la plage 20-45.",
            )


class AnalyseView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "fuel/analyse.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            consommation_flotte=services.consommation_moyenne(),
            par_vehicule=services.consommation_par_vehicule(),
            par_chauffeur=services.consommation_par_chauffeur(),
        )
        return contexte
```

#### `apps/fuel/urls.py`

*12 lignes*

```python
from django.urls import path

from . import views

app_name = "fuel"

urlpatterns = [
    path("", views.PleinListView.as_view(), name="liste"),
    path("imprimer/", views.PleinImprimerView.as_view(), name="imprimer"),
    path("nouveau/", views.PleinCreateView.as_view(), name="creer"),
    path("analyse/", views.AnalyseView.as_view(), name="analyse"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -23,4 +23,5 @@
     path("chauffeurs/", include("apps.drivers.urls")),
     path("garage/", include("apps.garage.urls")),
+    path("carburant/", include("apps.fuel.urls")),
     path("stock/", include("apps.inventory.urls")),
     path("audit/", include("apps.audit.urls")),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/fuel/templates/fuel
```

#### `apps/fuel/templates/fuel/plein_list.html`

*116 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Carburant{% endblock %}
{% block entete %}Carburant{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Carburant</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} plein{{ paginator.count|pluralize }}</p>
    </div>
    <div class="flex flex-wrap gap-3">
      <a href="{% url 'fuel:imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      <a href="{% url 'fuel:analyse' %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-chart-column" aria-hidden="true"></i> Analyse de la consommation
      </a>
      {% if peut_modifier %}
        <a href="{% url 'fuel:creer' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouveau plein
        </a>
      {% endif %}
    </div>
  </div>

  <dl class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <dt class="text-sm text-slate-600">Consommation moyenne{% if filtre.cleaned_data.vehicule or filtre.cleaned_data.chauffeur %} (selon le filtre){% else %} de la flotte{% endif %}</dt>
      <dd class="mt-1 text-2xl font-bold text-slate-900">
        {% if consommation_moyenne %}{{ consommation_moyenne|floatformat:1 }} <span class="text-sm font-medium text-slate-600">L/100 km</span>{% else %}<span class="text-base font-medium text-slate-600">Pas encore de donnée</span>{% endif %}
      </dd>
    </div>
    <div class="rounded-xl border p-4 shadow-sm {% if nombre_a_surveiller %}border-amber-300 bg-amber-50{% else %}border-slate-200 bg-white{% endif %}">
      <dt class="text-sm {% if nombre_a_surveiller %}text-amber-900{% else %}text-slate-600{% endif %}">Pleins à surveiller</dt>
      <dd class="mt-1 flex items-center gap-3 text-2xl font-bold text-slate-900">
        {{ nombre_a_surveiller }}
        {% if nombre_a_surveiller %}<a href="?alerte=A_SURVEILLER" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir la liste</a>{% endif %}
      </dd>
    </div>
  </dl>

  <form method="get" class="mt-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {% include "components/_champ.html" with champ=filtre.q %}
      {% include "components/_champ.html" with champ=filtre.vehicule %}
      {% include "components/_champ.html" with champ=filtre.chauffeur %}
      {% include "components/_champ.html" with champ=filtre.date_debut %}
      {% include "components/_champ.html" with champ=filtre.date_fin %}
      {% include "components/_champ.html" with champ=filtre.alerte %}
    </div>
    <div class="mt-4 flex items-center gap-3">
      <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
      {% if filtres_actifs %}<a href="{% url 'fuel:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
    </div>
  </form>

  {% if pleins %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des pleins de carburant</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Date</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Chauffeur</th>
            <th scope="col" class="hidden px-4 py-3 2xl:table-cell">Station</th>
            <th scope="col" class="px-4 py-3 text-right">Litres</th>
            <th scope="col" class="hidden px-4 py-3 text-right 2xl:table-cell">Montant</th>
            <th scope="col" class="hidden px-4 py-3 text-right xl:table-cell">Km compteur</th>
            <th scope="col" class="px-4 py-3 text-right">L/100 km</th>
            <th scope="col" class="px-4 py-3 text-right">Écart</th>
            <th scope="col" class="px-4 py-3">Alertes</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for plein in pleins %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ plein.date_plein|date:"d/m/Y" }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ plein.vehicule.immatriculation }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ plein.chauffeur.personnel.prenom }} {{ plein.chauffeur.personnel.nom }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 2xl:table-cell">{{ plein.station }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-800">{{ plein.quantite_litres|floatformat:"-1" }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-right text-slate-700 2xl:table-cell">{{ plein.montant_total|floatformat:0|intcomma }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-right text-slate-700 xl:table-cell">{{ plein.km_compteur|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">{% if plein.consommation %}{{ plein.consommation|floatformat:1 }}{% else %}<span class="font-normal text-slate-500">—</span>{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{% if plein.ecart_pct is not None %}{{ plein.ecart_pct|pourcentage_signe }} %{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  {% if plein.niveau_alerte == "JAUNE" %}{% badge "JAUNE" "Jaune" %}{% elif plein.niveau_alerte == "ROUGE" %}{% badge "ROUGE" "Rouge" %}{% endif %}
                  {% if plein.anomalie %}{% badge "ANOMALIE" "Anomalie" %}{% endif %}
                  {% if plein.alerte_saisie %}{% badge "SAISIE_SUSPECTE" "Saisie confirmée" %}{% endif %}
                  {% if plein.niveau_alerte == "AUCUNE" and not plein.anomalie and not plein.alerte_saisie %}<span class="text-slate-500">—</span>{% endif %}
                </div>
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
        <i class="fa-solid fa-gas-pump" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucun plein trouvé</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Les pleins saisis apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/fuel/templates/fuel/plein_form.html`

*68 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Nouveau plein{% endblock %}
{% block entete %}Carburant{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'fuel:liste' %}" class="underline-offset-2 hover:underline">Carburant</a>
    <span aria-hidden="true">/</span> Nouveau plein
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouveau plein</h1>
  <p class="mt-1 text-sm text-slate-600">
    La consommation se calcule à partir du plein précédent du même camion : saisissez les pleins dans l'ordre,
    avec un kilométrage qui augmente.
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}

    {% if saisie_suspecte %}
      <div role="alert" class="rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-950">
        <p class="font-semibold"><i class="fa-solid fa-triangle-exclamation mr-2" aria-hidden="true"></i>Vérifiez cette saisie avant de l'enregistrer</p>
        <p class="mt-2">
          Consommation calculée : <strong>{{ saisie_suspecte.consommation|floatformat:1 }} L/100 km</strong>,
          soit <strong>{{ saisie_suspecte.ecart_pct|pourcentage_signe }} %</strong> par rapport à la moyenne des
          derniers pleins de ce camion ({{ saisie_suspecte.moyenne|floatformat:1 }} L/100 km).
        </p>
        <p class="mt-2">
          Un écart aussi important vient souvent d'une erreur sur les <strong>litres</strong> ou sur le
          <strong>kilométrage</strong>. Corrigez les valeurs ci-dessous, ou confirmez si elles sont exactes :
          le plein sera alors enregistré avec la mention « saisie confirmée ».
        </p>
      </div>
    {% endif %}

    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.vehicule %}
      {% include "components/_champ.html" with champ=form.chauffeur %}
      {% include "components/_champ.html" with champ=form.date_plein %}
      {% include "components/_champ.html" with champ=form.station %}
      {% include "components/_champ.html" with champ=form.quantite_litres %}
      {% include "components/_champ.html" with champ=form.prix_unitaire %}
      {% include "components/_champ.html" with champ=form.km_compteur %}
      {% include "components/_champ.html" with champ=form.numero_ticket %}
    </div>

    <div class="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'fuel:liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      {% if saisie_suspecte %}
        <button type="submit" name="confirmer" value="1"
                class="rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-accent-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-600 focus-visible:ring-offset-2">
          Confirmer : les valeurs sont exactes
        </button>
      {% endif %}
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        {% if saisie_suspecte %}Enregistrer avec mes corrections{% else %}Enregistrer le plein{% endif %}
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/fuel/templates/fuel/analyse.html`

*93 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Analyse de la consommation{% endblock %}
{% block entete %}Carburant{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'fuel:liste' %}" class="underline-offset-2 hover:underline">Carburant</a>
    <span aria-hidden="true">/</span> Analyse
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Analyse de la consommation</h1>
  <p class="mt-1 text-sm text-slate-600">
    Consommation moyenne = total des litres ÷ total des kilomètres × 100, pondérée par la distance.
    Seuls les pleins dont la consommation a pu être calculée sont retenus.
  </p>

  <div class="mt-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:max-w-sm">
    <p class="text-sm text-slate-600">Moyenne de la flotte</p>
    <p class="mt-1 text-2xl font-bold text-slate-900">
      {% if consommation_flotte %}{{ consommation_flotte|floatformat:1 }} <span class="text-sm font-medium text-slate-600">L/100 km</span>{% else %}<span class="text-base font-medium text-slate-600">Pas encore de donnée</span>{% endif %}
    </p>
  </div>

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-camions">
      <h2 id="titre-camions" class="text-base font-semibold text-slate-900">Par camion</h2>
      {% if par_vehicule %}
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <caption class="sr-only">Consommation moyenne par camion</caption>
            <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th scope="col" class="py-2 pr-3">Camion</th>
                <th scope="col" class="px-3 py-2 text-right">Pleins</th>
                <th scope="col" class="px-3 py-2 text-right">Km</th>
                <th scope="col" class="px-3 py-2 text-right">L/100 km</th>
                <th scope="col" class="py-2 pl-3 text-right">Écart flotte</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              {% for g in par_vehicule %}
                <tr>
                  <th scope="row" class="whitespace-nowrap py-2 pr-3 text-left font-medium text-slate-900">{{ g.libelle }}</th>
                  <td class="px-3 py-2 text-right text-slate-700">{{ g.pleins }}</td>
                  <td class="whitespace-nowrap px-3 py-2 text-right text-slate-700">{{ g.distance|intcomma }}</td>
                  <td class="whitespace-nowrap px-3 py-2 text-right font-semibold text-slate-900">{{ g.consommation|floatformat:1 }}{% if g.anomalie %} {% badge "ANOMALIE" "Anomalie" %}{% endif %}</td>
                  <td class="whitespace-nowrap py-2 pl-3 text-right text-slate-700">{% if g.ecart_flotte_pct is not None %}{{ g.ecart_flotte_pct|pourcentage_signe }} %{% else %}—{% endif %}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      {% else %}
        <p class="mt-3 text-sm text-slate-700">Aucune consommation calculée pour l'instant.</p>
      {% endif %}
    </section>

    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-chauffeurs">
      <h2 id="titre-chauffeurs" class="text-base font-semibold text-slate-900">Par chauffeur</h2>
      {% if par_chauffeur %}
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <caption class="sr-only">Consommation moyenne par chauffeur</caption>
            <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr>
                <th scope="col" class="py-2 pr-3">Chauffeur</th>
                <th scope="col" class="px-3 py-2 text-right">Pleins</th>
                <th scope="col" class="px-3 py-2 text-right">Km</th>
                <th scope="col" class="px-3 py-2 text-right">L/100 km</th>
                <th scope="col" class="py-2 pl-3 text-right">Écart flotte</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              {% for g in par_chauffeur %}
                <tr>
                  <th scope="row" class="whitespace-nowrap py-2 pr-3 text-left font-medium text-slate-900">{{ g.libelle }}</th>
                  <td class="px-3 py-2 text-right text-slate-700">{{ g.pleins }}</td>
                  <td class="whitespace-nowrap px-3 py-2 text-right text-slate-700">{{ g.distance|intcomma }}</td>
                  <td class="whitespace-nowrap px-3 py-2 text-right font-semibold text-slate-900">{{ g.consommation|floatformat:1 }}{% if g.anomalie %} {% badge "ANOMALIE" "Anomalie" %}{% endif %}</td>
                  <td class="whitespace-nowrap py-2 pl-3 text-right text-slate-700">{% if g.ecart_flotte_pct is not None %}{{ g.ecart_flotte_pct|pourcentage_signe }} %{% else %}—{% endif %}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      {% else %}
        <p class="mt-3 text-sm text-slate-700">Aucune consommation calculée pour l'instant.</p>
      {% endif %}
    </section>
  </div>
</div>
{% endblock %}
```

## Étape 3 — Tests et compilation des styles

#### `apps/core/tests/test_search.py`

*191 lignes* — Recherche texte insensible aux accents et à la casse, et pagination tolérante.

```python
"""Recherche texte insensible aux accents et à la casse, et pagination tolérante."""

import pytest
from django.db import connection
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.search import Normalise, filtrer_par_texte, normaliser
from apps.hr.models import Personnel
from apps.hr.tests.factories import PersonnelFactory

pytestmark = pytest.mark.django_db


def _noms(queryset):
    return sorted(p.nom for p in queryset)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Traoré", "traore"),
        ("TRAORÉ", "traore"),
        ("Côte d'Ivoire", "cote d'ivoire"),
        ("Ñandú Çà", "nandu ca"),
        ("", ""),
        (None, ""),
    ],
)
def test_normaliser(texte, attendu):
    assert normaliser(texte) == attendu


# --- filtrer_par_texte ---


@pytest.fixture
def equipe():
    PersonnelFactory(nom="Traoré", prenom="Moussa", matricule="M-001", poste="Chauffeur")
    PersonnelFactory(nom="Traore", prenom="Ali", matricule="M-002", poste="Comptable")
    PersonnelFactory(nom="Koné", prenom="Awa", matricule="M-003", poste="Directrice")
    PersonnelFactory(nom="Diallo", prenom="Émile", matricule="M-004", poste="100% fiable_")


@pytest.mark.parametrize("recherche", ["traoré", "TRAORÉ", "traore", "TRAORE", "Traoré", "  traore  "])
def test_les_accents_et_la_casse_ne_changent_pas_le_resultat(equipe, recherche):
    resultat = filtrer_par_texte(Personnel.objects.all(), recherche, "nom")

    assert _noms(resultat) == ["Traore", "Traoré"]


@pytest.mark.parametrize("recherche", ["kone", "KONÉ", "koné"])
def test_un_nom_accentue_se_trouve_sans_ses_accents(equipe, recherche):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), recherche, "nom")) == ["Koné"]


def test_un_prenom_en_majuscule_accentuee_se_trouve(equipe):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "emile", "prenom")) == ["Diallo"]
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "ÉMILE", "prenom")) == ["Diallo"]


def test_chaque_mot_doit_se_trouver_dans_un_des_champs(equipe):
    personnel = Personnel.objects.all()

    assert _noms(filtrer_par_texte(personnel, "moussa traore", "nom", "prenom")) == ["Traoré"]
    assert _noms(filtrer_par_texte(personnel, "traore moussa", "nom", "prenom")) == ["Traoré"]
    assert _noms(filtrer_par_texte(personnel, "moussa kone", "nom", "prenom")) == []
    assert _noms(filtrer_par_texte(personnel, "m-003 awa", "matricule", "prenom")) == ["Koné"]


def test_les_pourcentages_et_soulignes_saisis_sont_du_texte(equipe):
    personnel = Personnel.objects.all()

    assert _noms(filtrer_par_texte(personnel, "100%", "poste")) == ["Diallo"]
    assert _noms(filtrer_par_texte(personnel, "%", "nom")) == []
    assert _noms(filtrer_par_texte(personnel, "_", "nom")) == []
    assert _noms(filtrer_par_texte(personnel, "fiable_", "poste")) == ["Diallo"]


def test_une_recherche_vide_ou_d_espaces_ne_filtre_rien(equipe):
    assert filtrer_par_texte(Personnel.objects.all(), "", "nom").count() == 4
    assert filtrer_par_texte(Personnel.objects.all(), "   ", "nom").count() == 4


def test_la_recherche_traverse_les_relations(equipe):
    chef = Personnel.objects.get(nom="Koné")
    employe = Personnel.objects.get(nom="Diallo")
    employe.superieur = chef
    employe.save()

    resultat = filtrer_par_texte(Personnel.objects.all(), "KONE", "superieur__nom")

    assert _noms(resultat) == ["Diallo"]


def test_une_recherche_sans_resultat(equipe):
    assert _noms(filtrer_par_texte(Personnel.objects.all(), "zzz", "nom", "prenom")) == []


def test_la_requete_hors_sqlite_utilise_lower_et_translate():
    """Branche PostgreSQL (non exécutée ici faute de serveur) : SQL sans extension."""
    requete = Personnel.objects.annotate(n=Normalise("nom")).query
    compilateur = requete.get_compiler(using="default")

    sql, parametres = Normalise.as_sql(requete.annotations["n"], compilateur, connection)

    assert "LOWER(" in sql and "TRANSLATE(" in sql
    assert parametres[0].startswith("àâä") and len(parametres[0]) == len(parametres[1])


# --- pagination tolérante ---

LISTES = [
    "missions:liste",
    "fleet:liste",
    "drivers:liste",
    "garage:liste",
    "fuel:liste",
    "inventory:articles",
    "inventory:mouvements",
    "customers:liste",
    "hr:personnel_liste",
    "hr:conges_liste",
]


@pytest.mark.parametrize("nom_url", LISTES)
@pytest.mark.parametrize("page", ["abc", "0", "-3", "999", "last", "", "1.5"])
def test_un_numero_de_page_inutilisable_ne_donne_jamais_404(client, nom_url, page):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(reverse(nom_url), {"page": page})

    assert reponse.status_code == 200


@pytest.fixture
def trois_pages():
    for i in range(45):
        PersonnelFactory(nom=f"Nom{i:02d}", matricule=f"P-{i:03d}")


def _matricules(reponse):
    return [p.matricule for p in reponse.context["personnel"]]


def test_une_page_trop_grande_affiche_la_derniere(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    reponse = client.get(reverse("hr:personnel_liste"), {"page": 999})

    assert reponse.context["page_obj"].number == 3
    assert len(_matricules(reponse)) == 5


def test_une_page_invalide_ou_negative_affiche_la_premiere(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    for page in ("abc", "0", "-2"):
        reponse = client.get(reverse("hr:personnel_liste"), {"page": page})
        assert reponse.context["page_obj"].number == 1, page


def test_last_affiche_la_derniere_page_et_les_pages_normales_restent_correctes(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    derniere = client.get(reverse("hr:personnel_liste"), {"page": "last"})
    deuxieme = client.get(reverse("hr:personnel_liste"), {"page": 2})

    assert derniere.context["page_obj"].number == 3
    assert deuxieme.context["page_obj"].number == 2
    assert len(_matricules(deuxieme)) == 20


def test_les_liens_de_pagination_conservent_les_filtres(client, trois_pages):
    client.force_login(UserFactory(role=Role.ADMIN))

    texte = client.get(reverse("hr:personnel_liste"), {"q": "nom", "page": 2}).content.decode()

    assert "q=nom" in texte and "page=3" in texte


def test_la_recherche_du_personnel_ignore_accents_et_casse_dans_l_ecran(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    PersonnelFactory(nom="Traoré", prenom="Moussa")
    PersonnelFactory(nom="Bamba", prenom="Issa")

    for recherche in ("traore", "TRAORÉ", "moussa traore"):
        reponse = client.get(reverse("hr:personnel_liste"), {"q": recherche})
        assert [p.nom for p in reponse.context["personnel"]] == ["Traoré"], recherche
```

#### `apps/fuel/tests/test_views.py`

*557 lignes* — Écrans du carburant : liste, saisie (avec confirmation d'une saisie suspecte), analyse.

```python
"""Écrans du carburant : liste, saisie (avec confirmation d'une saisie suspecte), analyse."""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.models import NiveauAlerte, Plein

pytestmark = pytest.mark.django_db

_tickets = itertools.count(1)


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [(m.level_tag, str(m)) for m in reponse.context["messages"]]


def _jour(decalage):
    """Date relative à aujourd'hui : décalage négatif = dans le passé."""
    return timezone.localdate() + timedelta(days=decalage)


def _plein(camion, chauffeur, *, km, litres, decalage, **surcharges):
    donnees = dict(
        vehicule=camion,
        chauffeur=chauffeur,
        date_plein=_jour(decalage),
        station="Total",
        quantite_litres=Decimal(str(litres)),
        prix_unitaire=Decimal("655"),
        km_compteur=km,
        numero_ticket=f"V-{next(_tickets)}",
        confirmer_alerte_saisie=True,
    )
    donnees.update(surcharges)
    return services.enregistrer_plein(**donnees)


def _serie(camion, chauffeur, consommations):
    """Plein initial à 1000 km puis un plein de 400 km par consommation (dans le passé)."""
    debut = -30
    _plein(camion, chauffeur, km=1000, litres=100, decalage=debut)
    for rang, conso in enumerate(consommations, start=1):
        _plein(
            camion,
            chauffeur,
            km=1000 + rang * 400,
            litres=Decimal(str(conso)) * 4,
            decalage=debut + rang,
        )
    return 1000 + len(consommations) * 400


def _donnees(camion, chauffeur, **surcharges):
    donnees = {
        "vehicule": camion.pk,
        "chauffeur": chauffeur.pk,
        "date_plein": _jour(0).isoformat(),
        "station": "Total Yopougon",
        "quantite_litres": "120",
        "prix_unitaire": "655",
        "km_compteur": "5000",
        "numero_ticket": f"F-{next(_tickets)}",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_carburant_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)

    assert client.get(reverse("fuel:liste")).status_code == 200
    assert client.get(reverse("fuel:analyse")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_carburant_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)

    for nom in ("fuel:liste", "fuel:creer", "fuel:analyse"):
        assert client.get(reverse(nom)).status_code == 403, nom


def test_la_direction_peut_desormais_saisir_un_plein(client):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie."""
    _connecte(client, Role.DIRECTION)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    assert client.get(reverse("fuel:creer")).status_code == 200
    client.post(reverse("fuel:creer"), _donnees(camion, chauffeur))
    assert Plein.objects.count() == 1


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("fuel:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_carburant_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/carburant/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/carburant/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_pleins_avec_consommation_et_ecart(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(immatriculation="4444 KL 01"), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "37"])  # le dernier : +23 % → jaune

    reponse = client.get(reverse("fuel:liste"))
    contenu = reponse.content.decode()

    assert "4444 KL 01" in contenu
    assert "37,0" in contenu and "+23,3 %" in contenu
    assert "Jaune" in contenu


def test_la_liste_affiche_les_indicateurs(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "44"])  # 44 : rouge

    reponse = client.get(reverse("fuel:liste"))

    assert reponse.context["consommation_moyenne"] == Decimal("37.00")
    assert reponse.context["nombre_a_surveiller"] == 1
    assert "Pleins à surveiller" in reponse.content.decode()


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:liste"))

    assert "Aucun plein trouvé" in reponse.content.decode()
    assert "Pas encore de donnée" in reponse.content.decode()


def test_la_liste_filtre_par_camion_chauffeur_periode_texte_et_alerte(client):
    _connecte(client, Role.PARCAUTO)
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur_a, chauffeur_b = ChauffeurFactory(), ChauffeurFactory()
    _serie(camion_a, chauffeur_a, ["30", "44"])
    autre = _plein(camion_b, chauffeur_b, km=900, litres=100, decalage=-1, station="Shell Cocody")

    par_camion = client.get(reverse("fuel:liste"), {"vehicule": camion_b.pk})
    par_chauffeur = client.get(reverse("fuel:liste"), {"chauffeur": chauffeur_b.pk})
    par_texte = client.get(reverse("fuel:liste"), {"q": "cocody"})
    par_periode = client.get(
        reverse("fuel:liste"), {"date_debut": _jour(-1).isoformat(), "date_fin": _jour(-1).isoformat()}
    )
    par_alerte = client.get(reverse("fuel:liste"), {"alerte": "ROUGE"})

    for reponse in (par_camion, par_chauffeur, par_texte, par_periode):
        assert list(reponse.context["pleins"]) == [autre]
    assert [p.niveau_alerte for p in par_alerte.context["pleins"]] == [NiveauAlerte.ROUGE]


def test_la_consommation_moyenne_suit_le_filtre_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur = ChauffeurFactory()
    _serie(camion_a, chauffeur, ["30"])
    _serie(camion_b, chauffeur, ["40"])

    reponse = client.get(reverse("fuel:liste"), {"vehicule": camion_b.pk})

    assert reponse.context["consommation_moyenne"] == Decimal("40.00")
    assert "selon le filtre" in reponse.content.decode()


@pytest.mark.parametrize(
    "parametres",
    [{"date_debut": "pas-une-date"}, {"vehicule": "999999"}, {"alerte": "???"}, {"chauffeur": "abc"}],
)
def test_un_filtre_invalide_est_ignore_sans_faire_echouer_la_page(client, parametres):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-1)

    reponse = client.get(reverse("fuel:liste"), parametres)

    assert reponse.status_code == 200
    assert len(reponse.context["pleins"]) == 1


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-60)
    for rang in range(1, 21):
        _plein(camion, chauffeur, km=1000 + rang * 400, litres=120, decalage=-60 + rang)

    assert len(client.get(reverse("fuel:liste"), {"page": 2}).context["pleins"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_plein(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-30)
    for rang in range(1, 15):
        _plein(camion, chauffeur, km=1000 + rang * 400, litres=120, decalage=-30 + rang)

    with django_assert_max_num_queries(14):
        client.get(reverse("fuel:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-1, station="<script>alert(1)</script>")

    contenu = client.get(reverse("fuel:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- saisie ---


def test_le_formulaire_de_saisie_est_prerempli_avec_la_date_du_jour(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:creer"))

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["date_plein"] == timezone.localdate()


def test_le_choix_du_chauffeur_exclut_les_inactifs(client):
    _connecte(client, Role.PARCAUTO)
    actif = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    reponse = client.get(reverse("fuel:creer"))

    assert list(reponse.context["form"].fields["chauffeur"].queryset) == [actif]


def test_le_premier_plein_d_un_camion_est_enregistre_sans_consommation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(kilometrage=100), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur), follow=True)

    plein = Plein.objects.get()
    assert plein.consommation is None
    assert reponse.redirect_chain[-1][0] == reverse("fuel:liste")
    assert any("Premier plein" in texte for _, texte in _messages(reponse))
    camion.refresh_from_db()
    assert camion.kilometrage == 5000  # le compteur du camion est relevé


def test_un_plein_normal_annonce_la_consommation_sans_alerte(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])  # dernier km : 1400

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="120"),
        follow=True,
    )

    messages = _messages(reponse)
    assert any(niveau == "success" and "30,0 L/100 km" in texte for niveau, texte in messages)
    assert not any(niveau == "warning" for niveau, _ in messages)


def test_un_plein_en_surconsommation_signale_l_alerte_et_l_ecart(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="148"),  # 37 L/100
        follow=True,
    )

    avertissements = [texte for niveau, texte in _messages(reponse) if niveau == "warning"]
    assert any("Jaune" in texte and "+23,3 %" in texte for texte in avertissements)
    assert Plein.objects.latest("pk").niveau_alerte == NiveauAlerte.JAUNE


def test_une_anomalie_est_signalee(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="180.04"),  # 45,01
        follow=True,
    )

    assert any(niveau == "warning" and "Anomalie" in texte for niveau, texte in _messages(reponse))


# --- saisie suspecte : avertissement puis confirmation ---


def _saisie_suspecte(camion, chauffeur, **surcharges):
    """Écart de +66,7 % : 200 L sur 400 km = 50 L/100 km face à une moyenne de 30."""
    return _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="200", **surcharges)


def test_une_saisie_suspecte_n_est_pas_enregistree_et_demande_confirmation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    avant = Plein.objects.count()

    reponse = client.post(reverse("fuel:creer"), _saisie_suspecte(camion, chauffeur))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert Plein.objects.count() == avant
    assert "Vérifiez cette saisie" in contenu
    assert "+66,7 %" in contenu and "50,0 L/100 km" in contenu
    assert 'name="confirmer"' in contenu and "Confirmer" in contenu


def test_la_page_d_avertissement_conserve_les_valeurs_saisies(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"), _saisie_suspecte(camion, chauffeur, station="Shell Marcory")
    )

    assert reponse.context["form"]["station"].value() == "Shell Marcory"
    assert reponse.context["form"]["quantite_litres"].value() == "200"
    assert "Shell Marcory" in reponse.content.decode()


def test_confirmer_une_saisie_suspecte_l_enregistre_avec_la_mention(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    donnees = _saisie_suspecte(camion, chauffeur)
    donnees["confirmer"] = "1"
    reponse = client.post(reverse("fuel:creer"), donnees, follow=True)

    plein = Plein.objects.latest("pk")
    assert plein.alerte_saisie is True
    assert plein.consommation == Decimal("50.00")
    assert reponse.redirect_chain[-1][0] == reverse("fuel:liste")
    assert "Saisie confirmée" in reponse.content.decode()


def test_corriger_la_saisie_apres_l_avertissement_l_enregistre_normalement(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    donnees = _saisie_suspecte(camion, chauffeur)
    client.post(reverse("fuel:creer"), donnees)  # avertissement

    donnees["quantite_litres"] = "120"  # l'erreur était dans les litres
    reponse = client.post(reverse("fuel:creer"), donnees, follow=True)

    plein = Plein.objects.latest("pk")
    assert plein.alerte_saisie is False and plein.consommation == Decimal("30.00")
    assert any("Plein enregistré" in texte for _, texte in _messages(reponse))


def test_un_ecart_de_60_pour_cent_pile_n_exige_pas_de_confirmation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="192"),  # 48 L/100 = +60 %
    )

    assert reponse.status_code == 302


# --- erreurs de saisie ---


def test_un_kilometrage_qui_n_augmente_pas_est_refuse_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    avant = Plein.objects.count()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, km_compteur="1400"))

    assert reponse.status_code == 200
    assert "doit dépasser" in reponse.content.decode()
    assert Plein.objects.count() == avant


def test_un_ticket_deja_enregistre_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-5, numero_ticket="DOUBLON-1")

    reponse = client.post(
        reverse("fuel:creer"), _donnees(camion, chauffeur, km_compteur="1400", numero_ticket="DOUBLON-1")
    )

    assert "déjà enregistré" in reponse.content.decode()
    assert Plein.objects.count() == 1


def test_un_plein_anterieur_au_dernier_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-2)

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1400", date_plein=_jour(-5).isoformat()),
    )

    assert "dans l'ordre" in reponse.content.decode()
    assert Plein.objects.count() == 1


def test_une_date_dans_le_futur_est_refusee_par_le_formulaire(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(
        reverse("fuel:creer"), _donnees(camion, chauffeur, date_plein=_jour(3).isoformat())
    )

    assert "date_plein" in reponse.context["form"].errors
    assert Plein.objects.count() == 0


@pytest.mark.parametrize(
    "champ",
    [
        {"quantite_litres": "0"},
        {"quantite_litres": "-5"},
        {"quantite_litres": "abc"},
        {"prix_unitaire": "-1"},
        {"km_compteur": "-3"},
        {"numero_ticket": ""},
        {"station": ""},
        {"vehicule": "999999"},
        {"date_plein": "31/02/2026"},
    ],
)
def test_une_saisie_invalide_est_refusee_par_le_formulaire(client, champ):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, **champ))

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert Plein.objects.count() == 0


def test_un_prix_nul_est_refuse_par_le_service_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, prix_unitaire="0"))

    assert "strictement positif" in reponse.content.decode()
    assert Plein.objects.count() == 0


def test_la_saisie_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    assert client.post(reverse("fuel:creer"), _donnees(camion, chauffeur)).status_code == 403
    assert Plein.objects.count() == 0


# --- analyse ---


def test_l_analyse_affiche_les_tableaux_par_camion_et_par_chauffeur(client):
    _connecte(client, Role.DIRECTION)
    camion_a = VehiculeFactory(immatriculation="1111 AA 01")
    camion_b = VehiculeFactory(immatriculation="2222 BB 01")
    chauffeur_a = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    chauffeur_b = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _serie(camion_a, chauffeur_a, ["30", "30"])
    _serie(camion_b, chauffeur_b, ["40"])

    reponse = client.get(reverse("fuel:analyse"))
    contenu = reponse.content.decode()

    assert reponse.context["consommation_flotte"] == Decimal("33.33")
    assert "1111 AA 01" in contenu and "2222 BB 01" in contenu
    assert "Awa Koné" in contenu and "Issa Bamba" in contenu
    assert "+20,0 %" in contenu and "-10,0 %" in contenu


def test_l_analyse_sans_donnee_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    contenu = client.get(reverse("fuel:analyse")).content.decode()

    assert contenu.count("Aucune consommation calculée") == 2
    assert "Pas encore de donnée" in contenu


def test_une_periode_a_l_envers_est_signalee_et_ignoree(client):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-5)

    reponse = client.get(
        reverse("fuel:liste"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"}
    )

    assert reponse.status_code == 200
    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["pleins"]) == 1  # aucun filtre de date appliqué


def test_une_date_illisible_est_signalee_sans_erreur(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:liste"), {"date_debut": "pas-une-date"})

    assert reponse.status_code == 200
    assert "Saisissez une date valide" in reponse.content.decode()
```

#### `apps/notifications/tests/test_receivers.py`

*376 lignes* — Qui est prévenu de quoi : congés, stock, carburant, départ de mission.

```python
"""Qui est prévenu de quoi : congés, stock, carburant, départ de mission."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.hr import services as hr
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory
from apps.missions import services as missions
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory
from apps.notifications import receivers
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


class Equipe:
    def __init__(self):
        self.compte_sup = UserFactory(role=Role.PARCAUTO)
        self.superieur = PersonnelFactory(utilisateur=self.compte_sup)
        self.compte = UserFactory(role=Role.CHARGE_CLIENTELE)
        self.employe = PersonnelFactory(
            superieur=self.superieur, utilisateur=self.compte, nom="Bamba", prenom="Issa"
        )
        self.compte_rh = UserFactory(role=Role.RH)
        self.rh = PersonnelFactory(utilisateur=self.compte_rh, superieur=self.superieur)

    def demander(self, employe=None):
        return hr.demander_conge(
            employe or self.employe, date_debut=DEBUT, date_fin=FIN, motif="Repos",
            maintenant=MAINTENANT,
        )


@pytest.fixture
def equipe():
    return Equipe()


# --- congés ---


def test_le_superieur_est_prevenu_d_une_demande(equipe):
    conge = equipe.demander()

    (notification,) = _de(equipe.compte_sup)
    assert notification.categorie == CategorieNotification.CONGE
    assert notification.niveau == NiveauNotification.ATTENTION
    assert "Issa Bamba" in notification.titre
    assert "5 jours ouvrés du 05/10/2026 au 09/10/2026" in notification.message
    assert "03/09/2026" in notification.message  # 48 h après la demande
    assert notification.url == reverse("hr:conges_detail", args=[conge.pk])
    assert _de(equipe.compte) == [] and _de(equipe.compte_rh) == []


def test_une_mission_prevue_declenche_une_alerte_supplementaire_pour_le_validateur():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    fiche = ChauffeurFactory(personnel=PersonnelFactory(poste="Chauffeur", superieur=superieur))
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    hr.demander_conge(
        fiche.personnel, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT
    )

    demande, alerte = _de(compte_sup)
    assert demande.niveau == NiveauNotification.ATTENTION
    assert alerte.niveau == NiveauNotification.URGENT
    assert "Mission prévue" in alerte.titre and mission.numero in alerte.message


def test_le_directeur_est_prevenu_de_sa_propre_demande():
    compte = UserFactory(role=Role.DIRECTION)
    directeur = PersonnelFactory(utilisateur=compte)

    hr.demander_conge(directeur, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert len(_de(compte)) == 1


def test_sans_compte_pour_le_superieur_la_demande_reste_possible_et_personne_n_est_prevenu():
    superieur = PersonnelFactory()  # fiche sans compte utilisateur
    employe = PersonnelFactory(superieur=superieur, utilisateur=UserFactory())

    conge = hr.demander_conge(
        employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT
    )

    assert conge.pk and Notification.objects.count() == 0


def test_la_rh_est_prevenue_apres_la_validation_n1(equipe):
    conge = equipe.demander()

    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    (notification,) = _de(equipe.compte_rh)
    assert "N2" in notification.titre and "Issa Bamba" in notification.titre
    assert "03/09/2026" not in notification.message and "02/09/2026" in notification.message  # 24 h
    assert _de(equipe.compte) == []


def test_la_rh_n_est_pas_prevenue_de_sa_propre_demande(equipe):
    conge = equipe.demander(equipe.rh)
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    assert _de(equipe.compte_rh) == []


def test_l_employe_est_prevenu_de_l_approbation(equipe):
    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    hr.valider_n2(conge, equipe.compte_rh)

    (notification,) = _de(equipe.compte)
    assert notification.titre == "Votre congé est approuvé"
    assert "5 jours ouvrés du 05/10/2026 au 09/10/2026" in notification.message


def test_l_employe_est_prevenu_du_refus_avec_le_motif(equipe):
    conge = equipe.demander()

    hr.refuser(conge, equipe.compte_sup, commentaire="Période de forte activité")

    (notification,) = _de(equipe.compte)
    assert notification.titre == "Votre demande de congé est refusée"
    assert "Période de forte activité" in notification.message
    assert notification.niveau == NiveauNotification.ATTENTION


def test_l_employe_est_prevenu_de_l_annulation_par_la_rh(equipe):
    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, equipe.compte_rh)

    hr.annuler_conge_approuve(conge, equipe.compte_rh, motif="Besoin de service")

    annulation = _de(equipe.compte)[-1]
    assert annulation.titre == "Votre congé approuvé a été annulé"
    assert "Besoin de service" in annulation.message and "restitués" in annulation.message
    assert annulation.niveau == NiveauNotification.URGENT


def test_un_employe_sans_compte_ne_bloque_pas_la_decision(equipe):
    sans_compte = PersonnelFactory(superieur=equipe.superieur)
    conge = equipe.demander(sans_compte)

    hr.refuser(conge, equipe.compte_sup, commentaire="Non")

    assert Notification.objects.filter(titre__startswith="Votre").count() == 0


def test_une_notification_en_erreur_ne_bloque_jamais_un_conge(equipe, monkeypatch, caplog):
    def panne(*args, **kwargs):
        raise RuntimeError("panne de notification")

    monkeypatch.setattr(receivers, "notifier", panne)

    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, equipe.compte_rh)

    conge.refresh_from_db()
    assert conge.statut == "APPROUVE"
    assert "en erreur" in caplog.text


def _en_cours(equipe):
    from apps.hr.models import Conge, StatutConge

    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, equipe.compte_rh)
    Conge.objects.filter(pk=conge.pk).update(statut=StatutConge.EN_COURS)
    conge.refresh_from_db()
    return conge


def test_la_rh_est_prevenue_d_une_demande_de_report(equipe):
    conge = _en_cours(equipe)

    report = hr.demander_report(
        conge, equipe.compte, nouvelle_date_fin=date(2026, 10, 7), motif="Fin des vacances"
    )

    notification = _de(equipe.compte_rh)[-1]  # la RH a déjà la notification de validation N2 (_en_cours)
    assert notification.categorie == CategorieNotification.CONGE
    assert "Issa Bamba" in notification.titre
    assert "07/10/2026" in notification.message
    assert notification.action == "Confirmer le report"
    assert notification.url == reverse("hr:conges_detail", args=[conge.pk])


def test_l_employe_est_prevenu_de_la_decision_sur_son_report(equipe):
    conge = _en_cours(equipe)
    report = hr.demander_report(conge, equipe.compte, nouvelle_date_fin=date(2026, 10, 7), motif="x")

    hr.approuver_report(report, equipe.compte_rh)

    notification = _de(equipe.compte)[-1]  # l'employé a déjà la notification d'approbation (_en_cours)
    assert "validé" in notification.titre
    assert "07/10/2026" in notification.message


def test_l_employe_est_prevenu_du_refus_de_son_report(equipe):
    conge = _en_cours(equipe)
    report = hr.demander_report(conge, equipe.compte, nouvelle_date_fin=date(2026, 10, 7), motif="x")

    hr.refuser_report(report, equipe.compte_rh, motif="Effectif insuffisant")

    notification = _de(equipe.compte)[-1]
    assert "refusée" in notification.titre
    assert "Effectif insuffisant" in notification.message


# --- stock ---


def test_le_parc_auto_est_prevenu_d_un_stock_bas():
    parc, autre, rh = UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.RH)
    article = stock.creer_article(reference="FR-1", designation="Plaquettes", seuil_minimal=5)
    stock.enregistrer_entree(article, quantite=8, prix_unitaire=Decimal("1000"))

    stock.ajuster_stock(article, variation=-4, motif="Casse")  # 4 <= seuil 5

    for compte in (parc, autre):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.STOCK
        assert "Plaquettes" in notification.titre
        assert "FR-1 : 4 en stock pour un seuil minimal de 5" in notification.message
        assert notification.url == reverse("inventory:article_detail", args=[article.pk])
    assert _de(rh) == []


def test_le_stock_bas_n_est_signale_qu_au_franchissement_du_seuil():
    parc = UserFactory(role=Role.PARCAUTO)
    article = stock.creer_article(reference="FR-2", designation="Filtre", seuil_minimal=5)
    stock.enregistrer_entree(article, quantite=8, prix_unitaire=Decimal("1000"))

    stock.ajuster_stock(article, variation=-4, motif="Casse")
    stock.ajuster_stock(article, variation=-1, motif="Casse")  # déjà sous le seuil

    assert len(_de(parc)) == 1


# --- carburant ---


def _serie_pleins(consommations):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    jour = timezone.localdate() - timedelta(days=40)
    km = 1000
    fuel.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=jour, station="T",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"), km_compteur=km,
        numero_ticket=f"T-{camion.pk}-0",
    )
    pleins = []
    for rang, conso in enumerate(consommations, start=1):
        km += 400
        pleins.append(
            fuel.enregistrer_plein(
                vehicule=camion, chauffeur=chauffeur, date_plein=jour + timedelta(days=rang),
                station="T", quantite_litres=Decimal(str(conso)) * 4,
                prix_unitaire=Decimal("655"), km_compteur=km,
                numero_ticket=f"T-{camion.pk}-{rang}", confirmer_alerte_saisie=True,
            )
        )
    return camion, pleins


def test_une_surconsommation_rouge_previent_le_parc_auto_et_la_direction():
    parc, direction, rh = (UserFactory(role=r) for r in (Role.PARCAUTO, Role.DIRECTION, Role.RH))

    camion, _ = _serie_pleins([30, 30, 30, 44])  # +46,7 % : rouge

    for compte in (parc, direction):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.CARBURANT
        assert notification.niveau == NiveauNotification.URGENT
        assert f"alerte rouge sur {camion.immatriculation}" in notification.titre
        assert "44,0 L/100 km" in notification.message and "+46,7 %" in notification.message
        assert notification.url == f"{reverse('fuel:liste')}?vehicule={camion.pk}"
    assert _de(rh) == []


def test_une_alerte_jaune_est_de_niveau_attention():
    parc = UserFactory(role=Role.PARCAUTO)

    _serie_pleins([30, 30, 30, 37])  # +23,3 % : jaune

    (notification,) = _de(parc)
    assert notification.niveau == NiveauNotification.ATTENTION
    assert "alerte jaune" in notification.titre


def test_une_consommation_normale_ne_notifie_rien():
    UserFactory(role=Role.PARCAUTO)

    _serie_pleins([30, 30, 30, 31])

    assert Notification.objects.count() == 0


def test_une_notification_en_erreur_ne_bloque_pas_la_saisie_du_plein(monkeypatch, caplog):
    UserFactory(role=Role.PARCAUTO)

    def panne(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr(receivers, "notifier", panne)

    _, pleins = _serie_pleins([30, 30, 30, 44])

    assert len(pleins) == 4 and "en erreur" in caplog.text


# --- missions ---


def _mission_affectee(client):
    mission = missions.creer_mission(
        client=client, lieu_chargement="Abidjan", lieu_livraison="Bouaké",
        nature_marchandise="Ciment", poids_t=Decimal("20"), prix_convenu=Decimal("850000"),
    )
    missions.planifier_mission(mission)
    return missions.affecter_mission(
        mission, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
    )


def test_le_depart_previent_le_charge_clientele_attitre_du_client():
    attitre = UserFactory(role=Role.CHARGE_CLIENTELE)
    autre = UserFactory(role=Role.CHARGE_CLIENTELE)
    mission = _mission_affectee(ClientFactory(charge_clientele=attitre, raison_sociale="Cimaf"))

    missions.demarrer_mission(mission)

    (notification,) = _de(attitre)
    assert notification.titre == f"En cours de route : {mission.numero}"
    assert "Cimaf" in notification.message and "Abidjan" in notification.message
    assert "Bouaké" in notification.message
    assert notification.url == reverse("missions:detail", args=[mission.pk])
    assert _de(autre) == []


def test_sans_charge_attitre_tous_les_charges_clientele_sont_prevenus():
    a, b = UserFactory(role=Role.CHARGE_CLIENTELE), UserFactory(role=Role.CHARGE_CLIENTELE)
    mission = _mission_affectee(ClientFactory())

    missions.demarrer_mission(mission)

    assert len(_de(a)) == 1 and len(_de(b)) == 1
```

`core/tests/test_search.py` vérifie qu'un numéro de page inutilisable ne donne jamais 404 sur **toutes** les
listes : il a donc besoin que les listes existent.

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
python -m pytest apps/core/tests/test_search.py apps/fuel/tests/test_views.py apps/notifications/tests/test_receivers.py -q --no-cov
```

**Résultat attendu :** `168 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur (`demo_parcauto`) :**

1. **Carburant → Nouveau plein** : camion `1234 AB 01`, chauffeur `Moussa Ouattara`, une station, **180 litres**,
   prix 700, un compteur (par exemple le kilométrage actuel du camion + 10) et un numéro de ticket. Un premier
   plein n'a **pas de plein précédent** : pas de consommation, aucune alerte.
2. Saisissez un **deuxième plein** : compteur **+ 600 km**, **180 litres** (ticket différent) : consommation
   **30 L/100 km**, mais encore **aucune comparaison** (la moyenne de référence se calcule sur les pleins qui ont
   déjà une consommation).
3. Saisissez un **troisième plein** : compteur **+ 600 km** de plus, **300 litres** (soit 50 L/100 km contre 30) :
   l'écart est de **+66,7 %**. Le formulaire **se réaffiche avec un avertissement de saisie suspecte (au-delà de
   60 %) et un bouton Confirmer**. Rien n'est enregistré. Cliquez **Confirmer** : le plein est enregistré avec une
   **alerte rouge** et une **anomalie** (50 > 45).
4. Le **ticket déjà utilisé** est refusé. Un plein **daté avant** le dernier est refusé (chronologie).
5. Ouvrez **Analyse** : la consommation par camion et par chauffeur apparaît. La **cloche de `demo_direction`**
   compte l'alerte.

## Ce qu'il faut retenir

- Un service peut demander une **confirmation** en levant une exception *sans rien enregistrer* ; la vue
  transforme cela en dialogue.
- Les **messages** affichés à l'utilisateur formatent les nombres à la française.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 24 : écrans du carburant (pleins, confirmation des saisies suspectes, analyse)"
```

---

[← Chapitre 23](23-ecrans-stock.md) · [Sommaire](README.md) · [Chapitre 25 →](25-ecrans-finances.md)
