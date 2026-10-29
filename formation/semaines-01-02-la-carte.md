# Semaines 1 et 2 — La carte du projet

But : savoir **où chercher** avant de savoir écrire. Lisez `GUIDE-PARCOURS.md` (environ 30 heures, une étape par
séance de 1 à 2 heures), puis répondez aux 12 questions ci-dessous **en ouvrant le code**. Ne regardez les réponses
qu'après avoir cherché : chercher est l'exercice.

## Mise en route (jour 1)

```bash
python manage.py check
python -m pytest -q --no-cov
python manage.py runserver
```

Résultat attendu : aucun problème signalé, environ 3 415 tests réussis, puis le site sur http://localhost:8000
(connectez-vous avec un compte de `COMPTES-ESSAI.md`).

## Les 12 questions

1. Où est écrite la règle « un camion dont un document est expiré ne peut pas partir en mission » ?
2. Quel fichier décide quels rôles peuvent **consulter** les missions ? Et lesquels voient les **codes secrets** ?
3. Suivez un clic : que se passe-t-il, fichier par fichier, quand on enregistre la fiche d'un nouveau camion ?
4. Pourquoi les montants sont-ils des `Decimal`, jamais des `float` ?
5. D'où vient le délai de **30 jours** de l'alerte avant expiration, et comment le changer sans toucher au code ?
6. Quelle commande lance seulement les tests de la flotte ?
7. Que veut dire « suppression logique », et où est-elle définie ?
8. Une facture est validée : par quel chemin son écriture comptable est-elle créée ?
9. Pourquoi la Finance ne valide-t-elle pas les factures qu'elle prépare ? Où le code l'impose-t-il ?
10. L'app `missions` ne connaît pas `billing`. Comment le devis est-il annulé quand on annule une mission ?
11. Qui fait les calculs du tableau de bord ?
12. Où sont posés les en-têtes de sécurité, dont la politique de sécurité du contenu (CSP) ?

---

## Réponses

1. `apps/missions/services.py` : `documents_non_valides_du_vehicule` liste les documents expirés ou absents, et
   `_exiger_vehicule_en_regle` refuse l'affectation et le départ. Décision : `avenant-affectation-documents.md`.
2. `apps/missions/permissions.py` : `CONSULTATION` pour la consultation, `VOIR_CODES` pour les codes. Ce sont deux
   ensembles **indépendants**, exprès (voir l'exercice 5).
3. `apps/fleet/urls.py` (route `fleet:creer`) → `VehiculeCreateView` dans `apps/fleet/views.py` → le formulaire
   `VehiculeForm` vérifie la forme → `form_valid` appelle `services.creer_vehicule(**form.cleaned_data)` → le service
   vérifie les règles (doublons d'immatriculation et de VIN…) et crée la ligne → la vue redirige vers la fiche avec un
   message. **La règle est dans le service, jamais dans la vue.**
4. Un `float` arrondit en binaire : `0.1 + 0.2` ne vaut pas exactement `0.3`. Pour de l'argent, une erreur d'un
   centime répétée sur des milliers de lignes fausse la comptabilité. `Decimal` calcule en décimal exact.
5. `DELAI_ALERTE_JOURS = 30` dans `apps/core/constants.py`, valeur par défaut du paramètre `delai_alerte_jours`
   (`apps/parametres/models.py`). Il se change sur l'écran **Paramètres** (ADMIN, DIRECTION) ; le code le lit avec
   `parametres.services.delai_alerte()`.
6. `python -m pytest apps/fleet -q --no-cov`.
7. Une ligne « supprimée » reste en base, marquée `is_deleted` ; le manager par défaut la cache. C'est `BaseModel`,
   dans `apps/core/models.py`. On ne perd jamais l'historique, et l'administrateur peut restaurer.
8. `billing.services.valider` (vers la ligne 438) émet le signal `facture_a_comptabiliser` → `accounting/receivers.py`
   (`comptabiliser_une_facture_validee`) → `accounting.services.passer_ecriture`. Le signal est envoyé avec `send`
   (et non `send_robust`) : si l'écriture échoue, **la validation entière est annulée**.
9. Séparation des tâches : celui qui prépare ne valide pas (`avenant-validation-factures.md`). Le code :
   `VALIDATION = frozenset({Role.DIRECTION})` dans `apps/billing/permissions.py`, contrôlé strictement dans
   `billing.services.valider`.
10. Par un **signal** : `missions` émet `mission_annulee` (`apps/missions/signals.py`) et `billing` l'écoute
    (`apps/billing/receivers.py`). Une app « du bas » prévient sans connaître celles « du haut » ; le test
    `apps/core/tests/test_architecture.py` refuse toute dépendance en boucle.
11. Personne dans `dashboard` : `apps/dashboard/services.py` **assemble** des lectures fournies par chaque app
    (`fleet.repartition_statuts`, `missions.repartition_par_statut`…). Aucune règle n'y est recopiée.
12. `SecurityHeadersMiddleware`, dans `apps/core/middleware.py` ; la politique elle-même est dans
    `config/settings/base.py` (`CSP`).

## Vous êtes prêt pour la phase 2 si…

Vous trouvez la réponse de chaque question en moins de 10 minutes, sans le guide. Sinon, refaites la question une
semaine plus tard.
