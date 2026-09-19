# Comprendre le code de l'interface, du début à la fin

Ce guide explique comment fonctionne l'interface web de l'ERP DEN Source Group, dans l'ordre où
les choses se produisent quand un utilisateur clique. Tous les extraits sont réels : les numéros de
ligne (`fichier:ligne`) renvoient au code du projet. Lisez-le une fois de haut en bas, puis
servez-vous de la carte de la partie 9 pour retrouver un fichier.

---

## 1. L'idée générale en une image

Chaque écran suit le même chemin, toujours dans le même sens :

```
Navigateur  ──►  URL  ──►  Vue  ──►  Formulaire  ──►  Service  ──►  Modèle (base de données)
                            │                            │
                            └───────────  Gabarit HTML  ◄┘
```

| Couche | Fichier type | Sa seule responsabilité |
|---|---|---|
| **URL** | `urls.py` | Dire quelle vue répond à quelle adresse |
| **Vue** | `views.py` | Vérifier le rôle, lire la demande, appeler un service, choisir la page à afficher |
| **Formulaire** | `forms.py` | Lire et valider ce que l'utilisateur a saisi |
| **Service** | `services.py` | **Toutes les règles métier** (calculs, contrôles, transitions d'état) |
| **Modèle** | `models.py` | Décrire les tables et leurs contraintes |
| **Gabarit** | `templates/…/*.html` | Afficher : du HTML avec quelques instructions Django |

La règle qui explique tout le reste : **la vue ne décide jamais d'une règle métier**. Si demain une
règle change (par exemple le seuil d'une alerte), on modifie un service ; l'écran et, plus tard,
l'API mobile en profitent en même temps. C'est écrit en tête de chaque `views.py`, par exemple
`apps/fuel/views.py:3-4` : « Aucune règle métier ici : les vues contrôlent le rôle, lisent le
formulaire et délèguent à `services.py` ».

---

## 2. Ce qui se passe avant même qu'une vue s'exécute

### 2.1 Les réglages : `config/settings/base.py`

- **`MIDDLEWARE` (ligne 76)** : une chaîne de petits programmes que traverse chaque requête (session,
  protection CSRF, utilisateur connecté, messages…). Le dernier, `CurrentRequestMiddleware`
  (`apps/core/middleware.py:6`), mémorise la requête pour que le journal d'audit sache **qui** a
  fait une modification.
- **`TEMPLATES` (ligne 89)** : indique où sont les gabarits (`templates/` à la racine, plus le
  dossier `templates/` de chaque app grâce à `APP_DIRS`), et liste les **context processors**
  (lignes 95-100). Un context processor ajoute des variables **à tous les gabarits**, sans que les
  vues aient à s'en occuper. Nous en avons deux :
  - `apps.accounts.context_processors.menu` → la variable `menu` (le menu de gauche) ;
  - `apps.notifications.context_processors.notifications` → `nombre_non_lues` (la cloche).
- **`LOGIN_URL` (ligne 67)** : où envoyer quelqu'un qui n'est pas connecté.
- **`SESSION_COOKIE_AGE` (ligne 73)** : 30 minutes d'inactivité, comme le demande le cahier des charges.

### 2.2 Les adresses : `config/urls.py`

```python
# config/urls.py:12-27
urlpatterns = [
    path("", DashboardView.as_view(), name="home"),
    path("", include("apps.accounts.urls")),
    path("missions/", include("apps.missions.urls")),
    ...
    path("carburant/", include("apps.fuel.urls")),
    ...
]
```

Ce fichier ne fait que **monter** les adresses de chaque app sous un préfixe. Chaque app décrit ses
propres pages dans son `urls.py` :

```python
# apps/fuel/urls.py:5-11
app_name = "fuel"

urlpatterns = [
    path("", views.PleinListView.as_view(), name="liste"),
    path("nouveau/", views.PleinCreateView.as_view(), name="creer"),
    path("analyse/", views.AnalyseView.as_view(), name="analyse"),
]
```

`app_name = "fuel"` crée un **espace de noms**. Dans le code et les gabarits on n'écrit jamais
l'adresse à la main : on écrit son nom, `fuel:liste`, et Django retrouve `/carburant/`.
Conséquence pratique : on peut changer une adresse en un seul endroit sans casser un seul lien.
Côté gabarit : `{% url 'fuel:creer' %}` ; côté Python : `reverse("fuel:creer")` ou `redirect("fuel:liste")`.

### 2.3 La garde : `RoleRequiredMixin`

Toutes les vues protégées héritent de ce mixin :

```python
# apps/accounts/mixins.py:5-19
class RoleRequiredMixin(LoginRequiredMixin):
    roles: frozenset[str] = frozenset()

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if utilisateur.is_authenticated and utilisateur.role_effectif not in self.roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
```

Lecture pas à pas :

1. `dispatch` est la **première méthode** appelée quand une vue reçoit une requête.
2. Si l'utilisateur n'est pas connecté, `LoginRequiredMixin` (dont il hérite) l'envoie vers la page de
   connexion.
3. S'il est connecté mais que son rôle n'est pas dans `self.roles`, on lève `PermissionDenied` : Django
   affiche la page 403 (`templates/403.html`).
4. `role_effectif` (défini dans `apps/accounts/models.py`) fait qu'un superutilisateur agit comme ADMIN.

**À retenir absolument** : masquer un bouton dans un gabarit ne protège rien. Un utilisateur peut taper
l'adresse à la main. La vraie protection est cette garde, côté serveur. Les gabarits masquent les
boutons uniquement pour le confort.

Chaque app définit ses ensembles de rôles dans son `permissions.py` :

```python
# apps/fuel/permissions.py:11-12
CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.PARCAUTO})
```

Puis la vue déclare simplement `roles = permissions.CONSULTATION` (ou `MODIFICATION`).

---

## 3. Suivre un écran complet : le module Carburant

Prenons un module entier et lisons-le dans l'ordre. Tous les autres modules (missions, flotte,
chauffeurs, garage, stock, clients, congés, facturation…) sont construits sur ce même modèle.

### 3.1 Il s'enregistre dans le menu : `apps/fuel/apps.py`

```python
# apps/fuel/apps.py:9-18
def ready(self):
    from apps.accounts.navigation import EntreeMenu, enregistrer
    from . import permissions

    enregistrer(
        EntreeMenu("Carburant", "fuel:liste", "fa-gas-pump", permissions.CONSULTATION, ordre=45)
    )
```

`ready()` est appelée une fois au démarrage de Django. L'app y **déclare** son entrée de menu : libellé,
nom d'adresse, icône FontAwesome, rôles autorisés, position. Le menu, lui, est construit par
`apps/accounts/navigation.py` :

```python
# apps/accounts/navigation.py:33-51 (résumé)
def entrees_pour(role, chemin):
    visibles = sorted((e for e in _ENTREES.values() if e.roles is None or role in e.roles),
                      key=lambda e: (e.ordre, e.libelle))
    ...   # pour chaque entrée : url, icône, et « actif » si l'adresse courante commence par son url
```

**Pourquoi ce détour ?** `accounts` ne doit importer aucune app métier (sinon tout dépendrait de tout).
En inversant : ce sont les apps qui viennent s'inscrire dans un « registre ». Une entrée de menu
n'existe donc que si l'écran existe, et un rôle ne voit que ce qu'il peut ouvrir.

Le context processor (`apps/accounts/context_processors.py:4-9`) appelle `entrees_pour` à chaque page et
met le résultat dans la variable `menu`, que `base.html` parcourt (partie 5).

### 3.2 La vue « liste » : `PleinListView` (`apps/fuel/views.py:22-48`)

```python
class PleinListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "fuel/plein_list.html"
    context_object_name = "pleins"
    paginate_by = 20

    def get_filtre(self):
        ...FiltrePleinsForm(self.request.GET)

    def get_queryset(self):
        return services.rechercher_pleins(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        ...contexte.update(filtre=..., consommation_moyenne=..., peut_modifier=...)
        return contexte
```

C'est une **vue générique** de Django (`ListView`) : elle sait déjà afficher une liste paginée. On lui
fournit seulement ce qui est propre à l'écran :

| Attribut / méthode | Rôle |
|---|---|
| `roles` | Qui a le droit (la garde de la partie 2.3) |
| `template_name` | Quel gabarit afficher |
| `get_queryset()` | **Quelles lignes** afficher : ici on délègue au service `rechercher_pleins` |
| `paginate_by = 20` | 20 lignes par page (la pagination est obligatoire dans le cahier des charges) |
| `get_context_data()` | Les variables supplémentaires pour le gabarit (filtre, KPI, droit de saisie) |
| `PaginationTolerante` | Une page invalide (`?page=999`) affiche la dernière page au lieu d'une erreur 404 (`apps/core/views.py:4-21`) |

L'ordre des classes parentes compte : `PaginationTolerante` est placée avant `ListView` pour que sa
méthode `paginate_queryset` remplace celle de Django.

### 3.3 Le formulaire de filtre : lire `?vehicule=3&alerte=ROUGE`

Les filtres de la liste sont un **formulaire GET** (`apps/fuel/forms.py:51-…`). Sa méthode clé :

```python
# apps/fuel/forms.py:91 (extrait)
def criteres(self) -> dict:
    self.is_valid()                 # remplit cleaned_data avec les seuls champs VALIDES
    donnees = self.cleaned_data
    return {"recherche": donnees.get("q") or "", "vehicule": donnees.get("vehicule"), ...}
```

Une valeur invalide dans l'adresse (`?vehicule=abc`) est **ignorée** au lieu de faire planter la page.
Le dictionnaire obtenu est passé tel quel au service : `services.rechercher_pleins(**criteres)`
(`apps/fuel/services.py:245`). Le service construit la requête SQL (via l'ORM) ; la vue ne connaît pas
la base de données.

### 3.4 La vue « saisie » : `PleinCreateView` (`apps/fuel/views.py:51-105`)

C'est le cœur du modèle. Une **vue formulaire** suit ce cycle :

```
GET  /carburant/nouveau/   → affiche le formulaire vide
POST /carburant/nouveau/   → form_valid() si tout est valide, sinon réaffiche avec les erreurs
```

```python
# apps/fuel/views.py:66-91 (résumé)
def form_valid(self, form):
    confirmer = self.request.POST.get("confirmer") == "1"
    try:
        plein = services.enregistrer_plein(**form.cleaned_data, confirmer_alerte_saisie=confirmer)
    except SaisieSuspecte as avertissement:
        return self.render_to_response(self.get_context_data(form=form, saisie_suspecte=avertissement))
    except CarburantError as erreur:
        form.add_error(None, str(erreur))
        return self.form_invalid(form)
    messages.success(self.request, f"Plein enregistré : {nombre(plein.consommation, 1)} L/100 km.")
    return redirect("fuel:liste")
```

Le schéma se répète dans **tous** les écrans de saisie du projet :

1. Django construit le formulaire avec les données postées et le valide (types, longueurs, champs
   obligatoires). Si c'est invalide, `form_valid` n'est jamais appelé : la page est réaffichée avec les
   erreurs sous chaque champ.
2. `form.cleaned_data` contient alors des valeurs **déjà converties** (dates, décimaux, objets).
3. On appelle **un service**. Les règles métier y sont vérifiées (kilométrage croissant, ticket unique,
   écart de consommation…).
4. Le service signale un refus par une **exception métier** (`CarburantError` et ses filles, dans
   `exceptions.py`). La vue l'attrape et la transforme en message d'erreur dans le formulaire
   (`form.add_error(None, …)` = erreur générale, en haut du formulaire).
5. En cas de succès : un **message flash** (`messages.success`) puis `redirect(...)`.

**Pourquoi rediriger après un POST ?** C'est le motif « POST → redirection → GET ». Si on réaffichait
directement la page après l'enregistrement, un rafraîchissement du navigateur renverrait le formulaire
et créerait un doublon. Avec la redirection, le rafraîchissement ne fait qu'un simple GET.

**Le cas particulier de la saisie suspecte** montre bien la séparation des rôles : le service lève
`SaisieSuspecte` et n'enregistre rien ; la vue réaffiche le formulaire avec l'avertissement ; le gabarit
ajoute un bouton `name="confirmer" value="1"` ; en le pressant, le POST revient avec `confirmer=1` et
le même service accepte cette fois. Aucune règle métier n'est dans la vue : elle relaie seulement.

### 3.5 Le formulaire de saisie : `PleinForm` (`apps/fuel/forms.py:1-48`)

Un formulaire Django est une classe dont chaque attribut est un champ :

```python
quantite_litres = forms.DecimalField(label="Quantité (litres)", min_value=0, decimal_places=2, max_digits=8)
```

Trois techniques à reconnaître :

- **Listes déroulantes dynamiques** : `__init__` (ligne 35) donne à `vehicule` et `chauffeur` leurs
  choix via des services (`chauffeurs_actifs()`), et `label_from_instance` fixe le texte affiché.
- **Validation d'un champ** : une méthode `clean_<champ>` (ligne 44) refuse par exemple une date dans le
  futur.
- **Style commun** : la classe hérite de `StyleTailwindMixin` (`apps/core/forms.py:10-16`), qui ajoute
  la même apparence Tailwind à tous les champs :

```python
# apps/core/forms.py:13-16
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    for champ in self.fields.values():
        champ.widget.attrs.setdefault("class", CHAMP)
```

### 3.6 Le service (à survoler seulement ici)

`enregistrer_plein` (`apps/fuel/services.py:94`) est décorée `@transaction.atomic` : si une règle échoue à
mi-parcours, **rien** n'est écrit en base. Elle vérifie, calcule la consommation, décide du niveau
d'alerte, crée le `Plein`, met à jour le compteur du camion, et émet un signal si une alerte est levée.
C'est ce fichier qui contient le « métier » : l'interface n'en est que la porte d'entrée.

---

## 4. Les gabarits : de `base.html` à un champ de formulaire

### 4.1 La mise en page commune : `templates/base.html`

Tous les écrans **étendent** ce fichier. Ses « trous » (`block`) sont les seuls endroits où une page
fille écrit quelque chose :

| Bloc | Ligne | Contenu fourni par la page fille |
|---|---|---|
| `titre` | 6 | Le titre de l'onglet du navigateur |
| `entete` | 85 | Le petit libellé en haut à gauche |
| `contenu` | 115 | **Le corps de la page** |

Autour de ces blocs, `base.html` fournit : le logo, le **menu latéral** (boucle sur la variable `menu`),
la cloche de notifications, le nom et le rôle de l'utilisateur, le bouton de déconnexion (un formulaire
POST avec jeton CSRF), et l'inclusion des messages (`{% include "components/_messages.html" %}`, ligne 114).

Le début du fichier (lignes 13-31) charge Tailwind, Alpine.js et FontAwesome par CDN et déclare deux
palettes de couleurs tirées du logo : `marque` (bordeaux) et `accent` (orange). D'où les classes comme
`bg-marque-600` ou `text-accent-500` dans tous les gabarits.

### 4.2 Une page fille : `templates/fuel/plein_list.html`

```django
{% extends "base.html" %}
{% load humanize ui %}
{% block titre %}Carburant{% endblock %}
{% block entete %}Carburant{% endblock %}

{% block contenu %}
  ...
{% endblock %}
```

- `{% extends %}` : « je suis la page `base.html`, avec ces blocs remplis ».
- `{% load humanize ui %}` : charge des **filtres** et **balises** supplémentaires. `humanize` (fourni par
  Django) donne `intcomma` (séparateur de milliers) ; `ui` est le nôtre (`apps/core/templatetags/ui.py`).
- `{{ variable }}` affiche une valeur **en l'échappant automatiquement** (voir 7.2).
- `{% if %}`, `{% for %}`, `{% url %}`, `{% include %}` : les instructions de base.
- `{{ paginator.count|pluralize }}` : un **filtre** transforme la valeur (ici : mettre un « s » si > 1).

### 4.3 Les briques réutilisables

**a) Le champ de formulaire : `templates/components/_champ.html` (lignes 1-11)**

