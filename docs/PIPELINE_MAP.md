# PIPELINE_MAP.md — Vue 1-Page Pipeline V10

> **Mise à jour** : 07/08/2026 — Architect pass  
> **Usage** : Démarrage rapide de session. Tout est ici.

---

## Pipeline Complet — ASCII

```
╔══════════════════════════════════════════════════════════════════╗
║  INPUT : symbol, pair, timestamp, timeframe, bars (OHLCV)       ║
║          + news_events, usd_trend, db_path                      ║
╚══════════════════╤═══════════════════════════════════════════════╝
                   │
        ┌──────────▼──────────┐
        │  FATMAN DB READER   │  v10_fatman_db_reader.py
        │  Source : v9_forces │  R6: fallback si DB stale
        │  base_rank/quote_rk │  R9: log source label
        └──────────┬──────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼────┐  ┌─────▼─────┐  ┌───▼────┐
│  FORCE  │  │ STRUCTURE │  │CONTEXT │
│ F1-F8   │  │ S7-S8 BOS │  │C1-C7   │
│ w=0.30  │  │ w=0.25    │  │w=0.20  │
└────┬────┘  └─────┬─────┘  └───┬────┘
     └─────────────┼─────────────┘
                   │
        ┌──────────▼──────────┐
        │    VSA + CURRENCY   │  v10_vsa.py (w=0.10)
        │    STRENGTH + CONF  │  v10_currency_strength.py (w=0.08)
        │                     │  v10_confluence.py (w=0.07)
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │   SIGNAL SCORER     │  v10_signal_scorer.py
        │   composite_score   │  EnhancedSignal
        │   → A1/A2/A3/NONE   │  + CoT R5
        └──────────┬──────────┘
                   │
   ╔═══════════════▼════════════════╗
   ║  GATES PROGRESSIFS (COUCHE 5)  ║
   ╠════════════════════════════════╣
   ║  G1 Context Global             ║  market_context_global
   ║  G2 Behavior (R10 capital)     ║  currency_behavior
   ║  G3 Currency Strength          ║  bias < min_bias
   ║  G4 Fatboy Gate (P1/P2/P3)     ║  fatman_bible_signals
   ║  G5 Sigma Oracle               ║  perplexity_sigma_oracle
   ║  G6 Public Filters             ║  filter_compositor
   ║     (ICT OTE + SMC + Session)  ║
   ╚═══════════════╤════════════════╝
                   │
        ┌──────────▼──────────┐
        │  ContextFilteredSig │  final_level A1/A2/A3/NONE
        │  + downgrade_reason │  + blockers[]
        │  + cot dict complet │  + context.tradeable_pairs
        └──────────┬──────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼────┐  ┌─────▼─────┐  ┌───▼─────┐
│SCANNER  │  │  ALERT    │  │  RL     │
│behavior │  │DISPATCHER │  │ADAPTER  │
│ (Søn)   │  │Telegram   │  │(Phase H)│
└─────────┘  └───────────┘  └─────────┘
```

---

## Latences Cibles

| Module | Latence cible | Latence max R6 |
|--------|--------------|----------------|
| Fatman DB read | < 10ms | 50ms → fallback |
| Force + Structure + Context | < 30ms | 100ms → score 0.5 |
| VSA + Currency Str + Confluence | < 20ms | 80ms → skip additif |
| Signal Scorer | < 5ms | 20ms |
| Gates G1-G6 | < 15ms | 50ms → fail-open |
| **Total pipeline** | **< 80ms** | **300ms** |

---

## Fail-Open R6 — Comportement par Module

| Module | Si indisponible | Score retourné | Log R9 |
|--------|----------------|----------------|--------|
| Fatman DB | stale > 1h | fallback v10_currency_strength | `fatman_source=stale_fallback` |
| Force | exception | force_level=MEDIUM, score=0.50 | `force:exception` |
| Structure | exception | structure_type=NONE | `structure:exception` |
| Context | news indispo | c2_news_state=CLEAR (prudent) | `context:news_unavailable` |
| VSA | exception | vsa_state=NEUTRAL, 0 impact | `vsa:R6_skip` |
| Currency Strength | None | aucun impact (skip) | `cs:R6_skip` |
| Confluence | None | aucun impact (skip) | `conf:R6_skip` |
| Fatboy Gate | exception | skip complet (pas de downgrade) | `fatboy:R6_pass` |
| Sigma Oracle | exception | garde niveau actuel | `sigma:R6_keep` |
| Public Filters | None | aucun impact (backward compat) | `filters:R6_skip` |

---

## Commandes Rituel Vérification Session

```bash
# 1. Vérifier DB fraîche (< 15min)
sqlite3 data/v9_forces.db \
  "SELECT symbol, timeframe, bar_time FROM forces_snapshots \
   ORDER BY bar_time DESC LIMIT 5;"

# 2. Lancer tests rapides (smoke test)
pytest tests/unit/test_orchestrator.py -x -q

# 3. Vérifier pipeline complet sur 1 signal
python -c "
from core.v10.v10_orchestrator import compose_signal_with_context
print('Pipeline OK')
"

# 4. Vérifier alertes Telegram
python scripts/test_telegram_alert.py
```

---

## Checklist Démarrage Sprint

```
□ SOUL.md lu (§1 doctrine, §4 logique fusion)
□ STATE.md lu (sprint en cours, bloquants)
□ DB v9_forces.db fraîche (< 15min)
□ Branche : feat/v9-foundation-clean
□ pytest smoke test vert
□ DECISIONS_LOG.md à jour avant toute modif
```

---

*Liens* : [SOUL.md](./SOUL.md) | [LEVIER_HUB.md](./LEVIER_HUB.md) | [STATE.md](./STATE.md)
