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

{{FICHIER apps/hr/forms.py}}

`StyleTailwindMixin` (chapitre 2) donne à chaque champ le même aspect. Les formulaires n'ont **aucune règle
métier** : « ce congé dépasse-t-il le solde ? » se décide dans `services.demander_conge`.

## Étape 2 — Les vues

{{FICHIER apps/hr/views.py}}

À repérer dans ce fichier :

- `roles = permissions.CONGES_ACCES` : la **garde** (`RoleRequiredMixin`), sur chaque vue.
- `CongeListView` : trois vues possibles selon le rôle (`vues_disponibles`) ; `get_queryset` choisit le service.
- `CongeCreateView` : `form_valid` appelle `services.demander_conge`, gère les erreurs métier, redirige.
- `CongeDecisionView` : un seul point d'entrée `POST` pour valider, refuser et annuler.
- `PersonnelListView/DetailView/CreateView/UpdateView` : le même schéma pour le personnel.
- `AttributionView` : accorder des jours exceptionnels (RH seulement, motif obligatoire).

## Étape 3 — Les adresses

{{FICHIER apps/hr/urls.py}}

`app_name = "hr"` crée l'espace de noms : on écrit `reverse("hr:conges_liste")`. `<int:pk>` capture un numéro
dans l'adresse et le passe à la vue.

Montez ces adresses : voici la modification à faire dans `config/urls.py` :

{{CONFIG}}

## Étape 4 — Les gabarits

```bash
mkdir -p apps/hr/templates/hr
```

Chaque gabarit **hérite de `base.html`**. Lisez d'abord la liste des congés : c'est la plus riche.

{{FICHIER apps/hr/templates/hr/conge_list.html}}

{{FICHIER apps/hr/templates/hr/conge_form.html}}

{{FICHIER apps/hr/templates/hr/conge_detail.html}}

Sur la fiche d'un congé, les boutons ne s'affichent que si `actions` (calculé par le service) les contient ;
le formulaire de refus/annulation porte `data-confirm` : `app.js` demande confirmation. Le bloc
`{% for section in sections %}{% include section.template %}{% endfor %}` affichera **l'alerte de mission** que
`missions` ajoutera au chapitre 21.

{{FICHIER apps/hr/templates/hr/personnel_list.html}}

{{FICHIER apps/hr/templates/hr/personnel_form.html}}

{{FICHIER apps/hr/templates/hr/personnel_detail.html}}

## Étape 5 — Les tests d'écrans

{{RESTANTS}}

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

{{PYTEST}}

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
