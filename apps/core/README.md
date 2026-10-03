# core

Rôle : socle transverse (`BaseModel` avec timestamps + soft delete, mixins,
permissions communes). Aucune dépendance vers les autres apps métier —
c'est la racine du graphe de dépendances (architecture.md:99-163).

Entités principales : `BaseModel` (abstrait) — à créer à l'étape 1.

Recherche texte (`search.py`) : `filtrer_par_texte(queryset, texte, *champs)` compare des valeurs
sans accents ni majuscules (« traore » trouve « Traoré », « moussa traore » trouve Moussa
Traoré) ; à utiliser pour tout champ de recherche des listes plutôt que `icontains`. Sur
PostgreSQL : `LOWER(TRANSLATE(...))` sans extension ; sur SQLite : fonction `NORMALISER`
enregistrée à la connexion. `views.PaginationTolerante` : une page inexistante ou illisible
affiche la première ou la dernière page au lieu d'une erreur 404.

Formulaires (`forms.py`) : `StyleTailwindMixin` applique le style commun **et** écrit les champs `type="date"` au
format `AAAA-MM-JJ` que le navigateur exige (en français, Django écrivait `JJ/MM/AAAA` : la date du jour ou la date
existante n'apparaissait pas dans le champ). À utiliser pour tout formulaire.

Graphiques (`graphiques.py`, balises `graphiques`) et séries mensuelles (`services.py` : `debuts_de_mois`,
`total_par_mois`) : voir `apps/dashboard/README.md`.

Rapports imprimables (`rapports.py`, `views.ImpressionListeMixin`, `templates/rapports/`) — cahier-des-charges.md:82,
305 « Export PDF et Excel » : une page HTML autonome (pas `base.html`) avec un bouton « Imprimer » qui ouvre
l'impression du navigateur (Ctrl+P / Enregistrer au format PDF) ; même mécanisme que `billing.facture_print`,
généralisé pour ne pas le récrire à chaque écran. `contexte_rapport()` fournit l'en-tête (entreprise, titre,
généré le/par) ; `ImpressionListeMixin` transforme un `ListView` existant en rapport (mêmes rôles, recherche et
filtres, sans pagination, plafonné à 500 lignes) — voir les `*ImprimerView` de `missions`, `fleet`, `hr`,
`drivers`, `inventory`, `garage`, `fuel`, `customers`, `billing` et `audit`. La trésorerie (`finance`) et le
tableau de bord (`dashboard`) ont chacun leur propre vue, plus riches qu'une simple liste. Un nouveau rapport
de liste : sous-classer le `ListView` existant, ajouter `titre_impression` et `colonnes`, l'inscrire dans
`urls.py`, ajouter le bouton dans le gabarit avec `?{{ request.GET.urlencode }}` pour reprendre les filtres.



En-tête commune (`_entete_impression.html`) : logo (`static/img/logo-emblem.jpg`), raison sociale en bordeaux (`#8b0319`) et filet orange (`#f28a14`) — les couleurs du logo (`frontend/tailwind.config.js`), reprises aussi par le PDF des codes de mission (`apps/missions/documents.py`, ReportLab). Tout nouveau document imprimable doit inclure `_style_impression.html` et `_entete_impression.html` pour rester cohérent avec les autres ; c'est aussi le cas de la facture (`billing.facture_print`), qui les réutilise pour son propre en-tête.

**Fichiers téléversés** (`medias.py`) : jamais servis en libre accès. Une app qui stocke des fichiers déclare le préfixe de son `upload_to` et les rôles autorisés (`enregistrer_media("demandes_depense", permissions.X)` dans `AppConfig.ready()`) ; `/medias/<chemin>` (`MediaProtegeView`) exige la connexion et le rôle, refuse les chemins avec `..`, et ne sert à personne un préfixe non déclaré. Seuls les PDF et images courantes s'affichent dans le navigateur, le reste (HTML, SVG...) est téléchargé. En production (`MEDIA_ACCEL_REDIRECT`), Django répond `X-Accel-Redirect` et Nginx envoie le fichier depuis `/medias-internes/`, emplacement `internal` : Django ne lit pas le fichier. `MEDIA_URL` vaut `medias/`, donc `champ.url` pointe déjà vers cette vue.

**Erreurs métier** (`exceptions.ErreurMetier`, `middleware.ErreurMetierMiddleware`) : une opération peut échouer à cause d'une autre app (plein refusé parce que l'enveloppe de dépense est dépassée) ; l'erreur traverse alors l'écran d'origine, qui ne connaît pas cette famille. Les erreurs métier héritent d'`ErreurMetier` (`BillingError` pour l'instant) et, si l'écran ne les attrape pas, le middleware les transforme en message avec retour à la page d'origine au lieu d'une erreur 500 (l'API a son propre gestionnaire, `apps/api/exceptions.py`). Un GET sans page d'origine n'est pas masqué (pas de boucle de redirections).
