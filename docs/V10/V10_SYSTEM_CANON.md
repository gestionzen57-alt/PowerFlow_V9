# V10 SYSTEM CANON — Document de référence pour relancer V10

> **Date de pause** : 2026-08-15
> **Branche** : `feat/zcode-night` (HEAD au moment de la pause)
> **Tests** : 1405/1406 verts (1 fail non bloquant : `test_validate_big_gap_exclude`)
> **État** : Système en pause — Søn se recentre sur son trading manuel
>
> Ce document est le **point d'entrée unique** pour quiconque (Søn ou une IA)
> veut comprendre et relancer V10. Tout est ici.

---

## 1. POURQUOI V10 EXISTE

V10 est un **système cognitif financier auto-apprenant** qui observe les forces
de devises (Fatman), structure le marché, invente des stratégies, apprend de
ses trades, et agit sans permission préalable. Il protège le capital (R10 =
seul garde-fou : DD max 10%, position max 2%, levier max 5x).

V10 a été construit sur l'infrastructure de V9 (capture EA MT4, DB
forces_snapshots) mais est **code-additif pur** : 0 import de `core/v9/` dans
`core/v10/`. Les deux systèmes sont désormais dans des dépôts séparés.

---

## 2. ARCHITECTURE V10

### 2.1 Les 7 modules intelligents

```
MODULE 0 — MARCHÉ (DB v9_forces.db, alimentée par capture V9)
   ↓
MODULE 1 — CAPTURE (V9 conservé, port 31685, EA V9_Sonde_M1.mq4)
   ↓
MODULE 2 — CONTEXTE (TA lecture CEO, V10 réinjecté)
   ↓
MODULE 3 — ALERTES & EXÉCUTION (Telegram + Broker)
   ↓
MODULE 4 — DÉCISION (Chain-of-thought, 5 étapes)
   ↓
MODULE 5 — OPTIMISATION (Bayesian + Genetic)
   ↓
MODULE 6 — APPRENTISSAGE (Online RL, drift detection)
   ↓
MODULE 7 — RÉFLEXION (Self-explanation, post-mortem auto)
```

### 2.2 Code

| Dossier | Fichiers | Rôle |
|---|---|---|
| `core/v10/` | 140 `.py` | Cœur cognitif : force, structure, contexte, orchestrateur, VSA, cinématique, confluence, score qualité, RL adapter, bayesian recalibrator, replay engine, signal generator, decision pipeline |
| `scripts/v10_*.py` | 99 scripts | Runners : edge overlap, daily learning, replay, calibration, dashboards, alertes Telegram, benchmarks |
| `tests/test_v10_*.py` | 88 tests | Tests unitaires + intégration (1405 passent au moment de la pause) |
| `config/v10_*` | 8 fichiers | Seuils bayesian, active thresholds, CEO gate overlap, force native calibrated |
| `docs/V10/` | 51 docs | Doctrine, brainstorming, piliers, rapports, méthodologie |
| `data/v10_*.db` | 3 DBs (18 Mo) | v10_behaviors.db (15M), v10_decisions.db (1.3M), v10_learning_state.db (2.7M) |

### 2.3 Doctrine V10 — 10 règles (R1-R10)

| Règle | Nom | Principe |
|---|---|---|
| R1 | AGIR | Le système agit par défaut, sans permission CEO |
| R2 | LIVE-MICRO-LOT | Micro-lot 0.01→1.0 selon Sharpe |
| R3 | INVENTER | Génération continue : features, stratégies, seuils |
| R4 | APPRENDRE | Online RL — mise à jour poids à chaque trade clôturé |
| R5 | RÉFLÉCHIR | Chain-of-thought 5 étapes |
| R6 | EXPLIQUER | Chaque chiffre = 1 query SQL. Fail-open partout. |
| R7 | MESURER | KPIs auto-archivés — tests verts AVANT commit |
| R8 | AUTO-AMÉLIORER | Boucle fermée 100% auto |
| R9 | AUDITABLE | Décisions reproductibles bit-pour-bit |
| R10 | PROTÉGER CAPITAL | DD max 10%, position max 2%, levier max 5x |

**R10 = seul vrai garde-fou. Tout le reste : GO.**

---

## 3. L'EDGE OVERLAP (le terrain de chasse)

```
Fenêtre   : 12-16 UTC (OVERLAP Londres + NY)
Paires    : EURUSD, USDCHF, AUDUSD
TF        : M15 (barres fermées)
Signal    : |delta_forces| ≥ 25 → BUY si delta>0, SELL sinon
Filtre    : score de qualité 0-10 (cinématique + confluence + zones)
TP/SL     : TP=2xATR, SL=1xATR, hold max 4 barres M15
Sizing    : modulé par le score (🟢 ×1.0-1.5, 🟡 ×0.5-0.8, 🔴 ×0)
R10       : zéro ordre réel (broker non connecté)
```

### État de l'edge au moment de la pause