```django
{% include "components/_champ.html" with champ=form.quantite_litres %}
```

Ce petit gabarit produit : l'étiquette (avec `*` rouge si obligatoire), le champ, l'aide, et les messages
d'erreur en rouge avec `role="alert"` (lu par les lecteurs d'écran). Il est utilisé dans **tous** les
formulaires : une amélioration d'accessibilité s'y fait une seule fois.

**b) Les messages flash : `templates/components/_messages.html`**

Affiche les messages posés par `messages.success/warning/error` dans les vues. La couleur et l'icône
dépendent du niveau (`message.level_tag`). Un bouton « fermer » utilise Alpine.js
(`x-data="{ visible: true }"`, `x-show="visible"`, `@click="visible = false"`).

**c) La pagination : `templates/components/_pagination.html`**

Affiche « Page 2 sur 5 » et les liens Précédent/Suivant. Ses liens utilisent `{% querystring page=… %}`,
qui **conserve les autres paramètres** de l'adresse : un filtre actif survit au changement de page.

**d) Les pastilles de statut : `apps/core/templatetags/ui.py:84-93`**

```django
{% badge f.statut f.get_statut_display %}
```

```python
@register.simple_tag
def badge(code: str, libelle: str):
    couleur = STYLES[COULEURS_STATUT.get(code, "gris")]
    return format_html('<span class="... {}">{}</span>', couleur, libelle)
```

