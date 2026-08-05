# V10 CURRENCY STRENGTH — SPEC (Phase 23, section 7 checkpoint Perplexity)

**Source** : `workspace/perplexity/CHECKPOINT_V10_EDGE_FUND_20260805.md` §7
**HEAD au moment de la spec** : `40ed93a` (692 tests)
**HEAD réel à l'implémentation** : `a5e1871` (778 tests)
**Implémentation** : ZCode 2026-08-05 · **812/812 tests verts**

---

## 1. Gap réel identifié (R9 honnête)

Le prompt supposait `v10_currency_strength.py` absent. En réalité le
moteur EXISTE (Phase 1, commit `b1c3b98`, 16 tests) :
`compute_currency_strength()` — moteur Fatman Hawkeye (EMA 8/34
ATR-normalisé, percentile rank 50, 7 devises).

**Le vrai gap = l'API d'intégration orchestrateur** (4 fonctions
manquantes, confirmé par introspection) + le filtre pre-signal.

## 2. API livrée — `V10CurrencyStrength`

| Fonction | Signature | Comportement |
|---|---|---|
| `compute_scores` | `(tf="", lookback=20) → dict[devise, float]` | Scores normalisés [0,1] min-max. R6 : pas de données → 0.5 neutre |
| `get_pair_bias` | `(base, quote, tf="") → float [-1,+1]` | Score différentiel base - quote. Positif = haussier base/quote. R6 : devise inconnue → neutre |
| `get_fatman_tf` | `(trading_tf) → str` | Mapping : M1/M5→M15, M15→M30, M30→H1, H1→H4, H4→D1, D1→D1. Inconnu → H1 |
| `is_aligned` | `(pair, trading_tf, min_score=None) → bool` | `|bias| >= min_score (0.15)` ET TF Fatman ≠ TF trading (confirmation supérieure) |

**Fix R9 (découvert à l'implémentation)** : `min_signal_span=10.0` —
plage de scores < 10 → normalisation neutre (évite d'amplifier le
bruit en ±1.0, ex : scores 50.0 vs 50.1 → bias ±1.0 faux).

**Bonus** : `compute_scores_from_db(db_path, tf)` — charge les barres
réelles (forces_snapshots via v10_currency_behavior) → moteur → scores.

## 3. Filtre orchestrateur (MISSION 3)

Point d'intégration : `compose_signal_with_context()` (le
`_evaluate_signal()` du prompt n'existe plus).

Paramètre : `currency_strength: Optional[V10CurrencyStrength] = None`
(R6 fail-open : None → aucun impact).

| Condition | Action |
|---|---|
| `|bias| < min_bias (0.10)` | Downgrade A1→A2→A3→NONE + blocker `CURRENCY_STRENGTH_WEAK` |
| `is_aligned(pair, tf)` | Bonus `composite_score +0.08` (cap 1.0) |
| toujours | CoT R5 `3_currency_strength` : bias, fatman_tf, aligned |

## 4. Tests

- `tests/test_v10_currency_strength_api.py` : **30 tests** (spec exigeait 20)
  - normalisation [0,1] toutes devises, extrêmes, fail-open vide,
    scores égaux → neutre, scores dict
  - mapping TF : 7 cas + inconnu → H1 + map complète
  - bias : EURUSD positif, USD-CAD, devise inconnue neutre, vide → 0
  - is_aligned : seuil atteint/non, paire invalide, TF sans Fatman,
    seuil par défaut
  - overrides R8 (align_min_score), API_DEFAULTS présents
  - perf < 10ms/appel, DB réelle, DB absente fail-open, JSON R9,
    ré-export module
- `tests/test_v10_orchestrator_step7.py` : **+4 tests** (fail-open,
  weak downgrade, aligned bonus, signature optionnelle)

## 5. Doctrine

R2 additif pur ✅ (moteur existant non modifié, filtre kw-only) ·
R6 fail-open ✅ (4 cas) · R7 ✅ 812/812 · R8 overrides réversibles ✅ ·
R9 audit CoT ✅ · R10 0 ordre réel ✅ (V9_EXECUTION_ENABLED=0)

## 6. Prochaines étapes (checkpoint §4-5)

- Phase B : MQL5 pur (EA natif) — quand le bridge live MT5 sera validé
- Phase C : intégration orchestrateur complète (déjà branchée ici)
- Validation : WR avant/après filtre sur les 6 paires (dataset frais
  v10_signals_clean, Levier 2)
