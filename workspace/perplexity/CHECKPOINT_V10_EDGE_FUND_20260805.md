# CHECKPOINT V10 — PowerFlow Edge Fund Quantique
## 05/08/2026 — 10h49 CEST | Branch: feat/v9-foundation-clean | HEAD: 40ed93a

---

## 1. ÉTAT RÉEL DU SYSTÈME (Source: Git + DB)

### Tests & Infrastructure
| Métrique | Valeur |
|---|---|
| HEAD commit | `40ed93a` feat(v10): edge fund phase 31 — RL Promotion Gate |
| Tests V10 verts | **692 / 692** |
| Phases V10 livrées | **22** |
| DB size | 6.40 GB |
| V10 signals clean | **8 669** |
| Forces snapshots | **252 384** |
| Decisions | **109 161** |

### Timeframes (après intégration M30 — Phase 22)
| TF | Statut | Horizon signal | Gate WR |
|---|---|---|---|
| M1 | ✅ Collecte live | — | — |
| M5 | ✅ Intégré | — | — |
| M15 | ✅ Intégré | — | — |
| **M30** | ✅ **Intégré Phase 22** | 3 barres | ≥45% |
| H1 | ✅ Intégré | 2 barres | ≥45% |
| H4 | ✅ Intégré | 1 barre | ≥45% |

### Gate WR M30 (Phase 22 — résultat)
| Paire | WR M30 | Gate |
|---|---|---|
| AUDUSD | 50.30% | ✅ PASS |
| GBPUSD | 48.11% | ✅ PASS |
| USDCAD | 50.00% | ✅ PASS |
| USDCHF | 45.28% | ✅ PASS |
| EURUSD | <45% | ⏳ Recalibration |
| USDJPY | <45% | ⏳ Recalibration |

### Comparatif V9 → V10 (ΔWR)
| Paire | ΔWR | Signal |
|---|---|---|
| USDCHF | +28.5 pts | ⭐ Majeur |
| USDCAD | +29.7 pts | ⭐ Majeur |

---

## 2. ARCHITECTURE V10 MODULES LIVRÉS

### Cœur cognitif (feat/v9-foundation-clean)
| Module | Fichier | Phases | Statut |
|---|---|---|---|
| Force scoring (F1-F5) | `core/v10/v10_force.py` | 14-15 | ✅ |
| Structure (S1-S9) | `core/v10/v10_structure.py` | 14-15 | ✅ |
| Context (C1-C7) | `core/v10/v10_context.py` | 14-15 | ✅ |
| Orchestrateur A1/A2/A3 | `core/v10/v10_orchestrator.py` | 14-15 | ✅ |
| Market Context Global | `v10_market_context_global.py` | 16 | ✅ |
| Bayesian Recalibrator | `v10_bayesian_recalibrator.py` | 17+21 | ✅ |
| RL Adapter (Thompson Bandit) | `v10_rl_adapter.py` | 18 | ✅ SHADOW |
| Signal Generator Live | `v10_signal_generator_live.py` | 19-20 | ✅ |
| M30 Integration | `v10_market_context_global.py` + orchestrator | 22 | ✅ |
| RL Promotion Gate | Phase 31 | `40ed93a` | ✅ |

### Kill switches actifs V10
| Switch | État |
|---|---|
| `V9_EXECUTION_ENABLED` | **0** — fondateur gelé |
| `V9_DYNAMIC_RISK_ENABLED` | **1** APPLY |
| `V9_SHADOW_MODE_ENABLED` | **1** |
| RL Adapter | **SHADOW** — kill si DD>5% |

---

## 3. COMPRÉHENSION FATMAN — CE QUI A CHANGÉ

### Logique reverse-engineerée
Le Fatman calcule un **score de force relatif par devise** (8 devises majeures) sur une
fenêtre glissante multi-TF. La lecture se fait toujours sur le TF Fatman **supérieur** au TF
de trading :

| TF Trading | TF Fatman de référence |
|---|---|
| M1 / M5 | M15 |
| M15 | M30 |
| **M30** | **H1** |
| H1 | H4 |
| H4 | D1 |

### Ce que V9 ratait
1. Calcul force devise **mono-TF** → signal plat sans direction claire
2. Pas de scoring **cross-devise** (EUR vs USD isolément, pas EUR/USD relatif)
3. Absence **M30** dans le pipeline de contexte → gap sur la lecture Fatman M15→H1
4. VSA ignoré comme confirmation d'intention institutionnelle
5. Seuil signal **binaire** (0/1) au lieu d'un **score continu** pondéré par confluence