Un dictionnaire (`COULEURS_STATUT`) associe chaque code de statut (`EMISE`, `EN_MISSION`, `ROUGE`…) à
une couleur. Le **texte** de la pastille porte toujours le sens : la couleur n'est qu'un renfort
(accessibilité). `format_html` échappe le libellé : on ne fabrique jamais de HTML avec du texte utilisateur
sans lui.

**e) Les nombres à la française : `apps/core/formats.py`**

`nombre(1500.5, 1)` donne « 1 500,5 » et `pourcentage_signe(23.33)` donne « +23,3 ». Ces fonctions
arrondissent correctement (le formatage de Django **tronque**). À utiliser dès qu'un nombre entre dans un
**message** ; dans un gabarit, on utilise `|floatformat:0|intcomma`.

---

## 5. Un peu de JavaScript : Alpine.js

L'interface n'a presque pas de JavaScript : Alpine.js (chargé par CDN) ajoute de petits comportements
directement dans le HTML. On en rencontre trois formes :

```html
<div x-data="{ ouvert: false }">                       <!-- un petit état local -->
  <button @click="ouvert = !ouvert">Annuler</button>   <!-- @click : réagir au clic -->
  <form x-show="ouvert" x-cloak>...</form>             <!-- x-show : afficher/cacher -->
</div>
```

