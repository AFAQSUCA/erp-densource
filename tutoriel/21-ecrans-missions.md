# Chapitre 21 — Écrans : missions et codes QR

> 14 fichier(s) dans ce chapitre, 2393 lignes de code.

## Ce que vous allez construire

Les **écrans des missions** : le cycle de vie du chapitre 9, cliquable.

| Écran | Adresse | Qui |
|---|---|---|
| Liste (statut, recherche) | `/missions/` | ADMIN, DIRECTION, CHARGE_CLIENTELE |
| **Créer** une mission | `/missions/nouvelle/` | idem |
| **Fiche** avec la **frise du cycle de vie**, les actions possibles, les **codes et leurs QR** | `/missions/<id>/` | idem |
| Actions en POST : **planifier**, **affecter**, **démarrer**, **récupération**, **livraison**, **clôturer** | `/missions/<id>/planifier/`… | selon le rôle et le statut |
| Image QR d'un code | `/missions/<id>/qr/expediteur.png` (ou `destinataire`) | ADMIN, DIRECTION, CHARGE_CLIENTELE |

Deux blocs sont aussi **fournis à d'autres pages** par `missions` : l'alerte « ce chauffeur a une mission prévue
sur la période » (fiche d'un congé, chapitre 17) et la **liste des missions d'un client** (fiche client,
chapitre 19).

## Prérequis

- Chapitres 1 à 20 terminés.

## Ce que ce chapitre apporte de nouveau

- **Des actions dont la disponibilité dépend du rôle *et* du statut** : `permissions.actions_disponibles(utilisateur,
  mission)` (chapitre 9) renvoie un dictionnaire ; le gabarit n'affiche que les boutons dont la valeur est vraie.
  **Mais la vue re-vérifie** : masquer un bouton ne protège rien.
- **Une classe mère d'actions** (`ActionMissionView`) : chaque action (`planifier`, `démarrer`…) hérite d'un
  comportement commun (contrôle du droit, appel du service, message, redirection) et ne définit que ce qui change.
- **Un contenu qui n'est pas une page** : `CodeQrView` renvoie une **image PNG** fabriquée à la volée avec la
  bibliothèque `qrcode`. Elle est réservée aux rôles qui voient les codes, **jamais mise en cache**
  (`Cache-Control: no-store, private`), et l'image ne contient **que le code**.
- **Des codes montrés seulement tant qu'ils servent** : `permissions.codes_visibles`.
- **Des gabarits qui s'incluent dans d'autres apps** : `_alerte_conge.html` et `_missions_client.html` sont des
  *fragments* (leur nom commence par `_`) chargés par les registres de sections.

## Étape 1 — Formulaires, vues, adresses

#### `apps/missions/forms.py`

*58 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin
from apps.customers import services as customers_services
from apps.drivers import services as drivers_services
from apps.fleet import services as fleet_services


class MissionForm(StyleTailwindMixin, forms.Form):
    """Création d'une mission (cahier-des-charges.md:129-131)."""

    client = forms.ModelChoiceField(queryset=None, label="Client")
    lieu_chargement = forms.CharField(label="Lieu de chargement", max_length=200)
    lieu_livraison = forms.CharField(label="Lieu de livraison", max_length=200)
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(
        label="Poids (tonnes)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )
    date_depart_prevue = forms.DateField(
        label="Départ prévu",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Facultatif. Sert à repérer les conflits avec les congés des chauffeurs.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = customers_services.clients_pour_selection()


class AffectationForm(StyleTailwindMixin, forms.Form):
    """Affectation d'un camion et d'un chauffeur disponibles."""

    vehicule = forms.ModelChoiceField(queryset=None, label="Camion disponible")
    chauffeur = forms.ModelChoiceField(queryset=None, label="Chauffeur disponible")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_disponibles()
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.capacite_charge_t} t)"
        )
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_disponibles()


class CodeForm(StyleTailwindMixin, forms.Form):
    """Saisie du code remis à l'expéditeur ou au destinataire."""

    code = forms.CharField(
        label="Code", max_length=12, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )


class LivraisonForm(CodeForm):
    km_arrivee = forms.IntegerField(label="Kilométrage à l'arrivée", min_value=0)
```

#### `apps/missions/views.py`

*231 lignes* — Écrans des missions.

```python
"""Écrans des missions.

Les vues ne portent aucune règle métier : elles contrôlent le rôle, lisent le
formulaire et délèguent à ``services.py`` (conventions.md:19-23). Une erreur
métier (``MissionError``) devient un message affiché à l'utilisateur.
"""

import io

import qrcode
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import MissionError
from .forms import AffectationForm, CodeForm, LivraisonForm, MissionForm
from .models import StatutMission

ETAPES = [
    (StatutMission.BROUILLON, "Brouillon"),
    (StatutMission.PLANIFIEE, "Planifiée"),
    (StatutMission.AFFECTEE, "Affectée"),
    (StatutMission.EN_COURS_DEPART, "Départ"),
    (StatutMission.EN_COURS_COLIS_RECUPERE, "Colis récupéré"),
    (StatutMission.LIVREE, "Livrée"),
    (StatutMission.CLOTUREE, "Clôturée"),
]


def _etapes(statut: str) -> list[dict]:
    """Frise du cycle de vie : chaque étape est faite, en cours ou à venir."""
    rang_courant = [code for code, _ in ETAPES].index(statut)
    return [
        {
            "libelle": libelle,
            "etat": "faite" if rang < rang_courant else "courante" if rang == rang_courant else "a_venir",
        }
        for rang, (_, libelle) in enumerate(ETAPES)
    ]


class MissionListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "missions/mission_list.html"
    context_object_name = "missions"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_missions(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutMission.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            peut_creer=self.request.user.role_effectif in permissions.CREATION,
        )
        return contexte


class MissionDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "missions/mission_detail.html"
    context_object_name = "mission"

    def get_queryset(self):
        return services.missions_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mission, utilisateur = self.object, self.request.user
        actions = permissions.actions_disponibles(utilisateur, mission)
        contexte.update(
            etapes=_etapes(mission.statut),
            actions=actions,
            codes=permissions.codes_visibles(utilisateur, mission),
            form_affectation=AffectationForm() if actions["affecter"] else None,
            form_recuperation=CodeForm() if actions["recuperation"] else None,
            form_livraison=LivraisonForm() if actions["livraison"] else None,
        )
        return contexte


class MissionCreateView(RoleRequiredMixin, FormView):
    roles = permissions.CREATION
    form_class = MissionForm
    template_name = "missions/mission_form.html"

    def form_valid(self, form):
        try:
            mission = services.creer_mission(**form.cleaned_data)
        except MissionError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Mission {mission.numero} créée en brouillon.")
        return redirect("missions:detail", pk=mission.pk)


