# V10 CACHE_BOARD — Cache opérationnel live

**Dernière mise à jour** : 2026-08-04 (~22:00 UTC)

---

## 📦 Snapshot live — Currency Strength Engine (Phase 1)

| Champ | Valeur |
|---|---|
| Source | DB v9_forces.db / forces_snapshots |
| TF | H1 (extensible M1/M5/M15/M30/H4/D1) |
| Paires trackées | 6/6 (EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD) |
| Devises trackées | 7/7 (EUR, GBP, USD, JPY, CHF, AUD, CAD) |
| Last timestamp | 2026-08-04T20:00:02Z |
| n_bars used | 600 (100 par pair × 6 paires) |
| Insufficient | 0 |
| Spread Fatman | 90.00 (large — divergence cross-pair visible) |

### Top / Bottom
- **Strongest** : GBP (rank 1) + JPY (rank 2) → momentum haussier sur snapshot
- **Weakest** : CAD (rank 7) — momentum baissier visible

### À étalonner en Phase 2 (VSA) + Phase 7 (Macro)
- Fenêtre `history` actuellement synthétique (proxy)
- Percentile rank se calibre sur moments EMA des 50 bougies précédentes
- Phase 6 MT5 Bridge livrera les vrais ticks pour recalculer proprement

---

## ⏳ Pipeline V10 — état

```
[1] Currency Strength ✅ Phase 1 LIVRÉE
[2] VSA Engine            🔴 P1 (prochain chantier)
[3] Extreme Detector      ⏸️
[4] Multi-TF Confluence   ⏸️
[5] Signal Orchestrator   ⏸️
[6] MT5 Bridge Tickmill   ⏸️
[7] Macro Filter          ⏸️
[8] Scalp Engine M1       ⏸️

Cœur cognitif V10 (Phase E-F) : ✅ Running, signal-only, 54/54 verts
DB v9_forces.db : ✅ 6.4 GB, 27 tables
capture_server : ✅ PID live (port 31685)
```

---

## 📈 Dernier test live (CLI Phase 1)

```bash
$ python scripts/v10_currency_strength_demo.py --tf H1
=== Currency Strength V10 :: TF=H1 :: 2026-08-04T20:00:02Z ===
Source       : DB v9_forces.db
Paires       : 6/6 USD
Insufficient : 0
n_bars_used  : 600
---
DEVISE     SCORE   VELOCITY  RANK  BAR
GBP        95.00   +78.6037     1  |██████████████████████████████| ◀ TOP
JPY        95.00  +213.3780     2  |██████████████████████████████|
EUR         5.00  -186.1021     3  |······························|
USD         5.00   -18.9002     4  |······························|
CHF         5.00   -52.4666     5  |······························|
AUD         5.00  -105.3945     6  |······························|
CAD         5.00   -36.7693     7  |······························| ◀ BOT
---
Strongest    : GBP | Weakest: CAD | Spread: 90.00
Audit        : seed=42 | invert_sign=True
[STATS] DB-snapshots=1 | fixture-snapshots=0
```

---

## 🔗 Pointeurs

- `scripts/v10_currency_strength_demo.py` — CLI
- `core/v10/v10_currency_strength.py` — moteur
- `core/v10/v10_currency_pairs.py` — mapping paires/devises
- Tests : `tests/test_v10_currency_pairs.py` (4) + `tests/test_v10_currency_strength.py` (12)
- Plan : `docs/V10/V10_PLAN_EDGE_FUND_QUANTIQUE.md` §4 PHASE 1