| Date | Trades | WR | PnL | Verdict |
|---|---|---|---|---|
| 13/08 (replay 7j) | 270 | 59.3% | +540 pips | PROMOTE (gate passée) |
| 14/08 (replay 5j audit) | 55 | 41.82% | -18 pips | DRAWDOWN — ne pas promouvoir |
| 14/08 (shadow live) | 4 | 25% | -2.6 pips | DRAWDOWN |
| 15/08 (dataset refresh) | 100k | 40.8% | -713 pips | NONE-level dominant |

**Verdict honnête** : l'edge mécanique (delta_forces brut) n'est pas fiable.
Il était probablement surajusté sur la période de tuning. L'audit VSA
recommande : **NE PAS promouvoir LIVE** tant que l'interprétation
institutionnelle de Søn n'est pas codée.

---

## 4. LES 7 PILIERS DE LA LECTURE INSTITUTIONNELLE

Le système actuel trade sur un delta_forces mécanique. La vision de Søn
est un système qui **lit le marché** comme un trader humain. 7 piliers ont
été extraits du brainstorming de Søn (13-14/08) :

| # | Pilier | Description | Codé ? | Module |
|---|---|---|---|---|
| 1 | Cinématique | La courbe avant la valeur : pics, exhaustion, divergence | ✅ | `v10_cinematics.py` |
| 2 | Confluence TF | M5+M15+M30+H1, sizing modulé | ✅ | `v10_confluence_tf.py` |
| 3 | Coalition multidevise | Leader/follower, rupture risk-on | ⬜ squelette | `v10_coalition_devises.py` |
| 4 | Personnalité de devise | Tempo, véracité, comportement par devise | ⬜ squelette | `v10_personality_devise.py` |
| 5 | Fractalité temporelle | 1min → H4, TF de lisibilité par devise | ⬜ squelette | `v10_fractalite_tf.py` |
| 6 | Cycles Fatman | Naissance → expansion → maturité → épuisement | ⬜ squelette | `v10_cycles_fatman.py` |
| 7 | Forces par TF | Échelles propres, zones par percentile, croisement + double test + propagation/répulsion | 🔶 calibration | `v10_forces_par_tf.py` |

**Le module unificateur** : `v10_quality_score.py` — agrège les piliers en un
score 0-10. Le paradigme est **CHASSEUR** (score de qualité → action) et non
**NOTAIRE** (block/allow binaire → friction).

### Documents de brainstorming (source de vérité)

| Document | Piliers | Contenu |
|---|---|---|
| `docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` | 4+5+6 | Personnalité devise, fractalité, cycles (15 blocs de questions) |
| `docs/V10/LECTURE_FORCES_PAR_TIMEFRAME.md` | 7 | Échelles propres, croisement, zones extrêmes, double test, répulsion |
| `docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` | 6+7 | Croisement H4 = changement de phase, emboîtement H1, antagonisme |
| `docs/V10/PILLIERS_STRATEGIQUES.md` | Tous | Synthèse 7 piliers + score qualité + architecture 7 couches |
| `docs/V10/METHODOLOGIE_INJECTION.md` | — | Contrat multi-IA (le brainstorming de Søn = source de vérité) |
| `docs/V10/POINT_GENERAL_INSTITUTIONNEL.md` | Tous | Tableau de bord détaillé 7 piliers + 20 règles |

---

## 5. AUDIT VSA P1-P15 (14/08)

11 patches atomiques livrés pour aligner le système sur la doctrine VSA pure
(Tom Williams) :

| Patch | Fichier | Doctrine corrigée |
|---|---|---|
| P1 | `v10_vsa.py` | close_location ≥ 0.6 (MARKUP), ≤ 0.4 (MARKDOWN), upthrust flag |
| P2 | `v10_filter_compositor.py` | Fatman = filtre contexte, jamais trigger d'entrée |
| P3 | `v10_vsa.py` | σ-bands sur spread (ATR/20 doctrine) |
| P4 | `v10_decision_pipeline.py` | Gate triple VSA (≥1 confirmation wyckoff OU compression) |
| P5 | `v10_vsa.py` | End-of-bar gate (is_closed_bar=False → NEUTRAL) |
| P6 | `v10_replay_engine.py` | Conviction = effort + close_location (pas volume seul) |
| P7 | `v10_signal_generator_live.py` | Gate Effort/Résultat sur decide_signal_level |
| P8 | `v10_quality_score.py` | Filtre is_closed_bar=1 sur cinématique M15 |
| P9 | `v10_confluence_tf.py` | σ-threshold=1.0 sur pente M5 |
| P10 | `v10_force_native.py` | force_boost pondéré par close_location |
| P15 | `v10_vsa.py` | Gap detection open vs close précédent |

Rapport complet : `docs/V10/AUDIT_VSA_RAPPORT_COMPLET_2026-08-14.md`

---

## 6. DÉPENDANCE V9 — COMMENT V10 ACCÈDE AUX DONNÉES

### Le lien unique : la DB `v9_forces.db`

V10 lit la table `forces_snapshots` dans la DB V9 (`data/v9_forces.db`, 36 Go).
Cette table est alimentée par le **capture_server V9** (port TCP 31685) qui
reçoit les données de l'EA MQL4 `V9_Sonde_M1.mq4` sur MT4.