class ActionMissionView(RoleRequiredMixin, View):
    """Base des actions du cycle de vie : POST uniquement, puis retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def executer(self, mission, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def message_succes(self, mission) -> str:  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk):
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                for erreurs in form.errors.values():
                    for erreur in erreurs:
                        messages.error(request, erreur)
                return redirect("missions:detail", pk=mission.pk)
            donnees = form.cleaned_data
        try:
            self.executer(mission, donnees)
        except MissionError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self.message_succes(mission))
        return redirect("missions:detail", pk=mission.pk)


class PlanifierView(ActionMissionView):
    roles = permissions.PLANIFICATION

    def executer(self, mission, donnees):
        services.planifier_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} planifiée."


class AffecterView(ActionMissionView):
    roles = permissions.AFFECTATION
    form_class = AffectationForm

    def executer(self, mission, donnees):
        services.affecter_mission(
            mission, vehicule=donnees["vehicule"], chauffeur=donnees["chauffeur"]
        )

    def message_succes(self, mission):
        return f"Mission {mission.numero} affectée."


class DemarrerView(ActionMissionView):
    roles = permissions.SUIVI_TERRAIN

    def executer(self, mission, donnees):
        services.demarrer_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} démarrée : camion et chauffeur en mission."


class RecuperationView(ActionMissionView):
    roles = permissions.SUIVI_TERRAIN
    form_class = CodeForm

    def executer(self, mission, donnees):
        services.confirmer_recuperation(mission, code=donnees["code"])

    def message_succes(self, mission):
        return f"Colis récupéré pour la mission {mission.numero}."


class LivraisonView(ActionMissionView):
    roles = permissions.SUIVI_TERRAIN
    form_class = LivraisonForm

    def executer(self, mission, donnees):
        services.livrer_mission(
            mission, code=donnees["code"], km_arrivee=donnees["km_arrivee"]
        )

    def message_succes(self, mission):
        return f"Mission {mission.numero} livrée : camion et chauffeur de nouveau disponibles."


class CloturerView(ActionMissionView):
    roles = permissions.CLOTURE

    def executer(self, mission, donnees):
        services.cloturer_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} clôturée et validée."


class CodeQrView(RoleRequiredMixin, View):
    """Image PNG du code QR d'une mission (« expediteur » ou « destinataire »).

    Le QR ne contient que le code : le chauffeur le scanne (ou le saisit) pour confirmer la
    récupération ou la livraison. Réservé aux rôles qui voient déjà le code, et seulement tant
    que le code est utile ; jamais mis en cache (le code est un secret).
    """

    roles = permissions.CONSULTATION
    http_method_names = ["get"]

    def get(self, request, pk, qui):
        if qui not in ("expediteur", "destinataire"):
            raise Http404
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        code = permissions.codes_visibles(request.user, mission)[qui]
        if not code:
            raise Http404
        image = qrcode.make(code, box_size=8, border=2)
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        reponse = HttpResponse(tampon.getvalue(), content_type="image/png")
        reponse["Cache-Control"] = "no-store, private"
        return reponse
```

Repérez :

- **`MissionListView`** : filtre par statut et texte via `services.rechercher_missions`.
- **`MissionDetailView`** : calcule `actions`, `codes` (montrés selon le rôle et le statut), la frise, et les
  formulaires (affectation, code, livraison) à afficher.
- **`ActionMissionView`** et ses filles : une transition = une classe de quelques lignes.
- **`CodeQrView`** : l'image du code, avec les en-têtes de non-mise en cache.

#### `apps/missions/urls.py`

*18 lignes*

```python
from django.urls import path

from . import views

app_name = "missions"

urlpatterns = [
    path("", views.MissionListView.as_view(), name="liste"),
    path("nouvelle/", views.MissionCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.MissionDetailView.as_view(), name="detail"),
    path("<int:pk>/planifier/", views.PlanifierView.as_view(), name="planifier"),
    path("<int:pk>/affecter/", views.AffecterView.as_view(), name="affecter"),
    path("<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("<int:pk>/cloturer/", views.CloturerView.as_view(), name="cloturer"),
    path("<int:pk>/qr/<str:qui>.png", views.CodeQrView.as_view(), name="qr"),
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
+    path("missions/", include("apps.missions.urls")),
     path("clients/", include("apps.customers.urls")),
     path("flotte/", include("apps.fleet.urls")),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/missions/templates/missions
```

#### `apps/missions/templates/missions/mission_list.html`

*90 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Missions{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Missions</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} mission{{ paginator.count|pluralize }}</p>
    </div>
    {% if peut_creer %}
      <a href="{% url 'missions:creer' %}"
         class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle mission
      </a>
    {% endif %}
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="N°, client, lieu…"
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
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or statut_choisi %}
      <a href="{% url 'missions:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if missions %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des missions</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">N°</th>
            <th scope="col" class="px-4 py-3">Client</th>
            <th scope="col" class="px-4 py-3">Trajet</th>
            <th scope="col" class="px-4 py-3 text-right">Poids</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3">Chauffeur</th>
            <th scope="col" class="px-4 py-3 text-right">Prix</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for mission in missions %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'missions:detail' mission.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ mission.numero }}</a>
              </td>
              <td class="px-4 py-3 text-slate-800">{{ mission.client }}</td>
              <td class="px-4 py-3 text-slate-700">{{ mission.lieu_chargement }} <span aria-label="vers">→</span> {{ mission.lieu_livraison }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ mission.poids_t|floatformat:"-2" }} t</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ mission.vehicule.immatriculation|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{% if mission.chauffeur %}{{ mission.chauffeur.personnel.prenom }} {{ mission.chauffeur.personnel.nom }}{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-800">{{ mission.prix_convenu|floatformat:0|intcomma }} FCFA</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge mission.statut mission.get_statut_display %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <i class="fa-solid fa-truck-fast" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucune mission trouvée</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or statut_choisi %}Aucun résultat pour ces critères.{% else %}Les missions créées apparaîtront ici.{% endif %}
      </p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/mission_form.html`

*42 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle mission{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span> Nouvelle mission
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle mission</h1>
  <p class="mt-1 text-sm text-slate-600">
    La mission est créée en brouillon ; elle reçoit son numéro et ses deux codes (expéditeur, destinataire).
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <div class="grid gap-5 sm:grid-cols-2">
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.client %}</div>
      {% include "components/_champ.html" with champ=form.lieu_chargement %}
      {% include "components/_champ.html" with champ=form.lieu_livraison %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.nature_marchandise %}</div>
      {% include "components/_champ.html" with champ=form.poids_t %}
      {% include "components/_champ.html" with champ=form.prix_convenu %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.date_depart_prevue %}</div>
    </div>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'missions:liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Créer la mission
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/mission_detail.html`

*160 lignes*

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}{{ mission.numero }}{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span> {{ mission.numero }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ mission.numero }}</h1>
    {% badge mission.statut mission.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ mission.client }}</p>

  {# Frise du cycle de vie #}
  <ol class="mt-6 flex flex-wrap gap-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Avancement de la mission">
    {% for etape in etapes %}
      <li class="flex items-center" {% if etape.etat == "courante" %}aria-current="step"{% endif %}>
        <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold
              {% if etape.etat == 'faite' %}bg-emerald-700 text-white
              {% elif etape.etat == 'courante' %}bg-accent-500 text-slate-900 ring-4 ring-accent-200
              {% else %}bg-slate-200 text-slate-600{% endif %}">
          {% if etape.etat == "faite" %}<i class="fa-solid fa-check" aria-hidden="true"></i><span class="sr-only">Terminée : </span>{% else %}{{ forloop.counter }}{% endif %}
        </span>
        <span class="ml-2 text-sm {% if etape.etat == 'courante' %}font-semibold text-slate-900{% elif etape.etat == 'faite' %}text-slate-800{% else %}text-slate-600{% endif %}">{{ etape.libelle }}</span>
        {% if not forloop.last %}<span class="mx-3 hidden h-px w-6 bg-slate-300 sm:block" aria-hidden="true"></span>{% endif %}
      </li>
    {% endfor %}
  </ol>

  <div class="mt-6 grid gap-6 lg:grid-cols-3">
    <div class="space-y-6 lg:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-transport">
        <h2 id="titre-transport" class="text-base font-semibold text-slate-900">Transport</h2>
        <dl class="mt-4 grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Chargement</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.lieu_chargement }}</dd></div>
          <div><dt class="text-slate-600">Livraison</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.lieu_livraison }}</dd></div>
          <div><dt class="text-slate-600">Marchandise</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.nature_marchandise }}</dd></div>
          <div><dt class="text-slate-600">Poids</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.poids_t|floatformat:"-2" }} t</dd></div>
          <div><dt class="text-slate-600">Prix convenu</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.prix_convenu|floatformat:0|intcomma }} FCFA</dd></div>
          <div><dt class="text-slate-600">Départ prévu</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_depart_prevue|date:"d/m/Y"|default:"Non renseigné" }}</dd></div>
        </dl>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-affectation">
        <h2 id="titre-affectation" class="text-base font-semibold text-slate-900">Camion et chauffeur</h2>
        {% if mission.vehicule %}
          <dl class="mt-4 grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            <div><dt class="text-slate-600">Camion</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.vehicule.immatriculation }} — {{ mission.vehicule.marque }} {{ mission.vehicule.modele }}</dd></div>
            <div><dt class="text-slate-600">Chauffeur</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.chauffeur.personnel.prenom }} {{ mission.chauffeur.personnel.nom }}</dd></div>
            <div><dt class="text-slate-600">Km au départ</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.km_depart|default_if_none:"—"|intcomma }}</dd></div>
            <div><dt class="text-slate-600">Km à l'arrivée</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.km_arrivee|default_if_none:"—"|intcomma }}</dd></div>
          </dl>
        {% else %}
          <p class="mt-3 text-sm text-slate-700">Aucun camion ni chauffeur affecté pour l'instant.</p>
        {% endif %}
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-dates">
        <h2 id="titre-dates" class="text-base font-semibold text-slate-900">Historique</h2>
        <dl class="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Créée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.created_at|date:"d/m/Y H:i" }}</dd></div>
          <div><dt class="text-slate-600">Départ effectif</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_depart|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Colis récupéré le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_recuperation|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Livrée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_livraison|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Clôturée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_cloture|date:"d/m/Y H:i"|default:"—" }}</dd></div>
        </dl>
      </section>
    </div>

    <div class="space-y-6">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-actions">
        <h2 id="titre-actions" class="text-base font-semibold text-slate-900">Actions</h2>

        {% if actions.planifier %}
          <form method="post" action="{% url 'missions:planifier' mission.pk %}" class="mt-4">
            {% csrf_token %}
            <p class="mb-2 text-sm text-slate-700">Valider la mission pour la rendre disponible à l'affectation.</p>
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Valider et planifier</button>
          </form>
        {% endif %}

        {% if actions.affecter %}
          <form method="post" action="{% url 'missions:affecter' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_affectation.vehicule %}
            {% include "components/_champ.html" with champ=form_affectation.chauffeur %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Affecter</button>
          </form>
        {% endif %}

        {% if actions.demarrer %}
          <form method="post" action="{% url 'missions:demarrer' mission.pk %}" class="mt-4"
                data-confirm="Démarrer la mission ? Le camion et le chauffeur passeront « En mission ».">
            {% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-accent-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-600 focus-visible:ring-offset-2">Démarrer la mission</button>
          </form>
        {% endif %}

        {% if actions.recuperation %}
          <form method="post" action="{% url 'missions:recuperation' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            <p class="text-sm text-slate-700">L'expéditeur confirme la récupération du colis avec son code.</p>
            {% include "components/_champ.html" with champ=form_recuperation.code %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Confirmer la récupération</button>
          </form>
        {% endif %}

        {% if actions.livraison %}
          <form method="post" action="{% url 'missions:livraison' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            <p class="text-sm text-slate-700">Le destinataire confirme la livraison avec son code.</p>
            {% include "components/_champ.html" with champ=form_livraison.code %}
            {% include "components/_champ.html" with champ=form_livraison.km_arrivee %}
            <button type="submit" class="w-full rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">Confirmer la livraison</button>
          </form>
        {% endif %}

        {% if actions.cloturer %}
          <form method="post" action="{% url 'missions:cloturer' mission.pk %}" class="mt-4"
                data-confirm="Clôturer et valider définitivement cette mission ?">
            {% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Clôturer et valider</button>
          </form>
        {% endif %}

        {% if not actions.planifier and not actions.affecter and not actions.demarrer and not actions.recuperation and not actions.livraison and not actions.cloturer %}
          <p class="mt-3 text-sm text-slate-700">Aucune action disponible pour votre rôle à cette étape.</p>
        {% endif %}
      </section>

      {% if codes.expediteur or codes.destinataire %}
        <section class="rounded-xl border border-amber-300 bg-amber-50 p-5 shadow-sm" aria-labelledby="titre-codes">
          <h2 id="titre-codes" class="text-base font-semibold text-amber-900"><i class="fa-solid fa-key mr-2" aria-hidden="true"></i>Codes à communiquer</h2>
          <p class="mt-1 text-xs text-amber-900">Confidentiels : à remettre uniquement à la personne concernée.</p>
          {% if codes.expediteur %}
            <div class="mt-4">
              <p class="text-sm text-amber-900">Expéditeur (récupération du colis)</p>
              <p class="mt-1 rounded-lg bg-white px-3 py-2 text-center font-mono text-xl font-bold tracking-widest text-slate-900">{{ codes.expediteur }}</p>
              <img src="{% url 'missions:qr' mission.pk 'expediteur' %}" alt="Code QR de l'expéditeur : {{ codes.expediteur }}" width="160" height="160" class="mx-auto mt-2 rounded-lg bg-white p-1">
              <p class="mt-1 text-center text-xs text-amber-900">Le chauffeur scanne ce QR avec l'espace mobile.</p>
            </div>
          {% endif %}
          {% if codes.destinataire %}
            <div class="mt-4">
              <p class="text-sm text-amber-900">Destinataire (confirmation de livraison)</p>
              <p class="mt-1 rounded-lg bg-white px-3 py-2 text-center font-mono text-xl font-bold tracking-widest text-slate-900">{{ codes.destinataire }}</p>
              <img src="{% url 'missions:qr' mission.pk 'destinataire' %}" alt="Code QR du destinataire : {{ codes.destinataire }}" width="160" height="160" class="mx-auto mt-2 rounded-lg bg-white p-1">
            </div>
          {% endif %}
        </section>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

C'est le gabarit le plus riche du projet : la **frise** (`{% for … %}` sur les statuts), la colonne des
**actions**, et le cadre des **codes à communiquer** avec leur QR. Les formulaires d'action portent
`data-confirm` pour demander confirmation avant de démarrer ou clôturer.

#### `apps/missions/templates/missions/_alerte_conge.html`

*14 lignes*

```django
{% load ui %}
<div role="alert" class="mt-4 rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-950">
  <p class="font-semibold"><i class="fa-solid fa-triangle-exclamation mr-2" aria-hidden="true"></i>Ce chauffeur a {{ section.contexte.missions|length }} mission{{ section.contexte.missions|length|pluralize }} prévue{{ section.contexte.missions|length|pluralize }} pendant cette période</p>
  <ul class="mt-2 space-y-1">
    {% for m in section.contexte.missions %}
      <li>
        {% if section.contexte.peut_ouvrir %}<a href="{% url 'missions:detail' m.pk %}" class="font-semibold underline underline-offset-2">{{ m.numero }}</a>{% else %}<strong>{{ m.numero }}</strong>{% endif %}
        · départ prévu le {{ m.date_depart_prevue|date:"d/m/Y" }} · {{ m.client }} · {{ m.lieu_chargement }} → {{ m.lieu_livraison }}
        · {% badge m.statut m.get_statut_display %}
      </li>
    {% endfor %}
  </ul>
  <p class="mt-2">Vérifiez avec l'exploitation que la mission peut être réaffectée avant de valider.</p>
</div>
```

#### `apps/missions/templates/missions/_missions_client.html`

*21 lignes*

```django
{% load ui humanize %}
<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-missions-client">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 id="titre-missions-client" class="text-base font-semibold text-slate-900">Missions ({{ section.contexte.total }})</h2>
  </div>
  {% if section.contexte.missions %}
    <ul class="mt-4 divide-y divide-slate-100 text-sm">
      {% for m in section.contexte.missions %}
        <li class="flex flex-wrap items-center justify-between gap-2 py-2">
          <span>
            <a href="{% url 'missions:detail' m.pk %}" class="font-semibold text-marque-700 underline-offset-2 hover:underline">{{ m.numero }}</a>
            <span class="text-slate-700">· {{ m.lieu_chargement }} → {{ m.lieu_livraison }} · {{ m.prix_convenu|floatformat:0|intcomma }} FCFA</span>
          </span>
          {% badge m.statut m.get_statut_display %}
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="mt-3 text-sm text-slate-600">Aucune mission pour ce client.</p>
  {% endif %}
</section>
```

## Étape 3 — Tests

#### `apps/accounts/tests/test_web.py`

*221 lignes* — Connexion, accueil, menu par rôle et garde d'accès.

```python
"""Connexion, accueil, menu par rôle et garde d'accès."""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts import navigation
from apps.accounts.models import Role
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


