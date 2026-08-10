# 🚀 PowerFlow V10 — Roadmap Cycle 21

> **État snapshot : 2026-08-10 22h55 CEST**
> Base : `feat/v10-c20-healthy` HEAD `aee039c`
> Doctrine : DOCTRINE_PERFORMANCE `673865c`

---

## 📊 Tableau de bord branches

| Branche | HEAD | Tests | Statut |
|---|---|---|---|
| `feat/v10-c20-healthy` | `aee039c` | baseline | 🟢 BASE STABLE |
| `feat/hermes-night` | `204e5de` | **1355 ✅** | ✅ Prêt pour PR |
| `feat/v10-zcode-z789` | `1cae657` | 1342 ✅ | ⚠️ PR #6 ouverte — P0 restant |
| `feat/zcode-night` | `aee039c` | — | 🟡 Vide — Z2/Z4/docs à pusher |

---

## ✅ Livraisons complètes ce soir (2026-08-10)

### Hermes Night — `feat/hermes-night` HEAD `204e5de`

| Task | Fichier | Commit | Statut |
|---|---|---|---|
| H7 | `core/v10/v10_fatman_wave_predictor.py` | `f1e804` | ✅ |
| H7 | `tests/test_v10_fatman_wave_predictor.py` (11 cas) | `f1e804` | ✅ |
| H8 | `scripts/run_replay_quality_gate.py` | `f1e804` | ✅ |
| H8 | `config/quality_gate.json` | `f1e804` | ✅ |
| H9 | `scripts/run_exports_audit.py` | `f1e804` | ✅ |
| H-NEXT | `core/v10/v10_live_pipeline.py` — `detect_pre_wave` branché | `1e696ee` | ✅ |
| H-NEXT | `tests/test_live_pipeline_prewave.py` (9 cas) | `1e696ee` | ✅ |
| **P0** | `core/v10/v10_replay_engine.py` — fix `signal_7_pre_wave` | `c7e2f7a` | ✅ |
| style | ruff import sort + F841 drop | `204e5de` | ✅ |

**Fonctionnalités actives dans `v10_live_pipeline.py` :**
- `detect_pre_wave(sigma_history)` appelé après calcul sigma (source H1)
- COMPRESSION → `signal_score *= 1.15`
- DIVERGENCE → `watch_only = True` (skip trade)
- NEUTRAL → inchangé
- R6 fail-open, R10 compute only
- `pre_wave_phase` tracé dans `DecisionRecord` (R9)

---

### ZCode Z789 — `feat/v10-zcode-z789` HEAD `1cae657` (PR #6)

| Task | Fichier | Commit | Statut |
|---|---|---|---|
| Z7 | `core/v9/arbiter.py` — `source_type` configurable | `28ccb49` | ✅ |
| Z7 | `tests/test_arbiter.py` (3 tests cross-worktree) | `28ccb49` | ✅ |
| Z8 | `scripts/run_coherence_audit.py` | `58cd505` | ✅ |
| Z8 | `reports/coherence_audit_2026_08_10.json` — 0 orphelin, 17 branchés | `58cd505` | ✅ |
| Z9 | `v10_decision_pipeline.py` — VSA multi-TF bonus +0.05/malus -0.03 | `1ff2ee6` | ✅ |
| Z9 | `v10_replay_engine.py` — VSA ctx branché | `1ff2ee6` | ✅ |
| Z9 | `tests/test_v10_decision_pipeline.py` (6 tests VSA) | `1ff2ee6` | ✅ |
| Z10 | `scripts/run_mt4_health.py` + rapport | `7203cf9` | ✅ |
| Z10 | `reports/mt4_health_2026_08_10.json` — port 31685 OK, 6/6 paires | `7203cf9` | ✅ |
| Z11 | `v10_fatman_bible_signals.py` — Signal 7 PRÉ-VAGUE | `f307f00` | ✅ |
| Z11 | `tests/test_v10_fatman_bible_signals.py` (8 tests S7) | `f307f00` | ✅ |

**⚠️ P0 restant sur cette branche :** `get_fatman_signal` import cassé dans `v10_replay_engine.py` — fix disponible sur `feat/hermes-night` commit `c7e2f7a`.

---

## 🚦 Prochaines étapes — Actions prioritaires

### 🔴 PRIORITÉ 1 — Merger PR #6 (ZCode Z789)

```
Condition : cherry-pick commit c7e2f7a de feat/hermes-night sur feat/v10-zcode-z789
            OU accepter que Hermes-night absorbe le fix dans sa propre PR
Action    : merger PR #6 feat/v10-zcode-z789 → feat/v10-c20-healthy
Tests     : 1342 ✅ (P0 fix → 1355+ attendus)
```

