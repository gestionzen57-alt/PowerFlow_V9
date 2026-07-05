# ROADMAP D'IMPLÉMENTATION — POWERFLOW V9

## Document maître — Version 1.0
## Date : 2026-07-05
## Statut : FONDATION POSÉE

---

## PRINCIPE DIRECTEUR

V9 est un système de lecture comportementale des forces.
L'ordre cognitif est non négociable :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution

Aucune couche aval ne peut être construite tant que la couche amont
n'est pas stable, testée et validée.

---

## PHASE 0 — FONDATION COGNITIVE ✅

### Objectif
Poser la base documentaire, doctrinale et structurelle de V9.

### Chantiers
0.1  Créer l'arborescence V9 propre (dossier vide)
0.2  Déposer les 6 documents piliers
0.3  Déposer les fichiers d'état
0.4  Déposer la roadmap
0.5  Initialiser la mémoire
0.6  Premier commit Git propre

### Critère de validation
- Tous les fichiers existent ✅
- L'arborescence est cohérente ✅
- Aucune contamination V8 ✅
- Git initialisé ✅ (commit 0ccc26c)

---

## PHASE 1 — SQUELETTE COGNITIF

### Objectif
Définir les formats, structures de données et interfaces
qui permettront aux couches de communiquer proprement.

### Chantiers
1.1  Définir le format de sortie de la couche Forces
     - Structure JSON attendue
     - Champs : devise, timeframe, intensité, direction,
       vitesse, croisement, recroisement, rejet, repulsion
     - Source prioritaire : MT4/SDI
     - Source complémentaire : MT5 ticks

1.2  Définir le format de sortie de la couche Scènes
     - Structure JSON attendue
     - Champs : timestamp, fenêtre temporelle, zone,
       coalitions détectées, antagonismes détectés,
       cinématique locale, confluences MTF

1.3  Définir le format de sortie de la couche Comportements
     - Structure JSON attendue
     - Champs : scène source, comportement qualifié,
       intensité, phase, transitions détectées,
       comparaison aux cas connus

1.4  Définir le format de sortie de la couche Fenêtres
     - Statut : absente / en préparation / ouverte /
       fragile / invalidée / ambiguë
     - Champs : scène source, comportement source,
       type de fenêtre, niveau de confiance

1.5  Définir le format de sortie de la couche Exploitabilité
     - Statut : non exploitable / watchlist / exploitable /
       refusé / ambigu
     - Jamais sans validation des couches amont

1.6  Définir le contrat de mémoire
     - Ce que chaque couche doit écrire en mémoire
     - Ce que chaque couche doit lire en mémoire
     - Cycle de vie des entrées mémoire

### Critère de validation
- Les formats sont documentés
- Les interfaces entre couches sont claires
- Aucune couche ne dépend d'une couche aval

---

## PHASE 2 — COUCHE FORCES

### Objectif
Construire le lecteur de forces multi-devises et multi-timeframes,
avec MT4/SDI comme source primaire et MT5 comme lecture complémentaire.

### Chantiers
2.1  Inventorier l'existant V8 sur la capture des forces
     - EA MQ4 actuel : audit, bugs connus, capacités
     - Structure de la base dbfresh
     - Format actuel des données forces
     - Classification A/B/C/D pour migration

2.2  Spécifier le nouveau lecteur de forces V9
     - 8 devises : USD, GBP, EUR, JPY, CAD, CHF, AUD, NZD
     - Timeframes : M1, M5, M15, M30, H1, H4, D1
     - M1 séparé (ticks/vélocité, pas candle-close)
     - MT4/SDI pilote, MT5 tick complémentaire
     - Même broker pour éviter les différentiels
     - Refresh strategy : fréquence et contraintes DB

2.3  Reconstruire ou nettoyer l'EA MQ4
     - Corriger le bug du buffer indicateur
     - Corriger l'inversion AUD/USD
     - Corriger les valeurs shiftées M5+
     - Compiler et déployer sur tous les timeframes
     - Valider que les forces lues sont cohérentes