# --- connexion / déconnexion ---


def test_la_page_de_connexion_s_affiche(client):
    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 200
    assert "Se connecter" in reponse.content.decode()


def test_connexion_reussie_redirige_vers_l_accueil_et_est_tracee(client):
    utilisateur = UserFactory(username="awa", role=Role.DIRECTION)

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": MOT_DE_PASSE}
    )

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, utilisateur=utilisateur, statut=StatutChoices.SUCCESS
    ).exists()


def test_connexion_avec_un_mauvais_mot_de_passe_affiche_une_erreur_et_est_tracee(client):
    UserFactory(username="awa")

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": "faux"}
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].non_field_errors()
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, statut=StatutChoices.FAILED
    ).exists()


def test_un_utilisateur_connecte_qui_ouvre_la_connexion_va_a_l_accueil(client):
    _connecte(client, Role.RH)

    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")


def test_deconnexion_par_post_ferme_la_session_et_est_tracee(client):
    utilisateur = _connecte(client, Role.RH)

    reponse = client.post(reverse("accounts:logout"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("accounts:login")
    assert client.get(reverse("home")).status_code == 302
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGOUT, utilisateur=utilisateur
    ).exists()


def test_la_deconnexion_refuse_le_get(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("accounts:logout")).status_code == 405


def test_la_deconnexion_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory())

    assert client.post(reverse("accounts:logout")).status_code == 403