- Le menu mobile (`base.html`), la fermeture des messages, le formulaire « autre mouvement » de la
  trésorerie, l'annulation d'un règlement, le champ « motif d'exonération » (visible seulement si la TVA
  vaut 0) fonctionnent ainsi.
- `x-cloak` cache l'élément tant qu'Alpine n'a pas démarré, pour éviter un clignotement.
- **Règle de sécurité que nous suivons** : on ne colle jamais une valeur saisie par l'utilisateur
  *dans* une expression Alpine (`x-data="{ v: '{{ valeur }}' }"`), car une apostrophe pourrait y injecter du
  code. On lit plutôt la valeur depuis le champ (`x-init="tva = $refs.taux.value"`).

---

## 6. Les motifs d'écrans que vous retrouverez partout

| Motif | Vue Django | Exemple |
|---|---|---|
| **Liste filtrable** | `ListView` + formulaire GET + `PaginationTolerante` | missions, flotte, factures |
| **Fiche** | `DetailView` (parfois `get_context_data` riche) | camion, chauffeur, facture |
| **Création / modification** | `FormView` (`form_valid` → service → `redirect`) | plein, client, dépense |
| **Action ponctuelle** | `View` limitée à `POST` | valider une facture, suspendre un chauffeur |
| **Tableau de synthèse** | `TemplateView` | analyse carburant, trésorerie, tableau de bord |

