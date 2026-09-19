# Glossaire Métier — Transport & Logistique (DEN Source Group)

> À lire par toute IA / développeur avant de coder une règle métier.

## A

**Affectée (mission)** — Statut d'une mission une fois le camion et le
chauffeur assignés, avant démarrage.

**Alerte préventive** — Notification émise 30 jours avant l'expiration d'un
document réglementaire (assurance, visite technique, patente, permis).

**Append-only** — Se dit d'une table (ex. `audit_log`) où l'on ne peut
qu'ajouter des lignes, jamais en modifier ni supprimer.

## B

**Brouillon (mission)** — Statut initial d'une mission en cours de saisie.

## C

**Carte Grise** — Document d'immatriculation du véhicule (CI).

**Chargé clientèle** — Employé responsable d'un portefeuille clients.

**Chauffeur** — Employé de l'entreprise, extension de la fiche Personnel.
Matricule unique partagé.

**Clôturée (mission)** — Statut final après livraison confirmée et
validation.

**Cycle de vie mission** — Brouillon → Planifiée → Affectée → En cours
[Départ → Colis récupéré] → Livrée → Clôturée & Validée.

## D

**Dispatcheur** — Employé qui affecte missions, camions et chauffeurs.

## E

**En maintenance (camion)** — Statut attribué automatiquement à l'ouverture
d'un OR.

**En mission (camion/chauffeur)** — Statut pendant l'exécution d'une
mission.

## F

**FCFA** — Franc CFA, devise officielle (Côte d'Ivoire).

## G

**Garage interne DEN Source** — Atelier de réparation interne.
Alternative : Prestataire externe.

## L

**L/100 km** — Unité standard de consommation carburant.
Formule : `(Litres ÷ (Km actuel − Km précédent)) × 100`.

## M

**Mobile Money** — Paiement via Wave, Orange Money, MTN.

**MFA** — Multi-Factor Authentication (obligatoire ADMIN/DIRECTION).

**MIS-2026-XXXX** — Format du numéro de mission auto-généré.

## N

**NCC** — Numéro de Compte Contribuable (identification fiscale CI).

**NIF** — Numéro d'Identification Fiscale.

## O

**OR (Ordre de Réparation)** — Document de maintenance. Types : Curatif,
Préventif, Diagnostic, Pneumatiques. Format : `OR-2026-XXXX`.

## P

**Patente** — Taxe professionnelle (document réglementaire camion).

**PBKDF2 / Argon2** — Algorithmes de hachage de mots de passe.

**PWA** — Progressive Web App (espace mobile chauffeur, offline possible).

**PUMP** — Prix Unitaire Moyen Pondéré (valorisation stock).

## Q

**QR code mission** — Code scanné par l'expéditeur (récupération colis) et
par le destinataire (confirmation livraison).

## R

**RBAC** — Role-Based Access Control (contrôle d'accès par rôle).

**Recalcul statut camion** — Algorithme déclenché à la clôture d'un OR :
1. OR ouverts → En maintenance
2. Mission planifiée/en cours → En mission
3. Immobilisé/Hors service → conserver
4. Sinon → Disponible

## S

**Soft delete** — Suppression logique (flag `is_deleted`), jamais physique.

**Statuts camion** — Disponible · En mission · En maintenance ·
Immobilisé · Hors service.

**Statuts chauffeur** — Disponible · En mission · En congé · Suspendu ·
Inactif.

**Statuts congé** — DEMANDE → VALIDATION_N1 → APPROUVE → EN_COURS →
TERMINE (ou REFUSE).

## T

**TVA** — Taxe sur la Valeur Ajoutée. Taux par défaut : 18 %.
Exonérations : Export, ONG, Convention (motif obligatoire si 0 %).

**Taux 3 niveaux** — Système (18 %) · Client (spécifique) · Facture.

## V

**Visite technique** — Contrôle périodique obligatoire du véhicule (CI).

## W

**Wave** — Service de Mobile Money (CI).

## Workflow congés (3 niveaux)

1. **Demande** employé (dates + motif)
2. **Validation N1** supérieur hiérarchique direct (le directeur valide lui-même) (délai 48 h)
3. **Validation N2** RH (délai 24 h)
4. **Notification** automatique employé
5. Si chauffeur → statut `En congé`

Règles :
- Blocage si solde insuffisant : droit de 2 semaines/an = 12 jours ouvrables (hors dimanches et jours fériés), + jours exceptionnels RH.
- Alerte N1 si chauffeur a une mission sur la période.
- Annulation d'un congé approuvé : RH uniquement + notification.