2.4  Construire le bridge MT4 → DB V9
     - Schéma de base V9 propre
     - Table forces : devise, timeframe, valeur, timestamp
     - Table ticks : prix, volume, timestamp (MT5)
     - Index et performance

2.5  Construire le reader de forces V9
     - Module Python qui lit la DB
     - Produit le format de sortie défini en 1.1
     - Gère le stale (données trop anciennes)
     - STALE_GATE bloquant si données périmées

2.6  Tests de validation couche Forces
     - Données présentes pour les 8 devises
     - Données présentes pour tous les timeframes
     - Pas d'inversion de devises
     - Cohérence temporelle (timestamps)
     - STALE_GATE fonctionne

### Critère de validation
- Les forces sont lues correctement
- 8 devises × 7 timeframes couverts
- M1 géré séparément
- MT4/SDI pilote, MT5 complémentaire
- STALE_GATE actif
- Aucune valeur inversée

---

## PHASE 3 — COUCHE SCÈNES

### Objectif
Transformer les forces brutes en scènes structurées.

### Chantiers
3.1  Définir le moteur de construction de scène
     - Entrée : snapshot de forces (8 devises × 7 TF)
     - Sortie : scène structurée (format 1.2)
     - Logique : assembler forces + zones + temporalité +
       coalitions + antagonismes en une scène cohérente

3.2  Détection des coalitions
     - Identifier les devises alignées
     - Mesurer l'intensité de l'alignement
     - Détecter les rotations de leadership

3.3  Détection des antagonismes
     - Identifier les conflits de forces
     - Mesurer l'intensité du conflit
     - Détecter les bascules d'équilibre

3.4  Extraction de la cinématique locale
     - Angle, courbure, pente
     - Pliure (rupture de dynamique)
     - Accélération / décélération
     - Rotation de force
     - Compression / extension

3.5  Confluences multi-timeframes
     - Emboîtement des lectures MTF
     - Cascades temporelles
     - Signatures de cohérence

3.6  Tests de validation couche Scènes
     - Une scène est produite à partir de forces réelles
     - Les coalitions sont détectées
     - Les antagonismes sont détectés
     - La cinématique est extraite
     - Les confluences MTF sont présentes

### Critère de validation
- Une scène peut être produite
- Elle contient forces, zones, temporalité, coalitions,
  antagonismes, cinématique et confluences
- La scène est comparable à la perception humaine

---

## PHASE 4 — COUCHE COMPORTEMENTS

### Objectif
Qualifier ce que la scène est en train de faire dans le temps.

### Chantiers
4.1  Définir la bibliothèque de comportements
     - Maintien
     - Bascule
     - Lutte / combat de forces
     - Contraction
     - Extension
     - Tension
     - Rupture
     - Rééquilibrage
     - Annulation (recroisement)
     - Préparation d'ouverture de fenêtre
     - Seconde bosse
     - Rotation de leadership

4.2  Construire le lecteur de comportements
     - Entrée : scène courante + historique de scènes
     - Sortie : comportement qualifié (format 1.3)
     - Logique : comparer les scènes successives
       pour identifier la dynamique

4.3  Détection des transitions
     - Quand un comportement bascule vers un autre
     - Points de rupture comportementale
     - Annulations et retours

4.4  Singularités locales
     - Identifier ce qui rend une scène unique
     - Détecter les variantes d'un comportement connu
     - Journaliser les cas atypiques

4.5  Tests de validation couche Comportements
     - Un comportement est qualifié à partir de scènes
     - Les transitions sont détectées
     - Les singularités sont journalisées
     - Le comportement est comparable à la perception humaine

### Critère de validation
- Un comportement peut être qualifié
- Les transitions sont traçables
- Les cas atypiques sont journalisés
- Le comportement reflète la perception de l'opérateur

