# CACHE_BOARD — PowerFlow V9

## Rôle
Ce fichier est le tableau de bord compact de reprise.
Il doit pouvoir être relu en 2 minutes maximum au début de chaque session.

## Statut global
- Projet : PowerFlow V9
- Nature : refondation cognitive + architecture propre
- Base : dossier V9 vide
- Source de vérité : GitHub
- Doctrine : architecture-first
- État : Chaîne cognitive V9 étendue à 9 couches, TOUTES TERMINÉES — Forces → Scènes →
  Comportements → Fenêtres → Exploitabilité (Phases 1-6) → Régime → Principes → Signal →
  Décision (Phase 9). Phase 7 (déploiement live), Phase 8 (monitoring/calibration/replay),
  Phase 9 (Décision et Principes) **canonisée 2026-07-05**, Phase 9.7 (Paper-Trade Simulator)
  **livrée 2026-07-07**, Phase 9.8 (VPS-READY) **livrée 2026-07-07**, Phase 9.9 (Consolidation
  Complète) **livrée 2026-07-07**, **Phase 9.10 (WIN/LOSS resolver)** **livrée 2026-07-08**,
  **Phase 13 (recalibrage arbiter)** **livrée 2026-07-10**. Zone_diagnostics alimentée
  (ZoneDetector + grammaire complète). **930 tests verts** (vérifiés 2026-07-10, +52 depuis
  la session H24 autopilot CEO).