**Les actions en POST** suivent toutes le même squelette (par exemple `apps/drivers/views.py`,
`StatutView`, ou `apps/billing/views.py`, `_ActionFacture`) :

```python
class StatutView(RoleRequiredMixin, View):
    roles = permissions.MODIFICATION
    http_method_names = ["post"]          # un GET renvoie 405 « méthode non autorisée »

    def post(self, request, pk):
        objet = get_object_or_404(...)
        form = MonForm(request.POST)
        if not form.is_valid(): messages.error(...); return redirect(...)
        try:    services.faire_quelque_chose(objet, ...)
        except MonErreurMetier as erreur: messages.error(request, str(erreur))
        else:   messages.success(request, "C'est fait.")
        return redirect("app:detail", pk=objet.pk)
```

Pourquoi POST et pas un simple lien ? Un **lien** (GET) ne doit jamais modifier de données : un robot ou
un préchargement pourrait le suivre. Les modifications passent par un formulaire POST, protégé par
CSRF (partie 7).

---

## 7. La sécurité dans l'interface

### 7.1 Le jeton CSRF

Tout formulaire POST contient `{% csrf_token %}`. Django refuse (erreur 403) un POST sans ce jeton
secret, ce qui empêche un site tiers de faire agir votre navigateur à votre insu. Chaque module a un test
`Client(enforce_csrf_checks=True)` qui vérifie ce refus.

