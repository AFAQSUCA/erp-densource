# Avenant — Documents exigés pour affecter une mission

Précise le cahier des charges, §3 Module 5, ligne 129 (« camion disponible, chauffeur disponible ») et §3 Module 3,
ligne 110 (permis : numéro, catégories C, E, expiration ; visite médicale). Jusqu'ici, seuls un permis ou une visite
**expirés** bloquaient l'affectation ; un chauffeur à la fiche permis vide et un camion sans assurance ou visite
technique valide passaient sans contrôle (audit M5-04, AUD-10, AUD-12).

## Décision de l'entreprise (12/10/2026)

| Cas | Décision |
|---|---|
| Chauffeur : n° de permis, date d'expiration du permis ou visite médicale non renseignés, ou ni catégorie C ni E | **Bloquant** |
| Camion : carte grise, assurance, visite technique ou patente **expirée ou jamais enregistrée** | **Bloquant** |

## Règles

- Contrôlé à l'**affectation**, à la **réaffectation** (changement de camion ou de chauffeur) et au **départ** de la
  mission : un document a pu expirer entre-temps.
- La catégorie **C** (porteur) **ou E** (ensemble articulé) suffit.
- Une date d'expiration égale à aujourd'hui ne bloque pas encore (expiré = date dépassée).
- Le message d'erreur nomme **tous** les manques à la fois, pour une seule correction.
- Les alertes du tableau de bord signalent ces manques avant qu'ils ne bloquent une mission (documents manquants des
  camions : audit M2-22).

## Implémentation

`apps/missions/services.py` : `documents_manquants_du_chauffeur`, `documents_non_valides_du_vehicule`,
`_exiger_documents_valides`, `_exiger_vehicule_en_regle`. Tests : `apps/missions/tests/test_documents_et_reaffectation.py`.
