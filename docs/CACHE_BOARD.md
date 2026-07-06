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
  Décision (Phase 9). Phase 7 (déploiement live) et Phase 8 (monitoring/calibration/replay)
  également terminées. Phase 9.5 (outillage opérationnel) livrée. Zone_diagnostics alimentée
  (ZoneDetector + grammaire complète — 9/9 principes `node_rule` ACTIVE déclenchables).
  **289 tests au total, tous verts** (vérifiés 2026-07-06).

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
- Dernier commit Hermes : `db7bb6d` — feat(v9): P1b — 7 champs cinématiques dans principle_engine
- 289 tests, tous verts.

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