def test_la_session_expire_apres_30_minutes_d_inactivite():
    assert settings.SESSION_COOKIE_AGE == 30 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


# --- accueil ---


def test_l_accueil_exige_une_connexion_et_conserve_la_destination(client):
    reponse = client.get(reverse("home"))

    assert reponse.status_code == 302
    assert reponse.url == f"{reverse('accounts:login')}?next=/"


def test_l_accueil_salue_l_utilisateur(client):
    utilisateur = UserFactory(role=Role.DIRECTION, first_name="Awa")
    client.force_login(utilisateur)

    contenu = client.get(reverse("home")).content.decode()

    assert "Bonjour Awa" in contenu
    assert "Direction" in contenu


def test_le_menu_depend_du_role(client):
    _connecte(client, Role.DIRECTION)
    assert 'href="/missions/"' in client.get(reverse("home")).content.decode()

    finances = Client()
    _connecte(finances, Role.FINANCES)  # seuls les congés sont ouverts à ce rôle pour l'instant
    contenu = finances.get(reverse("home")).content.decode()
    assert 'href="/missions/"' not in contenu
    assert 'href="/rh/conges/"' in contenu
    assert "Aucun écran n" not in contenu

    chauffeur = Client()
    _connecte(chauffeur, Role.CHAUFFEUR)  # passe par l'espace mobile : aucun écran web
    assert "Aucun écran n" in chauffeur.get(reverse("home")).content.decode()


def test_un_chauffeur_est_renvoye_vers_l_espace_mobile(client):
    _connecte(client, Role.CHAUFFEUR)

    assert "espace mobile" in client.get(reverse("home")).content.decode()


def test_un_superutilisateur_sans_role_agit_en_admin(client):
    admin = UserFactory(role="", is_superuser=True, is_staff=True)
    client.force_login(admin)

    assert admin.role_effectif == Role.ADMIN
    assert client.get(reverse("missions:liste")).status_code == 200


# --- pages d'erreur ---


def test_un_role_non_autorise_recoit_la_page_403(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("missions:liste"))

    assert reponse.status_code == 403
    assert "Accès refusé" in reponse.content.decode()


def test_une_page_inexistante_affiche_la_page_404(client, settings):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["testserver"]
    _connecte(client, Role.DIRECTION)

    reponse = client.get("/n-existe-pas/")

    assert reponse.status_code == 404
    assert "Page introuvable" in reponse.content.decode()


# --- navigation ---


def test_entrees_pour_filtre_par_role_trie_et_marque_l_entree_active(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    reserve_rh = navigation.EntreeMenu(
        "Réservé RH", "missions:liste", "fa-flask", frozenset({Role.RH}), ordre=5
    )
    monkeypatch.setattr(
        navigation, "_ENTREES", {"missions:liste": reserve_rh, "home": accueil}
    )

    rh = navigation.entrees_pour(Role.RH, "/missions/")
    finances = navigation.entrees_pour(Role.FINANCES, "/missions/")

    assert [e["libelle"] for e in rh] == ["Accueil", "Réservé RH"]
    assert [e["actif"] for e in rh] == [False, True]
    assert [e["libelle"] for e in finances] == ["Accueil"]


def test_l_accueil_n_est_actif_que_sur_la_racine(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil})

    assert navigation.entrees_pour(Role.RH, "/")[0]["actif"] is True
    assert navigation.entrees_pour(Role.RH, "/missions/")[0]["actif"] is False


def test_une_entree_dont_l_ecran_n_existe_pas_est_ignoree_sans_erreur(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    fantome = navigation.EntreeMenu("Fantôme", "ecran:inexistant", "fa-ghost", None, ordre=1)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil, "ecran:inexistant": fantome})

    assert [e["libelle"] for e in navigation.entrees_pour(Role.RH, "/")] == ["Accueil"]


def test_aucun_commentaire_de_template_ne_fuit_dans_les_pages(client):
    """`{# ... #}` multi-lignes s'afficherait en texte brut : régression déjà vue."""
    pages = [reverse("accounts:login")]
    _connecte(client, Role.DIRECTION)
    pages += [reverse("home"), reverse("missions:liste"), reverse("missions:creer")]

    for url in pages:
        contenu = client.get(url).content.decode()
        assert "{#" not in contenu and "#}" not in contenu, url
        assert "{%" not in contenu and "%}" not in contenu, url