### 7.2 L'échappement automatique (XSS)

Dans un gabarit, `{{ valeur }}` transforme `<script>` en `&lt;script&gt;` : le texte saisi par un
utilisateur ne peut donc pas exécuter de code. Nous ne désactivons jamais cet échappement (`|safe` n'est
pas utilisé sur du texte saisi). Chaque module a un test qui injecte `<script>alert(1)</script>` et vérifie
qu'il apparaît échappé.

### 7.3 Le rôle vérifié côté serveur

Répétons-le, car c'est l'erreur classique : `{% if peut_modifier %}` dans un gabarit ne fait que **masquer**
un bouton. La protection est `roles = …` sur la vue **et**, pour les actions sensibles, un second
contrôle dans le service (par exemple `services.valider` d'une facture n'accepte que le rôle DIRECTION,
même si la vue laissait passer).

### 7.4 Redirections sûres, confirmations

Une notification ne redirige que vers une adresse **interne** (`url_has_allowed_host_and_scheme`,
`apps/notifications/views.py`). Les actions destructives demandent une confirmation
(`onsubmit="return confirm('…')"`).

---

## 8. Ce qui relie les modules sans les faire dépendre les uns des autres

Un module de « niveau bas » (clients, chauffeurs) ne doit pas importer un module de « niveau haut »
(missions, facturation). Trois mécanismes permettent quand même à une fiche d'afficher des informations
d'ailleurs :

1. **Le menu** (partie 3.1) : chaque app s'inscrit dans un registre au démarrage.
2. **Les sections de fiche** (`apps/core/sections.py`) : la fiche d'un client déclare un registre
   `DETAIL_CLIENT` ; l'app `missions` y enregistre un fournisseur qui ajoute le bloc « Missions du
   client ». La fiche fait `{% for section in sections %}{% include section.template with section=section %}{% endfor %}`
   sans jamais importer `missions`. Même chose pour l'alerte « mission prévue » sur un congé.
3. **Les signaux** (`apps/*/signals.py`) : le service émet un événement (« facture soumise »), et
   l'app `notifications` s'y abonne pour créer les messages. Le métier ignore les notifications.

Ces trois mécanismes sont la raison pour laquelle on peut ajouter un module sans modifier les autres.

---

## 9. Carte des fichiers (où trouver quoi)

| Je cherche… | Fichier |
|---|---|
| Les adresses de tout le site | `config/urls.py` puis `apps/<app>/urls.py` |
| La garde des rôles | `apps/accounts/mixins.py` |
| Qui a le droit de faire quoi | `apps/<app>/permissions.py` |
| Le menu latéral | `apps/accounts/navigation.py` (+ `AppConfig.ready()` de chaque app) |
| La mise en page (logo, menu, couleurs) | `templates/base.html` |
| Un champ de formulaire, les messages, la pagination | `templates/components/` |
| Les pastilles, les nombres français | `apps/core/templatetags/ui.py`, `apps/core/formats.py` |
| Le style commun des formulaires | `apps/core/forms.py` |
| La pagination tolérante, la recherche sans accents | `apps/core/views.py`, `apps/core/search.py` |
| Les règles métier d'un module | `apps/<app>/services.py` |
| Les écrans d'un module | `apps/<app>/views.py` et `apps/<app>/templates/<app>/` |
| Les tests d'un écran | `apps/<app>/tests/test_views.py` |
| Le tableau de bord | `apps/dashboard/services.py`, `apps/dashboard/templates/dashboard/index.html` |
| La cloche et les notifications | `apps/notifications/` |