---

## PHASE 5 — COUCHE FENÊTRES

### Objectif
Détecter quand une dynamique devient potentiellement exploitable.

### Chantiers
5.1  Définir les types de fenêtres
     - Absente
     - En préparation
     - Ouverte
     - Fragile
     - Invalidée
     - Ambiguë

5.2  Construire l'évaluateur de fenêtres
     - Entrée : comportement qualifié + contexte
     - Sortie : statut de fenêtre (format 1.4)
     - Logique : évaluer si le comportement
       ouvre, ferme, ou maintient une fenêtre

5.3  Gestion de la durée de vie des fenêtres
     - Suivi de l'ouverture à la fermeture
     - Détection de fragilité
     - Conditions d'invalidation

5.4  Tests de validation couche Fenêtres
     - Une fenêtre peut être qualifiée
     - Le cycle de vie est traçable
     - L'absence de fenêtre est une réponse valide
     - Le système peut dire "pas de fenêtre"

### Critère de validation
- Une fenêtre peut être détectée
- Son cycle de vie est traçable
- L'absence de fenêtre est acceptée comme réponse normale
- Pas de fausse fenêtre sans comportement confirmé

---

## PHASE 6 — REPLAY ET APPRENTISSAGE

### Objectif
Construire le système centralisé de replay pour confronter
les cas présents aux cas passés et enrichir la reconnaissance.

### Chantiers
6.1  Construire la base de replay centralisée
     - Stockage des scènes historiques
     - Stockage des comportements historiques
     - Stockage des fenêtres historiques
     - Stockage des résultats observés

6.2  Construire le moteur de confrontation
     - Comparer une scène courante aux scènes passées
     - Détecter ressemblances, divergences, singularités
     - Score de similarité

6.3  Construire le journal des singularités
     - Cas atypiques
     - Variantes de comportements
     - Nouveaux patterns non classés

6.4  Consolidation de la mémoire
     - Promouvoir les hypothèses validées vers memory.md
     - Archiver les hypothèses rejetées
     - Enrichir la bibliothèque de comportements

6.5  Apprentissage progressif
     - Familles de scènes émergentes
     - Comportements récurrents
     - Conditions de fenêtres validées

### Critère de validation
- Le replay peut comparer un cas à l'historique
- Les singularités sont journalisées
- La mémoire s'enrichit avec le temps
- Les familles de comportements émergent

---

## PHASE 7 — EXPLOITABILITÉ CONTRÔLÉE

### Objectif
Évaluer si une fenêtre devient exploitable,
uniquement après validation de toutes les couches amont.

### Chantiers
7.1  Construire le gate d'exploitabilité
     - Entrée : fenêtre qualifiée + replay + confiance
     - Sortie : statut d'exploitabilité (format 1.5)
     - Jamais sans validation des couches amont

7.2  Règles de refus
     - Refus si perception non stabilisée
     - Refus si scène ambiguë
     - Refus si comportement non qualifiable
     - Refus si fenêtre non confirmée
     - Refus si replay insuffisant

7.3  HITL sur exploitabilité
     - Toute fenêtre potentiellement exploitable
       mais mal prouvée → validation humaine
     - Toute nouvelle catégorie de fenêtre → validation humaine

7.4  Tests de validation couche Exploitabilité
     - Le gate refuse correctement les cas faibles
     - Le gate n'approuve que les cas prouvés
     - L'absence d'exploitabilité est une réponse valide

### Critère de validation
- Le gate d'exploitabilité fonctionne
- Les refus sont traçables et justifiés
- Aucune exploitation sans perception stable
- HITL actif sur les cas sensibles

---

## PHASE 8 — ORCHESTRATION COMPLÈTE

### Objectif
Connecter toutes les couches en une boucle cohérente.

### Chantiers
8.1  Construire l'orchestrator
     - Lit l'état global
     - Choisit la couche à activer
     - Empêche les raccourcis cognitifs
     - Gère les conditions d'arrêt