### 🔴 PRIORITÉ 2 — Ouvrir PR Hermes-night

```
Branche  : feat/hermes-night → feat/v10-c20-healthy
Tests    : 1355 ✅
Contenu  : H7+H8+H9+H-NEXT+P0 (9 fichiers nouveaux, 3 modifiés)
Action   : ouvrir PR + review + merger
```

### 🟠 PRIORITÉ 3 — Session Hermes H-EXPORTS

```
Branche cible : feat/hermes-night (HEAD 204e5de)
Objectif      : auditer + compléter core/v10/__init__.py

Prompt Hermes :
  1. python scripts/run_exports_audit.py
  2. Pour chaque "ADD_TO_INIT" dans exports_audit.json
     → ajouter export dans __init__.py (R2 additif)
  3. Modules critiques manquants attendus :
     - v10_perplexity_sigma_oracle
     - v10_behavior_rag
     - v10_net_exposure
     - v10_rl_promotion
  4. tests/test_v10_init_exports.py (≥ 5 cas)
  5. ruff check + pytest
  COMMIT sur feat/hermes-night.
```

### 🟡 PRIORITÉ 4 — Grammar audit (dédoublement modules)

```
Constat Z8 : 3 fichiers grammar coexistent sans canonique officiel
  - v10_grammar_v9       : 4 références → CANONIQUE
  - v10_grammar_v9_final : 2 références → DEPRECATE
  - v10_grammar_v9_extra : 1 référence  → DEPRECATE

Action (ZCode ou Hermes) :
  python scripts/audit_grammar_modules.py --apply
  → déplace _final et _extra dans core/v10/_deprecated/
  COMMIT sur feat/v10-c20-healthy directement (opération de nettoyage pure)
```

### 🟡 PRIORITÉ 5 — Push feat/zcode-night (Z2+Z4+docs)

```
Fichiers prêts (Perplexity) :
  - scripts/run_live_health_check.py  (6 couches, score 90%)
  - scripts/audit_grammar_modules.py  (--apply)
  - docs/PARALLEL_BRANCHES.md
  → Push sur feat/zcode-night puis absorber dans PR #6 ou PR séparée
```

### 🟢 PRIORITÉ 6 — Tag c21-healthy

```
Après merge de toutes les PR :
  git tag -a c21-healthy -m "Cycle 21 : Signal7 + VSA multi-TF + pre-wave live"
  Tests cibles : ≥ 1400 pass
  Gate GO LIVE : track record empirique shadow requis (SHADOW→ACTIVE)
```

---

## 🧹 Dette technique résiduelle (pré-existante, hors périmètre c21)

| Module | Problème | Impact | Plan |
|---|---|---|---|
| `v10_currency_strength_legacy.py` | Doublon de `v10_currency_strength.py` | Faible | Audit `__init__.py` + archiver |
| `v10_walk_forward.py` vs `v10_walk_forward_optimizer.py` | 2 fichiers WFA | Moyen | Désigner canonique |
| `test_arbiter.py` 14 échecs | Baseline V9 pré-existant | Nul (isolé) | Non-régression confirmée |
| Signal 7 `direction="NONE"` | Pas encore orienté par le gap live | Moyen | Wire `fatman_scores` live dans H-EXPORTS |

---

## 🔑 Règles de sécurité (invariants)

| Règle | Contenu |
|---|---|
| **R2** | Additif pur — zéro suppression de tests ou de code fonctionnel |
| **R6** | Fail-open — tout import externe enveloppé, pipeline jamais bloqué |
| **R9** | Audit JSON tracçable sur chaque décision |
| **R10** | Compute only — zéro ordre réel sans GO LIVE CEO |
| **R25’** | Gate GO LIVE — SHADOW→ACTIVE conditionné à track record empirique |

---

## 📅 Historique sessions (2026-08-10)

| Heure | Agent | Livraison |
|---|---|---|
| 14h02 | Hermes | WFA M15 + filtre régime HMM (WFA_MARGINAL) |
| 18h49 | Perplexity | H7+H8+H9 push feat/hermes-night |
| 18h58 | ZCode | PR #6 ouverte (Z7-Z11, SHA 1cae657) |
| 20h19 | Hermes | H-NEXT : detect_pre_wave dans v10_live_pipeline |
| 20h23 | Hermes | P0 fix : get_fatman_signal → signal_7_pre_wave |
| 20h25 | Hermes | style : ruff clean — HEAD 204e5de, 1355 tests |
| 22h26 | Perplexity | Review complète PR #6 publiée (3 points d’action) |
| 22h55 | Perplexity | **Ce fichier ROADMAP pushé sur feat/v10-c20-healthy** |