```

#### `apps/customers/tests/test_views.py`

*376 lignes* — Écrans clients : accès par rôle, portefeuille, fiche, création, interactions.

```python
"""Écrans clients : accès par rôle, portefeuille, fiche, création, interactions."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services
from apps.customers.models import Client, Interaction, TypeInteraction
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "raison_sociale": "Cimaf CI",
        "ncc_nif": "CI-1234567A",
        "contact_principal": "Awa Coulibaly",
        "telephone": "+2250700000000",
        "email": "awa@cimaf.ci",
        "adresse": "Abidjan, Plateau",
        "charge_clientele": "",
        "taux_tva": "18",
        "motif_exoneration": "",
        "delai_paiement_jours": "30",
    }
    donnees.update(surcharges)
    return donnees


def _interaction(**surcharges):
    donnees = {
        "type_interaction": "APPEL",
        "date_interaction": (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "resume": "Point sur la livraison de mardi",
    }
    donnees.update(surcharges)
    return donnees


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_clients_sont_accessibles_a_admin_direction_et_charge_clientele(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    assert client.get(reverse("customers:liste")).status_code == 200
    assert client.get(reverse("customers:detail", args=[fiche.pk])).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_clients_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    for url in (
        reverse("customers:liste"),
        reverse("customers:detail", args=[fiche.pk]),
        reverse("customers:creer"),
        reverse("customers:modifier", args=[fiche.pk]),
    ):
        assert client.get(url).status_code == 403, url


def test_la_direction_est_en_lecture_seule(client):
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()

    assert client.get(reverse("customers:creer")).status_code == 403
    assert client.get(reverse("customers:modifier", args=[fiche.pk])).status_code == 403
    assert client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction()).status_code == 403
    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()
    assert "Modifier" not in texte and "Ajouter une interaction" not in texte


def test_les_clients_exigent_la_connexion(client):
    assert client.get(reverse("customers:liste")).status_code == 302


# --- liste ---


def test_la_liste_affiche_les_clients_et_filtre(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)
    ClientFactory(raison_sociale="Cimaf", charge_clientele=charge)
    ClientFactory(raison_sociale="Solibra", taux_tva=Decimal("0"), motif_exoneration="ONG")

    tous = client.get(reverse("customers:liste"))
    recherche = client.get(reverse("customers:liste"), {"q": "soli"})
    portefeuille = client.get(reverse("customers:liste"), {"mes_clients": "on"})
    exonere = client.get(reverse("customers:liste"), {"exonere": "on"})

    assert len(tous.context["clients"]) == 2
    assert [c.raison_sociale for c in recherche.context["clients"]] == ["Solibra"]
    assert [c.raison_sociale for c in portefeuille.context["clients"]] == ["Cimaf"]
    assert [c.raison_sociale for c in exonere.context["clients"]] == ["Solibra"]
    assert "Mon portefeuille" in tous.content.decode()
    assert "Exonéré" in exonere.content.decode()


def test_le_filtre_portefeuille_n_est_propose_qu_au_charge_clientele(client):
    _connecte(client, Role.DIRECTION)

    assert "Mon portefeuille" not in client.get(reverse("customers:liste")).content.decode()


def test_la_liste_vide_invite_a_creer_un_client(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    texte = client.get(reverse("customers:liste")).content.decode()

    assert "Créez la fiche du premier client" in texte


def test_la_liste_signale_les_reclamations(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.RECLAMATION, resume="Retard"
    )

    reponse = client.get(reverse("customers:liste"))

    assert reponse.context["clients"][0].nb_reclamations == 1


def test_la_liste_des_clients_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    for _ in range(12):
        fiche = ClientFactory(charge_clientele=auteur)
        services.enregistrer_interaction(fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="x")

    with django_assert_max_num_queries(8):
        assert client.get(reverse("customers:liste")).status_code == 200


# --- fiche ---


def test_la_fiche_affiche_les_informations_et_l_historique(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="Cimaf CI", taux_tva=Decimal("0"), motif_exoneration="ONG")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.REUNION, resume="Réunion de cadrage"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Cimaf CI" in texte and "Exonéré : ONG" in texte
    assert "Réunion de cadrage" in texte and "Historique commercial (1)" in texte


def test_la_fiche_liste_les_missions_du_client(client):
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()
    mission = MissionFactory(client=fiche, statut=StatutMission.PLANIFIEE)
    MissionFactory(client=ClientFactory())  # mission d'un autre client

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Missions (1)" in texte and mission.numero in texte


def test_les_textes_saisis_sont_echappes(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="<script>alert(1)</script>")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="<img src=x onerror=alert(2)>"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "<img src=x" not in texte
    assert "&lt;img src=x onerror=alert(2)&gt;" in texte


def test_un_client_inexistant_donne_404(client):
    _connecte(client, Role.ADMIN)

    assert client.get(reverse("customers:detail", args=[999])).status_code == 404


# --- création et modification ---


def test_le_charge_clientele_cree_un_client(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(
        reverse("customers:creer"), _donnees(charge_clientele=charge.pk), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.charge_clientele == charge and fiche.taux_tva == Decimal("18")
    assert reponse.redirect_chain[-1][0] == reverse("customers:detail", args=[fiche.pk])
    assert any("Cimaf CI" in m for m in _messages(reponse))


def test_creation_d_un_client_exonere_sans_motif_est_refusee(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(reverse("customers:creer"), _donnees(taux_tva="0"))

    assert reponse.status_code == 200
    assert "Motif obligatoire" in reponse.content.decode()
    assert not Client.objects.exists()


def test_creation_d_un_client_exonere_avec_motif(client):
    _connecte(client, Role.ADMIN)

    client.post(reverse("customers:creer"), _donnees(taux_tva="0", motif_exoneration="EXPORT"))

    assert Client.objects.get().motif_exoneration == "EXPORT"


def test_un_nif_deja_utilise_est_signale(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-1234567A")

    reponse = client.post(reverse("customers:creer"), _donnees())

    assert "déjà utilisé" in reponse.content.decode()
    assert Client.objects.count() == 1


def test_le_formulaire_ne_propose_que_les_charges_clientele_actifs(client):
    _connecte(client, Role.ADMIN)
    bon = UserFactory(role=Role.CHARGE_CLIENTELE)
    autre = UserFactory(role=Role.FINANCES)

    propositions = set(
        client.get(reverse("customers:creer")).context["form"].fields["charge_clientele"].queryset
    )

    assert bon in propositions and autre not in propositions


def test_la_modification_met_a_jour_la_fiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]),
        _donnees(ncc_nif="CI-0000001A", telephone="+2250101010101"),
        follow=True,
    )

    fiche.refresh_from_db()
    assert fiche.telephone == "+2250101010101" and fiche.raison_sociale == "Cimaf CI"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.ADMIN)
    fiche = ClientFactory(raison_sociale="Solibra")

    reponse = client.get(reverse("customers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["raison_sociale"] == "Solibra"


def test_la_creation_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.ADMIN))

    assert http.post(reverse("customers:creer"), _donnees()).status_code == 403


# --- interactions ---


def test_le_charge_clientele_ajoute_une_interaction(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction(), follow=True)

    interaction = Interaction.objects.get()
    assert interaction.auteur == auteur and interaction.client == fiche
    assert any("ajoutée" in m for m in _messages(reponse))
    assert "Point sur la livraison de mardi" in reponse.content.decode()


def test_une_interaction_sans_resume_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]), _interaction(resume=""), follow=True
    )

    assert not Interaction.objects.exists()
    assert _messages(reponse)


def test_une_interaction_dans_le_futur_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    demain = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]),
        _interaction(date_interaction=demain),
        follow=True,
    )

    assert not Interaction.objects.exists()
    assert any("futur" in m for m in _messages(reponse))


def test_l_interaction_n_accepte_que_post_et_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    fiche = ClientFactory()
    url = reverse("customers:interaction", args=[fiche.pk])

    assert http.get(url).status_code == 405
    assert http.post(url, _interaction()).status_code == 403


def test_la_modification_refuse_le_nif_d_un_autre_client(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-0000009A")
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]), _donnees(ncc_nif="CI-0000009A")
    )

    assert "déjà utilisé" in reponse.content.decode()
    fiche.refresh_from_db()
    assert fiche.ncc_nif == "CI-0000001A"


def test_le_delai_de_paiement_se_saisit_et_s_affiche(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(
        reverse("customers:creer"), _donnees(delai_paiement_jours="45"), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.delai_paiement_jours == 45
    assert "45 jours" in reponse.content.decode()


def test_le_delai_de_paiement_doit_etre_entre_1_et_365_jours(client):
    _connecte(client, Role.ADMIN)

    for valeur in ("0", "366", "abc"):
        reponse = client.post(reverse("customers:creer"), _donnees(delai_paiement_jours=valeur))
        assert reponse.status_code == 200, valeur
    assert not Client.objects.exists()
```

#### `apps/drivers/tests/test_views.py`

*350 lignes* — Écrans des chauffeurs : accès par rôle, liste, fiche, modification, statut.

```python
"""Écrans des chauffeurs : accès par rôle, liste, fiche, modification, statut."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "telephone": "+2250701020304",
        "contact_urgence": "Awa - 0700000000",
        "numero_permis": "PC-555",
        "categories_permis": ["C", "E"],
        "date_expiration_permis": "2029-05-01",
        "date_expiration_visite_medicale": "2027-05-01",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.RH])
