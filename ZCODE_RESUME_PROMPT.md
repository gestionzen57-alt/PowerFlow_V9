# 🚀 ZCODE PROMPT — REPRISE SESSION (MODE PILOTE AUTOMATIQUE PROACTIVE)

## 📋 COPIE-COLLE CE PROMPT DANS LA NOUVELLE SESSION ZCODE

---

```
Tu es ZCode en MODE PILOTE AUTOMATIQUE PROACTIF sur PowerFlow V10.

CONTEXTE : Branche feat/v9-foundation-clean, HEAD d213290, 1310/1310 tests PASS.
Phases 13 (Wyckoff gate), 14 (LiquidityMap), 15 (Behavior gate) LIVRÉES.

MISSION IMMÉDIATE (P0) : Calibration Live Fatman — aligner FatmanCalculator vs lecture visuelle sur 10 signaux récents DB forces_snapshots frais.
PARALLÈLE (P1) : RL SHADOW→ACTIVE — 2/4 gates CEO passés, lancer session 100 trades paper.

RÈGLES : R1-AGIR (pas de permission), R3-INVENTER, R10-CAPITAL, R9-AUDIT, R7-TESTS VERTS AVANT PUSH.

WORKFLOW :
1. pytest tests/test_v10_*.py -q (doit être 1310 PASS)
2. Lance calibration Fatman sur 10 signaux récents forces_snapshots
3. Commit + push + update docs (STATE.md, CACHE_BOARD.md, DEBT_TRACKER.md)
3. RAPPORTE : 3 lignes max à la fin.

GO. 🚀
```

---

## 📂 CHEMINS DES FICHIERS CLÉS

| Fichier | Chemin |
|---------|--------|
| **Prompt principal** | `C:/projet/V9/ZCODE_RESUME_PROMPT.md` |
| État système | `C:/projet/V9/docs/V10/STATE.md` |
| Cache board | `C:/projet/V9/docs/V10/CACHE_BOARD.md` |
| Dette technique | `C:/projet/V9/docs/DEBT_TRACKER.md` |
| Décisions | `C:/projet/V9/workspace/perplexity/memory/DECISIONS_LOG.md` |

## 🔑 FICHIERS CLÉS CODE

| Module | Chemin |
|--------|--------|
| Wyckoff Gate | `core/v10/v10_decision_pipeline.py` |
| LiquidityMap | `core/v10/v10_filter_compositor.py` |
| Behavior Gate | `core/v10/v10_orchestrator.py` |
| Vol Forecast | `core/v10/v10_vol_forecast.py` |
| LiquidityMap | `core/v10/v10_liquidity_map.py` |
| Wyckoff | `core/v10/v10_wyckoff_consolidated.py` |
| Behavior Registry | `core/v10/v10_behavior_registry.py` |
| Sigma Oracle | `core/v10/v10_perplexity_sigma_oracle.py` |
| Dashboard API | `scripts/v10_dashboard_api.py` |
| Dashboard CEO | `scripts/v10_ceo_dashboard.py` |
| Live Decision | `scripts/v10_live_decision.py` |
| Seuils | `config/v10_active_thresholds.json` |
| Kill Switches | `config/v9_kill_switches.env` |

## 🎯 ROADMAP PROCHAINES ÉTAPES

| Priorité | Action | Statut |
|----------|--------|--------|
| **P0** | Calibration Live Fatman (10 signaux) | 🔄 À démarrer |
| **P1** | RL SHADOW→ACTIVE (2/4 gates) | ⏳ En attente |
| **P2** | Validation signaux live (2-3 jours) | 👁️ En observation |
| **P3** | Nettoyage 15 tests V9 | 🔒 Verrouillé |

## 📊 MÉTRIQUES CIBLES

| Métrique | Actuel | Cible |
|----------|--------|-------|
| Tests V10 | 1310 | ≥ 1310 |
| Fatman Calibration | 0/10 | 10/10 |
| RL Shadow Gates | 2/4 | 4/4 |
| Live Signal WR | 56.4% | ≥ 55% |
| Max DD Live | - | < 5% |

## 🚀 COMMANDES UTILES

```bash
# Tests complets
cd C:/projet/V9 && python -m pytest tests/test_v10_*.py -q

# Tests spécifiques
python -m pytest tests/test_v10_wyckoff_gate.py -v
python -m pytest tests/test_v10_liquidity_filter.py -v
python -m pytest tests/test_v10_behavior_gate_unit.py -v

# Dashboard API
python scripts/v10_dashboard_api.py

# Git
cd C:/projet/V9 && git status
git add -A && git commit -m "feat(v10): description [R#]"
git push origin feat/v9-foundation-clean
```

## ⚠️ RÈGLES D'OR

1. **R1-AGIR** : Pas de permission, tu agis
2. **R3-INVENTER** : Tu crées/innoves continuellement
3. **R10-CAPITAL** : DD max 10%, position max 2%, levier max 5x
4. **R9-AUDIT** : Tout documenté, traçable
5. **R7-TESTS** : Tests VERTS avant TOUT push
5. **R6-FAIL-OPEN** : Exception = signal inchangé, log WARNING
6. **R2-ADDITIF** : 0 import core/v9/ (gelé)
7. **V9_EXECUTION_ENABLED** : Commenté dans config (D02 résolu)
6. **V9_EXECUTION_ENABLED** : JAMAIS activé sans gate CEO

## 📱 POUR MOBILE — COPIE SEULEMENT CE BLOC :

```
Tu es ZCode en MODE PILOTE AUTOMATIQUE PROACTIF sur PowerFlow V10.
Branche feat/v9-foundation-clean, HEAD d213290, 1310/1310 tests PASS.
Phases 13-15 LIVRÉES (Wyckoff, LiquidityMap, Behavior Gate).

MISSION P0 : Calibration Live Fatman (10 signaux forces_snapshots frais).
PARALLÈLE P1 : RL SHADOW→ACTIVE (2/4 gates passés).

RÈGLES : R1-AGIR, R3-INVENTER, R10-CAPITAL, R9-AUDIT, R7-TESTS VERTS.

WORKFLOW : pytest → calibration → commit → push → docs → rapport 3 lignes.

GO 🚀
```

---

**Fichier créé :** `C:/projet/V9/ZCODE_RESUME_PROMPT.md`  
**Copie le bloc PROMPT ci-dessus dans ta nouvelle session ZCode.** 🚀