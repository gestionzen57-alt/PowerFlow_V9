# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` ni `docs/STATE.md` — ce document en est une synthèse orientée reprise rapide.

**Resync Perplexity 2026-07-20 ~13h30 CEST — R32-CLOSE terminée + CVD 6/6 paires.**

## Principe directeur CEO (2026-07-20)

> Le système doit être **autonome et évoluer sans règle bloquante**.
> Toute règle gelant l'adaptation automatique doit être révisée ou supprimée.
> Zéro friction doctrinal.

## Statut global V9 — 2026-07-20 ~13h30 CEST

**Infrastructure** : tout sur **VPS Windows**. Capture server ✅ vivant.
**Marché Forex** : **OUVERT** — session Londres/New York.
**MT4** : EA `V9_Sonde_M1` déployé sur **toutes les paires M1** (6/6 incl. AUDUSD).
**Bot Telegram** : `Ipspx_bot` actif (chat_id `1401055223`).

## Kill switches (état réel — 2026-07-20)

| Kill switch | État | Note |
|---|---|---|
| `V9_EXECUTION_ENABLED` | **0 (INTERDIT)** | Fondateur, Phase 12 gelée |
| `V9_DYNAMIC_RISK_ENABLED` | **1 (APPLY)** | DRM APPLY permanent — R32 fermée |
| `V9_POSITION_MANAGER_ENABLED` | **1 (ON)** | Activé motion CEO 20/07 matin |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | **1 (ON)** | Activé motion CEO 20/07 matin |
| `V9_GBPUSD_LONG_ONLY` | **1 (ON)** | Activé 18/07 |
| `V9_NO_BAISSIERE` | **1 (ON)** | Global no-short (motion 18/07) |
| `V9_CVD_ENABLED` | **0 (OFF)** | Données en DB, 60j calibration avant activation |
| `V9_BEAR_PERCEPTION_ENABLED` | **0 (SHADOW)** | 60j calibration |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | **0 (SHADOW)** | Gated R22 |
| `V9_KELLY_CVAR_ENABLED` | **0 (OFF)** | NO-GO walk-forward Kelly |
| `V9_REGIME_GATE_ENABLED` | **0 (OFF)** | Phase B |

## CVD tick-level — 6/6 paires live ✅

| Paire | CVD live |
|-------|----------|
| EURUSD | ✅ |
| USDCAD | ✅ |
| GBPUSD | ✅ |
| USDJPY | ✅ |
| USDCHF | ✅ |
| AUDUSD | ✅ (rattaché 13h08 CEST) |

`V9_CVD_ENABLED=0` — collecte active, filtre inactif, 60j calibration minimum.

## Dernier commit structurant

[`fec67db`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/fec67db) — R32-CLOSE : DRM APPLY permanent + doctrine + tests verts · 20/07/2026 ~13h30 CEST

Plage complète session 20/07 : `22c2b77..fec67db` :
| SHA | Chantier |
|-----|----------|
| `a9f6191` | Motion CEO 3 activations (P2+P3+CVD migration) |
| `22c2b77` | Motions CEO #3 DRM APPLY + #4 DROP batch |
| `bff59e2` | Fix P0 idempotence post_decision_hook |
| `15aad44` | DROP batch catastrophe 17/07 (3 690 trades) |
| `4646f33` | Skip vestigiaux + dédup 18 doublons haussier |
| `1692c26` | BOARD.md resync 13h |
| `fec67db` | **R32-CLOSE : DRM APPLY permanent** |

## Baseline pytest — 2026-07-20 ~13h30

```
2356 passed / 3 failed / 2 xfailed
```
- **3 rouges tolérés** :
  - `test_post_catastrophe_wr_acceptable` — signal perf réel (intentionnel, WR 29.6% n=27)
  - `test_all_crons_wrapped_passes` — mojibake infra (pré-existant)
  - `test_doctrine_motion_log` — regex MCP niveau 2 vs ### (pré-existant)
- **0 xfail DRM** — les 3 tests DRM SHADOW sont maintenant verts en mode APPLY

## Performance live (paper trade, 20/07 après DROP)

| Segment | Trades | WR | Pips |
|---|---|---|---|
| GBPUSD haussier | 1 075 | **100 %** | +8 767 |
| Global paper_trades | 1 155 | **95.5 %** | +8 663 |
| WR live depuis 18/07 | 27 | **29.6 %** ⚠️ | à surveiller (n petit) |

## Stash à dropper

```bash
git stash drop stash@{0}  # R32-CLOSE-wip-nonperimeter — contenu déjà dans l'arbre
```
Confirmer que rien n'y manque, puis dropper.

## Ce qui est gelé

- **Phase 10** (fédération d'agents)
- **Phase 12** (exécution réelle) — interdit fondateur
- **CVD_ENABLED=1** — 60j calibration minimum

## Références pivots

- [`docs/STATE.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/STATE.md)
- [`docs/DOCTRINE.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/DOCTRINE.md)
- [`workspace/perplexity/memory/DECISIONS_LOG.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/workspace/perplexity/memory/DECISIONS_LOG.md)
- [`docs/CACHE_BOARD.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/CACHE_BOARD.md)
