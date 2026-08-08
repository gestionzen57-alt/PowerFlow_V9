# DEBT_TRACKER — PowerFlow V10
**Registre des dettes techniques actives**  
**Mis à jour :** 2026-08-07 15:30 CEST (post-Sprint 23)

> Toute dette doit avoir un propriétaire et une date cible.  
> Statuts : 🔴 Critique · 🟡 Modéré · 🟢 Mineur · ✅ Résolue

---

## Dettes actives

| ID | Sévérité | Description | Propriétaire | Date cible | Statut |
|---|---|---|---|---|---|---|
| D01 | 🔴 | 15 tests V9 rouges (pré-existants, V9 verrouillé) | Søn (mandat requis) | TBD | 🔴 Open |
| D10 | 🔴 | **Watchdog ANOMALIE** — absurd_pnl + jpy_pip_factor sur USDJPY (pips > max_plausible) | Zcode | 2026-08-08 | 🔴 Open |
| D02 | 🟡 | ~~`V9_EXECUTION_ENABLED=1` résidu dans `config/v9_kill_switches.env`~~ | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (M1) |
| D03 | 🟡 | ~~`docs/V10/CACHE_BOARD.md` obsolète (692 tests, HEAD 40ed93a)~~ | Hermes | 2026-08-07 | ✅ **RÉSOLUE** (M3) |
| D04 | 🟡 | `V10_QUANT_UPGRADE_SPRINT23.md` — sprint 23 non commencé | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (Sprint 23 complete) |
| D05 | 🟢 | Plusieurs docs/checkpoint_*.md dupliqués sans consolidation | Perplexity | Session actuelle | 🟢 Open |
| D06 | 🟢 | `dashboard_live.html` et `dashboard_v10_ceo.html` — ~~pas reliés à la vraie DB~~ | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (M2) |
| D07 | 🟢 | filter_compositor non câblé orchestrateur | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (S23-A) |
| D08 | 🟢 | SL/TP statiques (vol_forecast non intégré) | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (S23-B) |
| D09 | 🟢 | Endpoint backtest absent dashboard | Zcode | 2026-08-07 | ✅ **RÉSOLUE** (S23-C) |

---

## Dettes résolues

| ID | Description | Résolution | Date |
|---|---|---|---|
| R01 | Safe Haven flip inversé `v10_currency_strength` | commit `885a851` fix signe | 2026-08-05 |
| R02 | Doublon `v10_strategy_layers` / `v10_filter_compositor` | Wrapper réécrit | 2026-08 |
| R03 | `core/v10/__init__.py` 27 noms non résolus dans `__all__` | Réparé exhaustivement | 2026-08 |
| R04 | Stale gate dans boucles live (audit R9) | Réparé sprint R9 | 2026-08 |
| R05 | **D02 — V9_EXECUTION_ENABLED=1 résidu** | Commit M1 — commenté dans config | 2026-08-07 |
| R06 | **D03 — CACHE_BOARD.md obsolète** | Commit M3 — régénéré avec pytest + HEAD | 2026-08-07 |
| R07 | **D06 — Dashboards non reliés DB** | Commit M2 — FastAPI + JS live injection | 2026-08-07 |
| R08 | **D07 — filter_compositor non câblé** | Commit S23-A — câblé inconditionnel | 2026-08-07 |
| R09 | **D08 — SL/TP statiques** | Commit S23-B — vol_forecast GARCH/EWMA | 2026-08-07 |
| R10 | **D09 — Endpoint backtest absent** | Commit S23-C — /api/v1/backtest/summary | 2026-08-07 |

---

## Règle de gestion

1. Toute nouvelle dette détectée → ajout immédiat ici avec ID séquentiel
2. Toute résolution → déplacer en section "Résolues" avec commit de référence
3. Aucune dette D01/D02 ne peut être marquée ✅ sans commit vérifié
4. CEO review dettes 🔴 à chaque checkpoint session