def test_les_chauffeurs_sont_accessibles_a_la_direction_a_la_rh_et_a_l_admin(client, role):
    _connecte(client, role)

    assert client.get(reverse("drivers:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.PARCAUTO, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_les_chauffeurs_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:liste")).status_code == 403
    assert client.get(reverse("drivers:detail", args=[fiche.pk])).status_code == 403
    assert client.get(reverse("drivers:modifier", args=[fiche.pk])).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("drivers:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_chauffeurs_est_visible_de_la_rh_mais_pas_du_parc_auto(client):
    _connecte(client, Role.RH)
    assert 'href="/chauffeurs/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.PARCAUTO)
    assert 'href="/chauffeurs/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_chauffeurs_avec_leur_statut(client):
    _connecte(client, Role.DIRECTION)
    ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa", telephone="0700112233")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "Moussa Traoré" in contenu
    assert "0700112233" in contenu
    assert "Disponible" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucun chauffeur trouvé" in client.get(reverse("drivers:liste")).content.decode()


def test_la_liste_filtre_par_statut_et_recherche(client):
    _connecte(client, Role.RH)
    libre = ChauffeurFactory(personnel__nom="Adou")
    ChauffeurFactory(personnel__nom="Bamba", statut=StatutChauffeur.SUSPENDU)

    par_statut = client.get(reverse("drivers:liste"), {"statut": "DISPONIBLE"})
    par_texte = client.get(reverse("drivers:liste"), {"q": "adou"})

    assert [l["chauffeur"] for l in par_statut.context["lignes"]] == [libre]
    assert [l["chauffeur"] for l in par_texte.context["lignes"]] == [libre]


def test_la_liste_signale_et_filtre_les_echeances_proches(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    alerte = ChauffeurFactory(
        personnel__nom="Alerte", date_expiration_permis=aujourdhui + timedelta(days=10)
    )
    ChauffeurFactory(
        personnel__nom="Tranquille",
        date_expiration_permis=aujourdhui + timedelta(days=900),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=900),
    )

    complet = client.get(reverse("drivers:liste"))
    filtre = client.get(reverse("drivers:liste"), {"alerte": "1"})

    assert "À renouveler" in complet.content.decode()
    assert [l["chauffeur"] for l in filtre.context["lignes"]] == [alerte]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        ChauffeurFactory()

    page2 = client.get(reverse("drivers:liste"), {"page": 2})

    assert len(page2.context["lignes"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_chauffeur(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        ChauffeurFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("drivers:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    ChauffeurFactory(telephone="<script>alert(1)</script>")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_l_identite_les_contacts_et_les_echeances(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    fiche = ChauffeurFactory(
        personnel__nom="Traoré",
        personnel__prenom="Moussa",
        personnel__matricule="CH-007",
        telephone="0700112233",
        contact_urgence="Fatou 0701",
        numero_permis="PC-42",
        categories_permis=["C", "E"],
        date_expiration_permis=aujourdhui - timedelta(days=5),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=12),
    )

    reponse = client.get(reverse("drivers:detail", args=[fiche.pk]))
    contenu = reponse.content.decode()

    for attendu in ("Moussa Traoré", "CH-007", "0700112233", "Fatou 0701", "PC-42", "C, E"):
        assert attendu in contenu, attendu
    assert "Expiré" in contenu and "depuis 5 j" in contenu
    assert "À renouveler" in contenu and "dans 12 j" in contenu


def test_la_fiche_signale_les_informations_manquantes(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    contenu = client.get(reverse("drivers:detail", args=[fiche.pk])).content.decode()

    assert "Non renseigné" in contenu and "Non renseignées" in contenu


def test_la_fiche_d_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("drivers:detail", args=[999999])).status_code == 404


def test_la_fiche_propose_le_changement_de_statut_sauf_en_mission_ou_en_conge(client):
    _connecte(client, Role.DIRECTION)
    libre = ChauffeurFactory()
    en_mission = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    page_libre = client.get(reverse("drivers:detail", args=[libre.pk])).content.decode()
    page_mission = client.get(reverse("drivers:detail", args=[en_mission.pk])).content.decode()

    assert reverse("drivers:statut", args=[libre.pk]) in page_libre
    assert reverse("drivers:statut", args=[en_mission.pk]) not in page_mission
    assert "géré automatiquement" in page_mission


# --- modification ---


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory(telephone="0700112233", categories_permis=["C"])

    reponse = client.get(reverse("drivers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["telephone"] == "0700112233"
    assert reponse.context["form"].initial["categories_permis"] == ["C"]
    assert fiche.personnel.matricule in reponse.content.decode()


def test_modifier_une_fiche(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees(), follow=True)

    fiche.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("drivers:detail", args=[fiche.pk])
    assert fiche.numero_permis == "PC-555"
    assert fiche.categories_permis == ["C", "E"]
    assert str(fiche.date_expiration_permis) == "2029-05-01"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_modifier_avec_une_categorie_inconnue_est_refuse_par_le_formulaire(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(categories_permis=["C", "Z"])
    )

    fiche.refresh_from_db()
    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert fiche.categories_permis == []


def test_modifier_avec_une_date_invalide_est_refuse(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(date_expiration_permis="31/02/2029")
    )

    assert reponse.context["form"].errors
    fiche.refresh_from_db()
    assert fiche.numero_permis == ""


def test_modifier_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("drivers:modifier", args=[999999])).status_code == 404


# --- statut ---


def test_suspendre_puis_reactiver_un_chauffeur(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU
    assert any("Suspendu" in m for m in _messages(reponse))

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "DISPONIBLE"})
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_changer_le_statut_d_un_chauffeur_en_mission_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION
    assert any("missions et les congés" in m for m in _messages(reponse))


@pytest.mark.parametrize("cible", ["EN_MISSION", "EN_CONGE", "VOLANT", ""])
def test_un_statut_non_manuel_est_refuse_par_le_formulaire(client, cible):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": cible})

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_le_changement_de_statut_refuse_le_get(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:statut", args=[fiche.pk])).status_code == 405


def test_un_chauffeur_suspendu_ne_peut_plus_etre_affecte_a_une_mission():
    """Lien avec les missions : l'affectation exige un chauffeur « Disponible »."""
    from apps.fleet.tests.factories import VehiculeFactory
    from apps.missions import services as missions_services
    from apps.missions.exceptions import AffectationImpossible
    from apps.missions.tests.test_services import _planifiee
    from apps.drivers import services

    fiche = ChauffeurFactory()
    services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)

    with pytest.raises(AffectationImpossible, match="chauffeur"):
        missions_services.affecter_mission(
            _planifiee(), vehicule=VehiculeFactory(), chauffeur=fiche
        )


def test_les_formulaires_des_chauffeurs_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    fiche = ChauffeurFactory()

    assert client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees()).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE and fiche.numero_permis == ""
```

#### `apps/missions/tests/test_alerte_conge.py`

*114 lignes* — Alerte N1 : le chauffeur qui demande un congé a une mission prévue sur la période.

```python
"""Alerte N1 : le chauffeur qui demande un congé a une mission prévue sur la période.

Cahier-des-charges.md:219-221. Bloc fourni par ``missions`` à la fiche d'un congé.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr import services
from apps.hr.tests.factories import PersonnelFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


@pytest.fixture
def cas():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    fiche = ChauffeurFactory(personnel=PersonnelFactory(poste="Chauffeur", superieur=superieur))
    conge = services.demander_conge(
        fiche.personnel, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT
    )
    return conge, fiche, compte_sup


def _page(client, compte, conge):
    client.force_login(compte)
    return client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()


def test_le_validateur_est_prevenu_d_une_mission_sur_la_periode(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    texte = _page(client, compte_sup, conge)

    assert "1 mission prévue pendant cette période" in texte
    assert mission.numero in texte


def test_le_lien_vers_la_mission_est_reserve_aux_roles_qui_y_ont_acces(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    lien = reverse("missions:detail", args=[mission.pk])

    assert lien not in _page(client, compte_sup, conge)  # PARCAUTO n'a pas accès aux missions
    assert lien in _page(client, UserFactory(role=Role.DIRECTION), conge)


@pytest.mark.parametrize(
    "surcharges",
    [
        {"date_depart_prevue": date(2026, 10, 12)},  # après la période
        {"date_depart_prevue": date(2026, 10, 2)},  # avant la période
        {"date_depart_prevue": None},  # pas de date : non détectable
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.CLOTUREE},
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.BROUILLON},
    ],
)
def test_aucune_alerte_hors_periode_ou_hors_mission_active(client, cas, surcharges):
    conge, fiche, compte_sup = cas
    donnees = {"statut": StatutMission.PLANIFIEE, **surcharges}
    if donnees["statut"] == StatutMission.CLOTUREE:
        donnees["vehicule"] = VehiculeFactory()  # une mission clôturée a un camion
    MissionFactory(chauffeur=fiche, **donnees)

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_la_mission_d_un_autre_chauffeur_ne_declenche_pas_d_alerte(client, cas):
    conge, fiche, compte_sup = cas
    autre = ChauffeurFactory()
    MissionFactory(
        chauffeur=autre, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_plus_d_alerte_une_fois_le_conge_decide(client, cas):
    conge, fiche, compte_sup = cas
    MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    services.refuser(conge, compte_sup, commentaire="Mission prévue")

    assert "mission prévue pendant" not in _page(client, compte_sup, conge)


def test_la_section_missions_du_client_est_reservee_aux_roles_des_missions():
    from apps.customers.tests.factories import ClientFactory
    from apps.missions import sections

    fiche = ClientFactory()

    assert sections.section_missions_client(fiche, UserFactory(role=Role.RH)) is None
    assert sections.section_missions_client(fiche, UserFactory(role=Role.DIRECTION)) is not None
```

#### `apps/missions/tests/test_qr.py`

*109 lignes* — Image QR des codes d'une mission : droits, contenu, secret.

```python
"""Image QR des codes d'une mission : droits, contenu, secret."""

import io

import pytest
import qrcode
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def _png(code):
    tampon = io.BytesIO()
    qrcode.make(code, box_size=8, border=2).save(tampon, format="PNG")
    return tampon.getvalue()


def _mission(statut=StatutMission.AFFECTEE):
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory

    return MissionFactory(
        statut=statut, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
        code_expediteur="ABCD2345", code_destinataire="WXYZ6789",
    )


def test_le_qr_est_une_image_png_qui_ne_contient_que_le_code(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _mission()

    exp = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))
    dest = client.get(reverse("missions:qr", args=[mission.pk, "destinataire"]))

    assert exp.status_code == 200 and exp["Content-Type"] == "image/png"
    assert exp.content.startswith(b"\x89PNG") and Image.open(io.BytesIO(exp.content)).size[0] > 100
    assert exp.content == _png("ABCD2345") and dest.content == _png("WXYZ6789")  # contenu = le code seul
    assert exp.content != dest.content


def test_le_qr_n_est_jamais_mis_en_cache(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = _mission()

    reponse = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))

    assert reponse["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_roles_qui_voient_les_codes_voient_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 200


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.PARCAUTO, Role.RH, Role.FINANCES])
def test_les_autres_roles_n_obtiennent_pas_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 403


