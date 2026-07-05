# CHAÎNE COGNITIVE — PowerFlow V9

## Statut
Détail des 5+1 couches (+3 couches Phase 9 en cours). Pour la doctrine derrière cet ordre,
voir [docs/doctrine/CHARTE_COGNITIVE_V9.md](../doctrine/CHARTE_COGNITIVE_V9.md) et
[docs/DOCTRINE.md](../DOCTRINE.md). Pour le schéma DB, voir [DB_SCHEMA.md](DB_SCHEMA.md).
Pour le flux temps réel bout en bout, voir [PIPELINE_LIVE.md](PIPELINE_LIVE.md).

## Principe : chaque couche est additive et filtrante

```
Forces          100% des données brutes                        (aucun filtre)
   │
   ▼ SceneBuilder
Scènes          structure l'information            → qui / quoi
   │
   ▼ BehaviorAnalyzer
Comportements   ajoute la dynamique                 → comment
   │
   ▼ WindowGate
Fenêtres        filtre par opportunité              → quand
   │
   ▼ ExploitabilityEvaluator
Exploitabilité  filtre par qualité                   → est-ce tradable
   │
   ▼ RegimeDetector + PrincipleEngine + SignalGenerator + DecisionLogger  [Phase 9]
Décision        transforme en action recommandée     → que faire (jamais un ordre)
```

Aucune couche aval ne court-circuite une couche amont : chaque table référence son
prédécesseur par identifiant (`*_ref` / `*_id`), jamais par duplication de ses colonnes
(voir [DB_SCHEMA.md](DB_SCHEMA.md) « Vue d'ensemble des références inter-tables »).

## 1. Forces (`forces_reader.py`, `capture_server.py`, `db_schema.py`)

Lecture brute des 8 devises (USD, GBP, EUR, JPY, CAD, CHF, AUD, NZD) sur 7 timeframes
(M1 tick/vélocité + M5/M15/M30/H1/H4/D1 candle-close), transformées en direction, vitesse,
croisement, recroisement, rejet/répulsion, compression/extension. Gate unique en amont :
`StaleGate` marque (jamais ne supprime) toute donnée dont l'âge dépasse le seuil du
timeframe. Anti-replay : une bougie clôturée = un seul snapshot (index UNIQUE).

## 2. Scènes (`scene_builder.py`)

Structure l'état des forces à un instant : coalitions (devises alignées), antagonismes
(devises opposées), cinématique locale (angle, courbure, pente, pliure, rotation,
compression/extension calculés pas à pas entre snapshots), confluences multi-timeframes,
contexte temporel (session de marché), zone (dérivée des OHLC). Consomme uniquement
`forces_snapshots`, référence via `forces_snapshot_ref`.

## 3. Comportements (`behavior_analyzer.py`)

Qualifie la dynamique d'une scène dans le temps : 12 qualifications (maintien, bascule,
lutte_forces, contraction, extension, tension, rupture, reequilibrage, annulation,
preparation_ouverture_fenetre, seconde_bosse, rotation_leadership), avec intensité, phase
(initiation/développement/culmination/résolution), transitions (comportement précédent,
point de rupture, sens de transition) et comparaison aux cas connus (similarité, variantes).
Consomme uniquement `scenes` (déréférence administrative étroite vers symbol/timeframe
seulement, jamais les valeurs de force).

## 4. Fenêtres (`window_gate.py`)

Évalue l'ouverture/fermeture d'une opportunité : statut parmi 6 valeurs (absente,
en_preparation, ouverte, fragile, invalidee, ambigue), type (retournement, continuation,
rupture_range), niveau de confiance (bonus/malus), détection de fragilité, cycle de vie
(ouverture → fragile → invalidée). Consomme uniquement `behaviors`.

## 5. Exploitabilité (`exploitability_evaluator.py`)

Jugement tardif de tradabilité : statut parmi 5 valeurs (non_exploitable, watchlist,
exploitable, refuse, ambigu), raison de refus (cascade priorisée sur 5 valeurs), confiance
globale (bonus/malus documentés), validation HITL obligatoire dans certains cas (première
validation d'un statut exploitable, premier cas d'un type de fenêtre, ratio replay
incertain), `replay_context` (comparaison aux comportements passés de même qualification).
Consomme `windows` (+ déréférence étroite vers `behaviors`/`scenes` pour la similarité et
la confluence MTF, jamais de réinterprétation des valeurs de force).

## 6. Décision — Phase 9, en cours

> Code présent dans l'arborescence mais développé sur une session concurrente au moment de
> la rédaction (2026-07-05), non finalisé. Détail complet à valider à la clôture dans
> [docs/phases/PHASE9_DECISION.md](../phases/PHASE9_DECISION.md).

Trois sous-couches parallèles/complémentaires à Exploitabilité, puis une couche de synthèse :

- **RegimeDetector** — état global du marché par devise (NEUTRE/PALIER/CASSURE/EXTENSION/
  RETOUR_EQUILIBRE/REJET), machine à états portée de V8, référence `forces_snapshot_ref`.
- **PrincipleEngine** — évalue les 27 principes migrés de V8 (`core/v9/principles/*.yaml`),
  dont 10 principes ACTIVE routés vers le signal et 17 en mode SHADOW (journalisés,
  jamais routés). Un principe est un **détecteur** (entrée → bool + confiance), jamais un
  signal de trading direct.
- **SignalGenerator** — agrège les principes ACTIVE déclenchés en une direction + confiance,
  filtré par le statut d'exploitabilité (doit être `exploitable`) et par le régime (rejette
  PALIER/NEUTRE). Journalise toujours une `raison_absence` si aucun signal n'est produit.
- **DecisionLogger** — assemble signal + contexte complet (scène, comportement, fenêtre,
  exploitabilité, principes, régime) en une décision journalisée, avec une action
  **qualitative uniquement** (observer / surveiller / preparer_entree / aucune_action) —
  jamais un ordre d'exécution.

## Ce qui n'existe pas encore

- **Layer MT5 / ticks** (Phase 11) — `cassure_type` reste toujours `INDETERMINEE` faute de
  microstructure tick en V9.
- **`zone_diagnostics`** (table créée en Phase 9, non alimentée) — les 9 principes
  `node_rule` qui en dépendent sont évalués mais ne se déclenchent jamais tant qu'elle est
  vide (dégradation gracieuse documentée, voir [DB_SCHEMA.md](DB_SCHEMA.md)).
- **Exécution d'ordres** (Phase 12) — hors périmètre de toute couche actuelle.