- **Mémoire** : interne V9 (workspace/perplexity/memory/*.md + JOURNAL.md), 0 dépendance mem0
  (archivé 2026-07-07).
- **Doctrine** : 28 règles immuables (règle 28 = Hermes opérateur git unique, ajoutée 2026-07-07).
- **6 décisions §5 VPS** actées 2026-07-07 : A (orchestrateur central), 2a (Telegram HITL),
  3a (SQLite WAL), 4a (EA Phase 7 réutilisé), 5b (watchdog livré), 6a (DNS swap rollback).

  **Session 2026-07-06 — Calibration seuils + enrichissement cinématique :**
  - ANTAGONISM_THRESHOLD : 10.0 → 31.39 ✅ (calibration live n=218 M5+, commit `460716f`)
  - COALITION_THRESHOLD : maintenu 5.0 (gain marginal, 89.8% scènes déjà couvertes)
  - PLIURE_THRESHOLD : 3.0 → 1.7 ✅ (proxy corrigé vitesse→pente, P90 sur n=1454 M5+, commit `e9bd9b1`)
  - Cinématique enrichie : `velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`
    ajoutés dans `_compute_cinematics()` (commit `e2ea619`)
  - 7 champs cinématiques injectés dans `principle_engine._load_shared_context()`
    (`velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`, `pente`,
    `courbure`, `pliure_detectee`, `pliure_severite`) — données désormais
    évaluables par les principes YAML (commit `db7bb6d`)

  **Gaps résiduels identifiés (audit 2026-07-06, non bloquants) :**
  - `vitesse` dans forces_snapshots = devise de base du symbole uniquement (pas par devise)
    → `velocite_moyenne` reste un proxy d'une seule devise. Levier P3 : enrichir EA MT4.
  - `REGIME_LOOKBACK_BARS = 20` identique pour tous TF (portage V8, non recalibré).
  - `SIMILARITY_THRESHOLD = 0.65` non recalibré sur données live V9.
  - `REPLAY_MIN_CAS = 3` → malus systématique en live naissant (P3, non urgent).
  - Cross-TF direction (h1_dir/m5_dir) calculée sur max(forces) — approximation connue.

## Décision fondatrice
V9 part de zéro.
Aucune mémoire, aucun skill, aucune convention, aucun workflow ancien n'est repris implicitement depuis V8/Hermes.

## Mission produit
Construire un système qui comprend les forces dans leur lecture :
- globale
- temporelle
- zonale
- multi-devises
- fenêtrée
- orchestrée
- fractale
- comportementale

## Ordre cognitif officiel
1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Ce que le projet n'est pas
- pas une simple migration technique
- pas un bot de signal prioritaire
- pas un projet RAG en premier
- pas une accumulation de modules
- pas une extension sale de V8

## Ce que le projet doit devenir
- une base saine
- une mémoire fiable
- une doctrine stable
- un squelette agentique propre
- une machine de confrontation / replay / apprentissage continu

## Chantiers actifs
- [A] Doctrine fondatrice V9 ✅
- [B] Structure repo propre ✅
- [C] Politique mémoire V9 ✅
- [D] Inventaire de migration V8 → V9
- [E] AGENT.md racine V9
- [F] Lexique natif V9 ✅
- [G] Formats couche Forces ✅
- [H] Formats couche Scènes ✅
- [I] Formats couches Comportements / Fenêtres / Exploitabilité ✅
- [J] Corrections post-review ✅
- [K] Phase 2A — EA MT4 ✅
- [L] Phase 2B — capture Python + STALE_GATE + forces_reader ✅
- [M] Fusion Phase 2 + harmonisation STALE_GATE ✅
- [N] Phase 3 — Couche Scènes ✅
- [O] Phase 4 — Couche Comportements ✅
- [P] Phase 5 — Couche Fenêtres ✅
- [Q] Phase 6 — Couche Exploitabilité ✅
- [R] Smoke test chaîne complète ✅
- [S] Phase 7 — Déploiement live ✅
- [T] Phase 8 — Monitoring + calibration + replay ✅
- [U] Phase 9 — Décision et Principes ✅ (9/9 node_rule ACTIVE déclenchables)
- [V] Gouvernance documentaire ✅
- [W] Outillage opérationnel Phase 9.5 ✅
- [X] Correctif DST observabilité ✅ (calendrier canonique non modifié — décision explicite)
- [Y] ZoneDetector + grammaire complète ✅ (zone_diagnostics alimentée, 283 tests)
- [Z] Calibration seuils live + cinématique enrichie ✅ (289 tests, 2026-07-06)
  - ANTAGONISM_THRESHOLD 31.39, PLIURE_THRESHOLD 1.7
  - velocite_moyenne / acceleration_vraie / dispersion_velocite dans _compute_cinematics
  - 7 champs cinématiques dans principle_engine._load_shared_context
- [AA] Phase 9.7 — Paper-Trade Simulator ✅ (60 tests, livrée 2026-07-07, commit `aa5c365`)
  - Arbiter, RiskManager, PaperTradeLogger, paper_trades_db, v9_paper_trade_run.py
  - Hit rate par principe (v9_scoring.py) — WIN/LOSS = 0 (attente London/NY)
- [AB] Phase 9.8 — VPS-READY ✅ (20 tests, livrée 2026-07-07, commit `4aa4fd3`)
  - scripts/v9_heartbeat.py (port 31685 + DB freshness + Telegram alive/alert)
  - install_heartbeat_cron.bat (2 schtasks Windows)
  - 6 décisions §5 actées dans DECISIONS_LOG.md
- [AC] Phase 9.9 — Consolidation Complète ✅ (livrée 2026-07-07, voir CHECKPOINT_20260707_PHASE9_9.md)
  - C-1/C-2/C-3 : CONTEXT_CONTRACT.md resync + init_all_dbs() + .gitignore runtime
  - C-4 : docs/V9_FONCTIONNEMENT.md (12 sections, mode d'emploi global)
  - C-5a : 27 YAML principes status uppercase + v9_status (10 ACTIVE / 17 SHADOW)
  - C-5b : tests/test_v9_ops.py (8 tests routing)
  - F-3 : tests v9_calibration (15) + v9_replay (18)
  - F-4 : README.md resync (28 règles, 9 couches, 588 tests, 22 scripts)
  - F-5 : docs/STATE.md resync (Phase 9.7+9.8, 588 tests)
  - F-6/F-7/F-8 : CACHE_BOARD, AGENT.md, DOC_REGISTRY.yml resync
  - Règle 28 ajoutée : Hermes = opérateur git unique
  - Total session 2026-07-07 : 14 commits, 588/588 tests verts

## Risques ouverts
- dérive vers des solutions techniques prématurées
- contamination par anciennes mémoires Hermes
- confusion V8 / V9
- multiplicité des docs sans synchronisation
- perte de fil due aux limites de contexte

## Garde-fous
- Git = source de vérité
- STATE.md tenu à jour
- checkpoint à chaque jalon important
- cache board relu à chaque session
- migration par audit, jamais par héritage implicite

## Prochaines actions (post-session 2026-07-06)
1. **Observation live** — ouvrir le marché avec `scripts/v9_market_open.py --market-open`,
   surveiller `--watch signals`/`--watch decisions` sur les nouveaux seuils calibrés.
2. **Recalibration P2** (après n≥50 sessions live) :
   - `REGIME_LOOKBACK_BARS` par TF (dict M5/H1/H4/D1)
   - `SIMILARITY_THRESHOLD` sur données live V9
3. **Levier P3** (non urgent) : `REPLAY_MIN_CAS = 1` temporaire pendant montée en charge live.
4. **Phase 10** : GELÉE — ne pas ouvrir tant que stabilisation live Phase 9 non confirmée.

## HEAD actuel
- Branche : `feat/v9-foundation-clean`
- Dernier commit : voir `git log --oneline -1` (auto-géré par Hermes, règle 28)
- 588 tests, tous verts (règle 7, vérifié 2026-07-07).
- 14 commits livrés dans la session 2026-07-07 (cd9b629 → 77873cd).

## Références pivots
- docs/STATE.md
- docs/CACHE_BOARD.md (ce fichier)
- workspace/perplexity/ACTIVE_TASKS.md
- workspace/perplexity/memory/DECISIONS_LOG.md
- docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md
- docs/deployment/V9_AUTOMATION_RUNBOOK.md
- core/v9/config.py — seuils calibrés
- core/v9/scene_builder.py — _compute_cinematics enrichie
- core/v9/principle_engine.py — _load_shared_context enrichi
- scripts/v9_calibration.py — proxy PLIURE corrigé