def test_le_qr_exige_la_connexion(client):
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 302


def test_un_qr_inutile_ou_inconnu_est_un_404(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    recuperee = _mission(StatutMission.EN_COURS_COLIS_RECUPERE)
    livree = _mission(StatutMission.LIVREE)

    assert client.get(reverse("missions:qr", args=[recuperee.pk, "expediteur"])).status_code == 404  # colis déjà récupéré
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "destinataire"])).status_code == 200
    assert client.get(reverse("missions:qr", args=[livree.pk, "destinataire"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "autre"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[99999, "expediteur"])).status_code == 404


def test_la_fiche_de_la_mission_affiche_les_qr_pour_le_bon_role(client):
    mission = _mission()

    client.force_login(UserFactory(role=Role.DIRECTION))
    texte = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert reverse("missions:qr", args=[mission.pk, "expediteur"]) in texte
    assert reverse("missions:qr", args=[mission.pk, "destinataire"]) in texte
    assert "Code QR de l&#x27;expéditeur" in texte or "Code QR de l'expéditeur" in texte


def test_le_qr_ne_fuite_pas_dans_la_fiche_des_roles_sans_droit(client):
    mission = _mission()
    client.force_login(UserFactory(role=Role.ADMIN))
    assert "/qr/" in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    http = Client()
    http.force_login(UserFactory(role=Role.CHAUFFEUR))
    assert http.get(reverse("missions:detail", args=[mission.pk])).status_code == 403
```

#### `apps/missions/tests/test_views.py`

*575 lignes* — Écrans des missions : accès par rôle, affichage, actions du cycle de vie.

```python
"""Écrans des missions : accès par rôle, affichage, actions du cycle de vie."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.missions import services
from apps.missions.models import Mission, StatutMission

from .factories import MissionFactory
from .test_services import (
    _affectee,
    _creer,
    _en_cours,
    _livree,
    _planifiee,
    _recuperee,
)

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _url(nom, mission):
    return reverse(f"missions:{nom}", args=[mission.pk])


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_la_liste_est_accessible_aux_roles_de_gestion(client, role):
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHAUFFEUR]
)
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 403


@pytest.mark.parametrize(
    "nom", ["liste", "creer"]
)
def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client, nom):
    reponse = client.get(reverse(f"missions:{nom}"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


# --- liste ---


def test_la_liste_affiche_les_missions(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert mission.numero in contenu
    assert mission.client.raison_sociale in contenu
    assert "Planifiée" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucune mission trouvée" in client.get(reverse("missions:liste")).content.decode()


def test_la_liste_filtre_par_statut(client):
    _connecte(client, Role.DIRECTION)
    brouillon, planifiee = _creer(), _planifiee()

    reponse = client.get(reverse("missions:liste"), {"statut": StatutMission.PLANIFIEE})

    assert list(reponse.context["missions"]) == [planifiee]
    assert brouillon.numero not in reponse.content.decode()


def test_la_liste_ignore_un_statut_inconnu(client):
    _connecte(client, Role.DIRECTION)
    _creer()

    reponse = client.get(reverse("missions:liste"), {"statut": "N_IMPORTE_QUOI"})

    assert len(reponse.context["missions"]) == 1


def test_la_liste_recherche_par_client_numero_ou_lieu(client):
    _connecte(client, Role.DIRECTION)
    cible = _creer(client=ClientFactory(raison_sociale="Cimaf Côte d'Ivoire"))
    _creer(lieu_livraison="Korhogo")

    par_client = client.get(reverse("missions:liste"), {"q": "cimaf"})
    par_numero = client.get(reverse("missions:liste"), {"q": cible.numero})
    par_lieu = client.get(reverse("missions:liste"), {"q": "korhogo"})

    assert list(par_client.context["missions"]) == [cible]
    assert list(par_numero.context["missions"]) == [cible]
    assert len(par_lieu.context["missions"]) == 1


def test_la_liste_est_paginee_par_20_et_conserve_les_filtres(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        MissionFactory(statut=StatutMission.BROUILLON)

    page1 = client.get(reverse("missions:liste"), {"statut": "BROUILLON"})
    page2 = client.get(reverse("missions:liste"), {"statut": "BROUILLON", "page": 2})

    assert len(page1.context["missions"]) == 20
    assert len(page2.context["missions"]) == 1
    assert "statut=BROUILLON" in page1.content.decode()  # lien « Suivant »


def test_la_liste_n_effectue_pas_une_requete_par_mission(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        MissionFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("missions:liste"))


def test_le_contenu_saisi_est_echappe_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    _creer(lieu_chargement="<script>alert('xss')</script>")

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert "<script>alert('xss')</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_le_detail(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert mission.numero in contenu
    assert mission.vehicule.immatriculation in contenu
    assert mission.chauffeur.personnel.nom in contenu


def test_la_fiche_d_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("missions:detail", args=[999999])).status_code == 404


def test_la_frise_marque_l_etape_courante(client):
    _connecte(client, Role.DIRECTION)
    mission = _en_cours()

    reponse = client.get(_url("detail", mission))

    etapes = reponse.context["etapes"]
    assert [e["etat"] for e in etapes] == [
        "faite", "faite", "faite", "courante", "a_venir", "a_venir", "a_venir",
    ]
    assert reponse.content.decode().count('aria-current="step"') == 1


@pytest.mark.parametrize(
    ("etape", "expediteur", "destinataire"),
    [
        (_creer, True, True),
        (_en_cours, True, True),
        (_recuperee, False, True),  # colis récupéré : le code expéditeur ne sert plus
        (_livree, False, False),  # livrée : plus aucun code utile
    ],
)
def test_les_codes_ne_s_affichent_que_tant_qu_ils_servent(client, etape, expediteur, destinataire):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert (mission.code_expediteur in contenu) is expediteur
    assert (mission.code_destinataire in contenu) is destinataire


# --- actions proposées selon rôle et statut ---


def test_le_charge_clientele_peut_planifier_un_brouillon_mais_pas_affecter(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    brouillon = _creer()
    planifiee = _planifiee()

    page_brouillon = client.get(_url("detail", brouillon)).content.decode()
    page_planifiee = client.get(_url("detail", planifiee)).content.decode()

    assert _url("planifier", brouillon) in page_brouillon
    assert _url("affecter", planifiee) not in page_planifiee
    assert "Aucune action disponible" in page_planifiee


def test_la_direction_voit_le_formulaire_d_affectation_avec_les_seuls_camions_disponibles(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    libre = VehiculeFactory(immatriculation="1111 AA 01")
    VehiculeFactory(immatriculation="2222 BB 01", statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.get(_url("detail", mission))
    contenu = reponse.content.decode()

    assert _url("affecter", mission) in contenu
    assert libre.immatriculation in contenu
    assert "2222 BB 01" not in contenu


@pytest.mark.parametrize(
    ("etape", "action_attendue"),
    [
        (_affectee, "demarrer"),
        (_en_cours, "recuperation"),
        (_recuperee, "livraison"),
        (_livree, "cloturer"),
    ],
)
def test_la_direction_voit_l_action_de_l_etape(client, etape, action_attendue):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


def test_une_mission_cloturee_n_a_plus_d_action(client):
    _connecte(client, Role.ADMIN)
    mission = services.cloturer_mission(_livree())

    contenu = client.get(_url("detail", mission)).content.decode()

    assert "Aucune action disponible" in contenu


# --- création ---


def test_le_formulaire_de_creation_s_affiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.get(reverse("missions:creer"))

    assert reponse.status_code == 200
    assert "Nouvelle mission" in reponse.content.decode()


def test_creer_une_mission_valide(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan, Port",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "18.50",
            "prix_convenu": "850000",
            "date_depart_prevue": "2026-10-12",
        },
        follow=True,
    )

    mission = Mission.objects.get()
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert mission.statut == StatutMission.BROUILLON
    assert mission.poids_t == Decimal("18.50")
    assert str(mission.date_depart_prevue) == "2026-10-12"
    assert mission.numero in " ".join(_messages(reponse))


def test_creer_avec_un_poids_nul_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.DIRECTION)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "0",
            "prix_convenu": "1000",
        },
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_creer_sans_client_est_refuse(client):
    _connecte(client, Role.DIRECTION)

    reponse = client.post(reverse("missions:creer"), {"lieu_chargement": "x"})

    assert "client" in reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_la_creation_est_interdite_aux_autres_roles(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("missions:creer")).status_code == 403
    assert client.post(reverse("missions:creer"), {}).status_code == 403


# --- actions du cycle de vie ---


def test_planifier(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _creer()

    reponse = client.post(_url("planifier", mission), follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert any("planifiée" in m for m in _messages(reponse))


def test_une_action_refusee_par_le_service_affiche_l_erreur_sans_rien_changer(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()

    reponse = client.post(_url("planifier", mission), follow=True)  # déjà planifiée

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any("Impossible de planifier" in m for m in _messages(reponse))


def test_un_role_sans_droit_ne_peut_pas_agir_meme_par_post_direct(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.PLANIFIEE


def test_affecter(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE
    assert (mission.vehicule, mission.chauffeur) == (camion, chauffeur)


def test_affecter_un_camion_indisponible_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    en_panne = VehiculeFactory(statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": en_panne.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any(m for m in _messages(reponse))  # message d'erreur du formulaire


def test_affecter_une_charge_trop_lourde_affiche_l_erreur_du_service(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee(poids_t=Decimal("30"))
    petit = VehiculeFactory(capacite_charge_t=Decimal("10"))

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": petit.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    assert any("capacité" in m for m in _messages(reponse))
    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE


def test_demarrer(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    client.post(_url("demarrer", mission))

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert mission.vehicule.statut == StatutVehicule.EN_MISSION


def test_recuperation_avec_un_mauvais_code_est_refusee(client):
    _connecte(client, Role.DIRECTION)
    mission = _en_cours()

    reponse = client.post(_url("recuperation", mission), {"code": "AAAAAAAA"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert "Code incorrect." in _messages(reponse)


def test_recuperation_avec_le_bon_code_meme_en_minuscules(client):
    _connecte(client, Role.DIRECTION)
    mission = _en_cours()

    client.post(_url("recuperation", mission), {"code": mission.code_expediteur.lower()})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_livraison(client):
    _connecte(client, Role.DIRECTION)
    mission = _recuperee()

    client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart + 250},
    )

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.LIVREE
    assert mission.vehicule.kilometrage == mission.km_depart + 250
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


def test_livraison_avec_un_km_incoherent_est_refusee(client):
    _connecte(client, Role.DIRECTION)
    mission = _recuperee()

    reponse = client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart - 1},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert any("kilométrage" in m.lower() for m in _messages(reponse))


def test_livraison_sans_km_est_refusee_par_le_formulaire(client):
    _connecte(client, Role.DIRECTION)
    mission = _recuperee()

    client.post(_url("livraison", mission), {"code": mission.code_destinataire})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_cloturer(client):
    _connecte(client, Role.DIRECTION)
    mission = _livree()

    client.post(_url("cloturer", mission))

    mission.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE


def test_les_actions_refusent_le_get(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    assert client.get(_url("planifier", mission)).status_code == 405


def test_une_action_sur_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.post(reverse("missions:planifier", args=[999999])).status_code == 404


def test_les_actions_sont_protegees_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _creer()

    reponse = client.post(_url("planifier", mission))

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.BROUILLON


def test_un_parcours_complet_par_l_interface(client):
    """Brouillon → clôturée, uniquement par les écrans, avec les bons rôles."""
    charge = Client()
    _connecte(charge, Role.CHARGE_CLIENTELE)
    direction = Client()
    _connecte(direction, Role.DIRECTION)
    societe = ClientFactory()
    camion, chauffeur = VehiculeFactory(kilometrage=50000), ChauffeurFactory()

    charge.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Yamoussoukro",
            "nature_marchandise": "Riz",
            "poids_t": "12",
            "prix_convenu": "600000",
        },
    )
    mission = Mission.objects.get()
    charge.post(_url("planifier", mission))
    direction.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )
    direction.post(_url("demarrer", mission))
    mission.refresh_from_db()
    direction.post(_url("recuperation", mission), {"code": mission.code_expediteur})
    direction.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": 50240},
    )
    direction.post(_url("cloturer", mission))

    mission.refresh_from_db()
    camion.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE
    assert camion.kilometrage == 50240 and camion.statut == StatutVehicule.DISPONIBLE
```

Ce chapitre présente de nombreux tests laissés plus tôt car ils ouvrent des pages qui dépendent des missions :
les tests de connexion et de menu par rôle (`accounts/test_web.py`), des fiches des clients et des chauffeurs
(qui affichent des missions), l'alerte de congé et les codes QR.

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
python -m pytest apps/accounts/tests/test_web.py apps/customers/tests/test_views.py apps/drivers/tests/test_views.py apps/missions/tests/test_alerte_conge.py apps/missions/tests/test_qr.py apps/missions/tests/test_views.py -q --no-cov
```

**Résultat attendu :** `157 passed, 5 failed` (pour les 6 fichier(s) de tests présentés dans ce chapitre).

Des tests échouent à ce stade, **c'est normal** : ils vérifient des écrans qui n'existent pas encore (par exemple la page d'accueil). Ils passeront au chapitre indiqué :

- `test_web.py::test_deconnexion_par_post_ferme_la_session_et_est_tracee` → chapitre 26 (« La page d'accueil : le tableau de bord »)
- `test_web.py::test_l_accueil_exige_une_connexion_et_conserve_la_destination` → chapitre 26 (« La page d'accueil : le tableau de bord »)
- `test_web.py::test_l_accueil_salue_l_utilisateur` → chapitre 26 (« La page d'accueil : le tableau de bord »)
- `test_web.py::test_le_menu_depend_du_role` → chapitre 26 (« La page d'accueil : le tableau de bord »)
- `test_web.py::test_un_chauffeur_est_renvoye_vers_l_espace_mobile` → chapitre 26 (« La page d'accueil : le tableau de bord »)

Les cinq tests de `accounts/test_web.py` qui dépendent du **tableau de bord** échouent encore : ils passeront au
chapitre 26 (c'est attendu).

**Un parcours complet dans le navigateur** (`python manage.py runserver`) :

1. **`demo_charge`** : « Nouvelle mission » (client `Cimaf CI`, Abidjan → Bouaké, ciment, 22 tonnes, 780 000).
   Sur la fiche (statut **Brouillon**), cliquez **Planifier**.
2. **`demo_direction`** : ouvrez la mission, **Affecter** : choisissez le camion `1234 AB 01` et le chauffeur
   `Moussa Ouattara`. Essayez d'affecter une mission de **30 tonnes** : le service refuse (capacité 25 t).
3. **Démarrer** la mission : le camion et le chauffeur passent « En mission » (vérifiez dans Flotte et Chauffeurs).
   La fiche affiche **deux codes de 8 caractères et leurs QR**.
4. **Récupération** : saisissez le **code de l'expéditeur** (un mauvais code est refusé). Puis **Livraison** avec le
   **code du destinataire** et un kilométrage d'arrivée : la mission passe **Livrée**, le camion redevient
   Disponible et son compteur est à jour.
5. **Clôturer** la mission (Direction).
6. Avec **`demo_parcauto`**, ouvrez `/missions/` : **Accès refusé**. Avec **`demo_charge`**, la mission n'affiche
   plus le bouton « Affecter » (réservé à la Direction).
7. Le journal d'audit (`/admin/audit/auditlog/`, en tant qu'**administrateur** avec la MFA) montre chaque
   transition, **sans** aucun code secret.

## Ce qu'il faut retenir

- **Le service décide, la vue re-vérifie, le gabarit affiche** : trois couches, une seule règle.
- Une **image** peut être servie par une vue ordinaire ; on lui applique les mêmes gardes que pour une page.
- Un secret montré à l'écran ne doit **jamais être mis en cache**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 21 : écrans des missions (cycle de vie, actions, codes QR)"
```

---

[← Chapitre 20](20-ecrans-flotte.md) · [Sommaire](README.md) · [Chapitre 22 →](22-ecrans-garage.md)