```
MT4 → EA V9_Sonde_M1 → capture_server (port 31685) → v9_forces.db → V10 lit
```

### Après séparation physique

V10 (dans `C:\projet\V10`) accède à la DB V9 par **chemin absolu** :

```python
# core/v10/v10_db_config.py
V9_FORCES_DB = os.getenv("V9_FORCES_DB_PATH", r"C:\projet\V9\data\v9_forces.db")
```

Si V9 est arrêté (capture_server stoppé), V10 ne reçoit plus de données
fraîches — mais peut toujours faire des replays sur l'historique.

### Tables V10 lit dans v9_forces.db (lecture seule)

- `forces_snapshots` — table maîtresse (332k lignes, alimentée par capture)
- `paper_trades` — 337 trades V9 (pour comparaison V9 vs V10)
- `signals` — signaux V9
- `decisions` — décisions V9

### DBs propres à V10 (dans `C:\projet\V10\data\`)

- `v10_behaviors.db` (15 Mo) — 79 865 comportements enregistrés
- `v10_decisions.db` (1.3 Mo) — 1 109 décisions V10
- `v10_learning_state.db` (2.7 Mo) — état apprentissage RL

---

## 7. PROCÉDURE DE RELANCE

Si tu reviens dans 1 mois, 6 mois, 1 an — voici comment redémarrer V10 :

### 7.1 Vérifier que V9 capture toujours (optionnel)

```bash
cd C:\projet\V9
python -c "from core.v9.config import DB_PATH; print(DB_PATH)"
# Vérifier que capture_server tourne (port 31685)
netstat -an | findstr 31685
```

Si V9 ne tourne plus, V10 peut quand même faire des replays sur l'historique
accumulé (332k snapshots dans forces_snapshots).

### 7.2 Démarrer V10

```bash
cd C:\projet\V10

# Vérifier les tests
python -m pytest tests/test_v10_*.py -q --tb=short
# Objectif : 1405+ tests verts

# Configurer le chemin DB V9 (si non-default)
set V9_FORCES_DB_PATH=C:\projet\V9\data\v9_forces.db

# Lancer un scan edge OVERLAP
python scripts/v10_shadow_edge_overlap.py

# Lancer le daily learning
python scripts/v10_daily_learning.py

# Lancer un replay 5 jours
python scripts/v10_replay_5d_audit_p1_p15.py
```

### 7.3 Cron jobs V10 (à réinstaller si besoin)

- `v10-edge-overlap-shadow` — scan edge OVERLAP (*/20 min, lun-ven)
- `v10-edge-learning-loop` — boucle d'apprentissage drift

### 7.4 Ce qui reste à faire (feuille de route)

1. **Coder les 5 piliers manquants** (coalition, personnalité devise,
   fractalité, cycles, forces par TF) — voir `docs/V10/PILLIERS_STRATEGIQUES.md`
2. **Valider les patterns comportementaux** (Mission 3) — voir
   `docs/V10/SON_INTERPRETATION.md` §2.2
3. **Valider les seuils cinématiques** (Mission 4) — voir §4.1
4. **Prouver l'edge hors-échantillon** avant toute promotion LIVE
5. **Comprendre Fatman dans son ensemble** — Søn doit pouvoir expliquer
   son edge à un humain en 5 minutes sans contradictions

---

## 8. DOCUMENTS PIVOTS (à lire au redémarrage)

| Ordre | Document | Rôle |
|---|---|---|
| 1 | **Ce fichier** (`V10_SYSTEM_CANON.md`) | Point d'entrée unique |
| 2 | `PAUSE_NOTICE.md` (racine V10) | Pourquoi on a mis en pause |
| 3 | `docs/V10/PILLIERS_STRATEGIQUES.md` | Synthèse 7 piliers + paradigme CHASSEUR |
| 4 | `docs/V10/METHODOLOGIE_INJECTION.md` | Contrat multi-IA (Søn = source de vérité) |
| 5 | `docs/V10/DOCTRINE_PLEIN_POTENTIEL.md` | Doctrine autonomie totale |
| 6 | `docs/V10/AUDIT_VSA_RAPPORT_COMPLET_2026-08-14.md` | Audit VSA 11 patches |
| 7 | `docs/V10/STATE.md` | État du pipeline cognitif |
| 8 | `workspace/perplexity/memory/DECISIONS_LOG.md` | Décisions structurantes |

---

## 9. LEÇON DE LA PAUSE

> Le système devait servir Søn, mais c'est Søn qui servait le système.
> L'edge mécanique (delta_forces brut) performe moins bien que le trading
> manuel de Søn. L'interprétation institutionnelle (7 piliers) n'est pas
> encore codée. La priorité au redémarrage n'est pas le code — c'est
> la compréhension par Søn de son propre edge, qu'il pourra alors
> expliquer et que le système pourra alors capturer.

---

*Document rédigé le 2026-08-15 lors de la séparation physique V9/V10.
Tous les chiffres sont réels, vérifiés au moment de la pause.*