### Ce que V10 corrige (acquis)
- Scoring F1-F5 multi-devises avec fenêtre adaptative
- M30 intégré Phase 22 : bonus solidarity +0.15 si M30+H1 bias alignés
- Signal A1/A2/A3 avec score de confiance continu
- Bayesian Recalibrator grid 4D par (paire, TF)

---

## 4. GAPS RESTANTS (Priorités ordonnées)

| # | Gap | Impact | Effort |
|---|---|---|---|
| **G1** | `v10_currency_strength.py` — scoring devise pur Fatman | BLOQUANT | M |
| **G2** | Traduction logique Fatman → MQL5 sans DLL | Haut | M |
| **G3** | Filtre force devises câblé dans orchestrateur V10 | Haut | S |
| **G4** | VSA institutionnel dans le scoring de contexte | Moyen | M |
| **G5** | Zone diagnostics (zone_diagnostics module) | Moyen | M |
| **G6** | Backtests OOS M30 sur EURUSD/USDJPY (gate <45%) | Moyen | S |

---

## 5. PLAN ACTION — EDGE FUND QUANTIQUE (Séquence Hermes/ZCode)

### Phase A — Currency Strength Core (J1-J3)
**Objectif** : `v10_currency_strength.py` — reproduction algorithmique du calcul Fatman

```python
# Spec interface attendue
class V10CurrencyStrength:
    def compute_scores(self, tf: str, lookback: int) -> dict[str, float]:
        # Retourne {USD: 0.82, EUR: 0.34, GBP: 0.71, ...} normalisés [0,1]
        ...

    def get_pair_bias(self, base: str, quote: str, tf: str) -> float:
        # Score différentiel base - quote → direction signal
        ...

    def get_fatman_tf(self, trading_tf: str) -> str:
        # Mapping TF trading → TF Fatman de référence
        mapping = {
            "M1": "M15", "M5": "M15",
            "M15": "M30", "M30": "H1",
            "H1": "H4", "H4": "D1"
        }
        return mapping[trading_tf]
```

**Tests minimum** : 20 tests (calcul score, normalisation, mapping TF, edge cases)

### Phase B — MQL5 Pure (J4-J6)
**Objectif** : Indicateur Fatman-compatible en MQL5 pur (zéro DLL)

- Sources de données : `iCustom()` et buffers natifs MT5
- Architecture : `OnCalculate()` → calcul score 8 devises → buffer principal + 8 buffers devises
- Paires source : EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, EURGBP

### Phase C — Intégration Orchestrateur (J7-J8)
**Objectif** : Currency strength score câblé dans `v10_orchestrator.py`

- Filtre pre-signal : si score différentiel < seuil → signal bloqué
- Bonus confluence : si Fatman TF supérieur confirme → +0.10 confiance

### Phase D — ZCode Roadmap Update (J9)
**Objectif** : Roadmap mise à jour + docs pushés Git

---

## 6. MATRICE SIGNAUX EDGE FUND (V10 cible)

| Setup | TF | Levier | WR cible | R:R | Fréquence |
|---|---|---|---|---|---|
| A1 — Confluence totale | H1/H4 | ×50 | 62% | 1:2.5 | 2-3/semaine |
| A2 — Force + Structure | M30/H1 | ×30 | 55% | 1:2 | 5-7/semaine |
| A3 — Momentum | M15/M30 | ×20 | 48% | 1:1.5 | 10-15/semaine |
| VSA Institutionnel | H1 | ×40 | 60% | 1:3 | 1-2/semaine |
| Fatman Divergence | M30 | ×25 | 52% | 1:2 | 3-5/semaine |
| RL Promoted | H4 | ×50 | 65% | 1:3 | 1/semaine |

---

## 7. PROMPT ZCODE — IMPLÉMENTATION V10 CURRENCY STRENGTH

