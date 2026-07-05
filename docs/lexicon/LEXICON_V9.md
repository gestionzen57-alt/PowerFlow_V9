# LEXICON_V9.md

## But
Fixer le vocabulaire natif de PowerFlow V9.

## Termes fondamentaux

### Force
Variation structurée d'intensité, direction ou équilibre entre devises / timeframes.

### Scène
Configuration locale du marché dans une fenêtre donnée.

### Comportement
Évolution dynamique d'une scène dans le temps.

### Fenêtre
Moment où une dynamique devient surveillable, exploitable, fragile ou invalide.

### Zone
Espace de prix ou de structure significatif pour la lecture.

### Coalition
Alignement de plusieurs forces / devises / horizons vers une même dynamique.

### Antagonisme
Conflit de forces entre devises, horizons ou structures.

### Cinématique
Lecture du mouvement des forces : angle, courbure, pliure, pente, rotation, accélération, rupture.

### Orchestration
Organisation globale des relations entre forces, scènes, temporalités et devises.

### Replay
Confrontation d'un cas actuel à des cas passés pour enrichir la reconnaissance.

### Exploitabilité
Qualification tardive d'une fenêtre, jamais une définition première de la réalité.

## Termes complémentaires (Phases 7-9)

Ajoutés au fil des phases de déploiement live, monitoring et décision. Même règle que
ci-dessus : privilégier ce vocabulaire, justifier tout remplacement.

### Snapshot
Capture instantanée des 8 forces d'un symbole sur un timeframe donné, à un instant `bar_time`.
Une bougie fermée produit exactement un snapshot (anti-replay, `forces_snapshots`).

### Stale
Donnée périmée : son âge dépasse le seuil de fraîcheur défini par timeframe dans
`core/v9/config.py` (`STALE_THRESHOLDS_MS`). Une donnée stale est marquée, jamais supprimée
(`core/v9/stale_gate.py`).

### Pliure
Changement de direction (inversion de pente) de la force d'une devise, détecté au niveau de
la cinématique locale d'une scène (voir `PLIURE_THRESHOLD` dans `config.py`).

### Orchestrateur
Composant (`core/v9/orchestrator.py`) qui déclenche automatiquement la chaîne cognitive
(Scène → Comportement → Fenêtre → Exploitabilité) après chaque insertion non-stale, contrôlé
par `config.ENABLE_CHAIN`.

### Live
Données en temps réel issues du marché ouvert, capturées par l'EA MT4 et le serveur TCP,
par opposition à Replay.

### Régime
État global du marché sur un horizon donné (tendance, range, breakout, compression), calculé
sur une fenêtre glissante (`REGIME_LOOKBACK_BARS`). Introduit en Phase 9
(`core/v9/regime_detector.py`, `regime_db.py`) — **Phase 9 terminée et canonisée le
2026-07-05** (voir `docs/phases/PHASE9_DECISION.md`). Seuils encore `PROVISIONAL` (portés de
V8 sans recalibration sur données V9 réelles).

### Zone extrême
Niveau HTF (higher timeframe) où les forces atteignent un extrême relatif, générant une
opportunité potentielle en LTF (lower timeframe). Introduit en Phase 9 (`core/v9/zone_db.py`)
— table créée mais **non alimentée par un détecteur** (gap connu, non bloquant, ~5-8j
d'effort estimé, voir `docs/phases/PHASE9_DECISION.md`). Les principes qui en dépendent se
dégradent gracieusement.

### Principe
Règle de trading évaluable, exprimée comme une fonction pure (entrée → booléen + confiance).
Un principe est un DÉTECTEUR, jamais un signal de trading direct (voir
[DOCTRINE.md](../DOCTRINE.md) règle 11). Introduit en Phase 9 (`core/v9/principle_engine.py`,
`principle_db.py`, dossier `core/v9/principles/*.yaml`, 27 principes migrés de V8) — **Phase 9
terminée** : 10 principes ACTIVE, 17 SHADOW.

### Signal
Agrégation de plusieurs principes ACTIVE déclenchés en une direction et un niveau de
confiance, filtrée par exploitabilité et régime. Introduit en Phase 9
(`core/v9/signal_generator.py`, `signal_db.py`) — **Phase 9 terminée**.

### Décision
Signal replacé dans son contexte complet (scène, comportement, fenêtre, exploitabilité,
régime) plus une action qualitative recommandée (observer/surveiller/preparer_entree/
aucune_action), journalisée pour confrontation ultérieure. Introduit en Phase 9
(`core/v9/decision_db.py`, `decision_logger.py`) — **Phase 9 terminée**. Point ouvert : ne
marque pas encore explicitement replay vs live (doctrine règle 12).

## Règle
Tout document, agent ou skill V9 doit privilégier ce vocabulaire.
Si un terme extérieur le remplace sans raison, il doit être justifié.