---

## 10. Ajouter un nouvel écran : la recette

Supposons un écran « Fournisseurs ». Dans l'ordre :

1. **Modèle** (`models.py`) et **migration** (`python manage.py makemigrations`).
2. **Règles métier** dans `services.py` : `creer_fournisseur`, `rechercher_fournisseurs`… avec leurs
   exceptions dans `exceptions.py`. **Écrire leurs tests d'abord ou en même temps.**
3. **Droits** dans `permissions.py` : `CONSULTATION` et `MODIFICATION`.
4. **Formulaires** dans `forms.py` (hériter de `StyleTailwindMixin`).
5. **Vues** dans `views.py` : `RoleRequiredMixin` + vue générique adaptée (partie 6).
6. **Adresses** dans `urls.py` (avec `app_name`), puis une ligne `path("fournisseurs/", include(...))` dans
   `config/urls.py`.
7. **Gabarits** : `{% extends "base.html" %}`, les blocs `titre`/`entete`/`contenu`, les briques de la
   partie 4.3.
8. **Menu** : `enregistrer(EntreeMenu(...))` dans `AppConfig.ready()`.
9. **Tests d'écran** : accès par rôle (200 / 403 / redirection), affichage, filtres, saisie valide et
   invalide, CSRF, échappement XSS.
10. Lancer `python -m pytest --cov=apps` puis `python manage.py makemigrations --check`.

---

## 11. Comment on teste une interface

Les tests d'écran (`apps/*/tests/test_views.py`) n'ouvrent pas de navigateur : ils utilisent le **client de
test** de Django, qui envoie de vraies requêtes à l'application et lit la réponse.

```python
def test_le_charge_clientele_cree_un_client(client):
    _connecte(client, Role.CHARGE_CLIENTELE)                    # force_login : pas de mot de passe
    reponse = client.post(reverse("customers:creer"), _donnees(), follow=True)
    assert Client.objects.get(ncc_nif="CI-1234567A")            # l'effet en base
    assert reponse.redirect_chain[-1][0] == reverse(...)        # la redirection
    assert any("créé" in m for m in _messages(reponse))         # le message flash
```

Ce qu'on vérifie systématiquement : le code HTTP par rôle, le contenu affiché, l'effet en base, les
messages, les cas invalides, le CSRF, l'échappement, et le **nombre de requêtes SQL**
(`django_assert_max_num_queries`) pour éviter qu'une liste ne ralentisse quand les données grossissent.

---

## 12. Petit lexique

| Mot | Sens dans ce projet |
|---|---|
| **Vue** | Fonction ou classe qui reçoit une requête et renvoie une page |
| **Gabarit (template)** | Fichier HTML avec des instructions Django `{% … %}` et `{{ … }}` |
| **Context / contexte** | Le dictionnaire de variables fourni au gabarit |
| **Queryset** | Une requête sur la base, évaluée seulement quand on lit le résultat |
| **Mixin** | Classe qu'on « ajoute » à une autre pour lui donner un comportement (ici : la garde des rôles) |
| **Service** | Module contenant les règles métier, indépendant du web |
| **Signal** | Événement émis par un service, écouté par d'autres apps |
| **Message flash** | Petit texte affiché une seule fois à la page suivante (`django.contrib.messages`) |
| **CSRF** | Attaque où un site tiers fait envoyer un formulaire par votre navigateur ; contrée par un jeton |
| **XSS** | Injection de code dans une page via du texte saisi ; contrée par l'échappement |
| **Soft delete** | Suppression logique : la ligne reste en base, marquée « supprimée » |

---

### Pour aller plus loin

Le plus efficace pour comprendre : **ouvrir un module et le suivre avec ce guide**. Par exemple
`apps/drivers/` (le plus court : liste, fiche, modification, action de statut), puis `apps/fuel/`
(saisie avec avertissement), puis `apps/billing/` (cycle de vie complet avec plusieurs rôles).