```
MANDAT HERMES V10 — CURRENCY STRENGTH FATMAN INTEGRATION
Mode : AUTOPILOT NO-LIMIT | Doctrine : R2 additif pur | Gate : 20 tests verts minimum

CONTEXTE RÉEL (état Git 05/08/2026) :
- Branch : feat/v9-foundation-clean | HEAD : 40ed93a
- 692/692 tests verts | 22 phases V10 livrées
- M30 intégré Phase 22 — mapping TF complet M1/M5/M15/M30/H1/H4
- Gap critique : v10_currency_strength.py absent → scoring devise incomplet

MISSION 1 — Créer core/v10/v10_currency_strength.py
Implémenter la classe V10CurrencyStrength avec :
1. compute_scores(tf, lookback=20) → dict[devise, float] normalisé [0,1]
   - 8 devises : USD, EUR, GBP, JPY, CAD, AUD, CHF, NZD
   - Calcul : moyenne pondérée des forces relatives sur toutes les paires
     où la devise apparaît (ex: USD apparaît dans EURUSD, GBPUSD, USDJPY...)
   - Source data : DB forces_snapshots (table existante, 252 384 rows)
2. get_pair_bias(base, quote, tf) → float [-1, +1]
   - Score différentiel = score(base) - score(quote)
   - Positif = bias haussier base/quote
3. get_fatman_tf(trading_tf) → str
   - Mapping : M1/M5→M15, M15→M30, M30→H1, H1→H4, H4→D1
4. is_aligned(pair, trading_tf, min_score=0.15) → bool
   - True si |get_pair_bias| >= min_score ET Fatman TF supérieur confirme

MISSION 2 — Créer tests/test_v10_currency_strength.py
20 tests minimum couvrant :
- Normalisation [0,1] sur toutes les devises
- Mapping TF correct (6 cas)
- Bias EURUSD : si EUR > USD → positif
- Edge case : données absentes → score 0.5 (neutre, pas crash)
- Performance : compute_scores < 100ms sur 252K rows

MISSION 3 — Câbler dans v10_orchestrator.py
Filtre pre-signal dans _evaluate_signal() :
  cs = V10CurrencyStrength()
  bias = cs.get_pair_bias(base, quote, trading_tf)
  if abs(bias) < 0.10:
      return Signal(type="NONE", reason="currency_strength_weak")
  signal.confidence += 0.08 if cs.is_aligned(pair, tf) else 0

MISSION 4 — Mettre à jour docs/STATE.md
Ajouter section "Phase 23 — Currency Strength Fatman" avec :
- Commits produits
- Tests passés
- Gate WR avant/après sur les 6 paires

RÈGLES DOCTRINE (inviolables) :
- R2 : additif pur — AUCUNE modification des modules existants sans test isolé
- R8 : backup avant toute migration DB
- R10 : DD max 10%, kill switch si dépassé
- 20 tests verts AVANT push
- V9_EXECUTION_ENABLED reste 0

GO — Commence par MISSION 1, présente le fichier complet avant MISSION 2.
```

---

## 8. DOCUMENTS À METTRE À JOUR (post-implémentation)

| Document | Action | Responsable |
|---|---|---|
| `docs/STATE.md` | Ajouter Phase 23 | ZCode/Hermes |
| `docs/ROADMAP.md` | Currency Strength → DONE, MQL5 → IN PROGRESS | ZCode/Hermes |
| `workspace/perplexity/BOARD.md` | Resync HEAD + tests | Perplexity |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Décision G1 intégration Fatman | Perplexity |
| `docs/V10/V10_CURRENCY_STRENGTH_SPEC.md` | Créer spec complète | ZCode/Hermes |

---

## 9. VISION — CE QUE DEVIENT V10 AVEC LE PIPELINE COMPLET

Quand `v10_currency_strength.py` est livré et câblé :

1. **Signal A1 amélioré** : Force devise (Fatman) + Structure (BOS/CHoCH) + Context (VSA) = confluence 3 couches → WR cible 62%+
2. **Filtre institutionnel** : Seuls les signaux dans le sens du flux de force devise passent → réduction du bruit estimée -35%
3. **M30 pleinement exploité** : Le bonus solidarity Phase 22 (+0.15) devient pertinent car basé sur un score Fatman réel
4. **MQL5 autonome** : L'indicateur MT5 calcule les scores en temps réel sur les charts → dashboard visuel aligné avec le moteur Python
5. **Edge fund quantique** : 6 setups documentés, WR backtest ≥55% sur 4/6 paires, R:R moyen 1:2, fréquence 15-25 signaux/semaine

---

*Checkpoint généré par Perplexity — 05/08/2026 10h49 CEST*
*Source de vérité : Git feat/v9-foundation-clean HEAD 40ed93a | 692/692 tests*