8.2  Connecter les couches
     Forces → Scènes → Comportements → Fenêtres → Exploitabilité
     - Vérifier que chaque couche consomme la sortie de la précédente
     - Vérifier qu'aucune couche ne court-circuite une amont

8.3  Mémoire dans la boucle
     - Chaque cycle écrit dans memory_temp.md
     - Les résultats validés montent dans memory.md
     - Les handoffs passent par exchange.md

8.4  Boucle de replay
     - Après chaque cycle, le cas est confronté à l'historique
     - Les singularités sont journalisées
     - La mémoire s'enrichit

8.5  Garde-fous dans la boucle
     - Max itérations par cycle
     - Stagnation détectée
     - Budget temps / coût / tokens
     - Refus d'exécution si perception non stabilisée
     - HITL si ambiguïté

8.6  Tests de validation orchestration
     - La boucle complète tourne de Forces à Exploitabilité
     - Les garde-fous sont actifs
     - Le système peut s'arrêter proprement
     - Le système peut dire "je ne sais pas"

### Critère de validation
- La boucle complète tourne
- Les garde-fous sont actifs
- Le système peut dire "pas de fenêtre" ou "je ne sais pas"
- Aucune exécution sans perception stable

---

## PHASE 9 — MIGRATION V8 → V9

### Objectif
Migrer sélectivement les éléments utiles de V8 vers V9.

### Chantiers
9.1  Inventaire complet V8
     - Lister tous les fichiers, modules, scripts
     - Lister toutes les bases de données
     - Lister tous les documents
     - Lister toutes les configurations

9.2  Classification A/B/C/D
     A = reprendre tel quel
     B = réécrire avant reprise
     C = archiver
     D = re-spécifier depuis zéro

9.3  Migration par ordre
     1. Doctrine (déjà fait en Phase 0)
     2. Lexique (déjà fait en Phase 0)
     3. Mémoire (audit + reformulation)
     4. Structure agents/skills
     5. Assets
     6. Scripts
     7. Éléments métiers sélectionnés

9.4  Validation post-migration
     - V9 reste compréhensible sans lire V8
     - Aucune dette implicite
     - Tous les éléments migrés sont justifiés

### Critère de validation
- L'inventaire V8 est complet
- Chaque élément est classé
- La migration est traçable
- V9 est autonome

---

## DÉPENDANCES ENTRE PHASES

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
                                                           ↓
Phase 9 (parallèle) ←─── Phase 6 ←────────────────────────
                                ↓
                          Phase 7 → Phase 8

Phase 9 (migration V8) peut démarrer en parallèle dès la Phase 2,
mais ne peut se finaliser qu'après la Phase 5.

---

## DÉFINITION DE DONE — V9

V9 existe réellement quand :

✅ il peut lire les forces des 8 devises sur 7 timeframes
✅ il peut produire une scène structurée
✅ il peut qualifier un comportement
✅ il peut détecter une fenêtre
✅ il peut dire qu'une fenêtre est absente
✅ il peut confronter un cas présent à des cas passés
✅ il peut se taire quand la lecture n'est pas prouvée
✅ il peut refuser l'exploitabilité sans percevoir
✅ la mémoire s'enrichit à chaque cycle
✅ les garde-fous sont actifs
✅ le HITL fonctionne sur les cas sensibles

---

## PRIORISATION RECOMMANDÉE

Immédiat : Phase 0 (fondation) ✅ + Phase 1 (squelette cognitif)
Court terme : Phase 2 (forces) + Phase 3 (scènes)
Moyen terme : Phase 4 (comportements) + Phase 5 (fenêtres)
Long terme : Phase 6 (replay) + Phase 7 (exploitabilité) + Phase 8 (orchestration)
Transverse : Phase 9 (migration V8 → V9) en parallèle dès Phase 2