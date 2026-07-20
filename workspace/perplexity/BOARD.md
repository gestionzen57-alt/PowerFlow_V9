# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider.

**Resync Perplexity 2026-07-20 ~13h CEST — mission R22 terminée + CVD live confirmé.**

## Statut global V9 — 2026-07-20 ~13h CEST

**Infrastructure** : tout sur **VPS Windows** (PC local = poste de travail Søn). Quand Søn dit « redémarrer » → VPS.

**Marché Forex** : **OUVERT** — lundi 20/07 session Londres/New York en cours.

**Capture server** : ✅ vivant (`V9CaptureWatchdog Running`), redémarré ~11h55 CEST après recompilation EA M1.

**Plateforme** : **MT4** (≠ MT5). EA V9_Sonde_M1 recompilé + déployé sur toutes paires M1.

**Bot Telegram actif** : `Ipspx_bot` (chat_id `1401055223`). Token via `TELEGRAM_BOT_TOKEN_IPSPX` dans `.env` VPS.

**LLM** : OpenRouter (`tencent/hy3:free`), clé `OPENROUTER_API_KEY`.

## Kill switches (état réel — 2026-07-20 ~10h CEST, motions CEO matin)

| Kill switch | État | Note |
|---|---|---|
| `V9_EXECUTION_ENABLED` | **0 (INTERDIT)** | Fondateur, jamais — Phase 12 gelée |
| `V9_POSITION_MANAGER_ENABLED` | **1 (ON)** | Activé motion CEO 20/07 matin |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | **1 (ON)** | Activé motion CEO 20/07 matin |
| `V9_DYNAMIC_RISK_ENABLED` | **1 (APPLY)** | DRM en mode APPLY (motion CEO a9f6191) |
| `V9_GBPUSD_LONG_ONLY` | **1 (ON)** | Activé 18/07 — neutralise puits baissier |
| `V9_NO_BAISSIERE` | **1 (ON)** | Global no-short (motion 18/07) |
| `V9_CVD_ENABLED` | **0 (OFF)** | Données en DB, filtre inactif — 60j calibration |
| `V9_BEAR_PERCEPTION_ENABLED` | **0 (SHADOW)** | Phase B, 60j calibration |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | **0 (SHADOW)** | Gated R22 |
| `V9_PORTFOLIO_RISK_ENABLED` | **1 (ON)** | Défaut ON |
| `V9_KELLY_CVAR_ENABLED` | **0 (OFF)** | NO-GO walk-forward Kelly |
| `V9_REGIME_GATE_ENABLED` | **0 (OFF)** | Phase B |

## CVD tick-level — état déploiement

| Composant | État | Note |
|---|---|---|
| Migration DB (`cvd_delta`/`cvd_cumul`) | ✅ exécutée | 20/07 matin |
| EA `V9_Sonde_M1.mq4` recompilé | ✅ | 20/07 ~11h50 CEST |
| `capture_server` redémarré | ✅ | 20/07 ~11h55 CEST |
| Données CVD reçues live | ✅ **5/6 paires** | EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF |
| AUDUSD CVD | ⚠️ NULL | EA absent sur graphique AUDUSD M1 → à rattacher |
| `V9_CVD_ENABLED` | **0 (OFF)** | Données collectées, filtre inactif — 60j calibration avant activation |

## Dernier commit structurant

[`4646f33`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/4646f33) — Mission R22 lot : skip vestigiaux + dédup haussier + docs · 20/07/2026 ~13h CEST

Plage complète session 20/07 : `22c2b77..4646f33` :
- `bff59e2` — Fix P0 idempotence `post_decision_hook` (+2 tests)
- `15aad44` — DROP batch catastrophe 17/07 (3 690 trades, WR 1% → +56 090 pips récupérés)
- `4646f33` — Skip vestigiaux A+B + dédup 18 doublons haussier + docs

## Performance live (paper trade, 20/07 après DROP)

| Segment | Trades | WR | Pips |
|---|---|---|---|
| GBPUSD haussier (all) | 1 075 | **100 %** | +8 767 |
| Global paper_trades | 1 155 | **95.5 %** | +8 663 |
| WR live depuis 18/07 (n=27) | 27 | **29.6 %** ⚠️ | sous plancher 40 % |

> ⚠️ WR live post-dédup 29.6 % (n=27) : signal visible, petit échantillon. `test_post_catastrophe_wr_acceptable` laissé **rouge intentionnellement** (décision CEO). À surveiller.

## Baseline pytest — 2026-07-20 ~13h

```
2354 passed / 2 failed / 11 skipped / 3 xfailed / 3 xpassed
```
- **2 rouges tolérés** : `test_post_catastrophe_wr_acceptable` (signal perf réel, intentionnel) + `test_all_crons_wrapped_passes` (mojibake infra, pré-existant)
- `V9_EXECUTION_ENABLED=0` inchangé

## Actions immédiates ouvertes

| # | Action | Priorité | Exécutant |
|---|--------|----------|-----------|
| 1 | Rattacher EA `V9_Sonde_M1` sur graphique **AUDUSD M1** | 🔴 P1 | Søn (MT4 manuel) |
| 2 | Surveiller WR live (n=27 → 100 trades) | 🟡 passif | Observation |
| 3 | Motion CEO #1 R32 (DRM SHADOW vs APPLY) | 🟡 ouverte | Décision CEO |

## Ce qui est gelé

- **Phase 10** (fédération d'agents) — gelée R19
- **Phase 12** (exécution réelle) — interdit fondateur
- **Skills auto-générés / agents spécialisés** — hors périmètre actuel
- **CVD_ENABLED=1** — 60j calibration minimum avant activation

## Références pivots

- [`docs/STATE.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/STATE.md) — source de vérité vivante
- [`workspace/perplexity/memory/DECISIONS_LOG.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/workspace/perplexity/memory/DECISIONS_LOG.md) — historique décisions
- [`docs/CACHE_BOARD.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/CACHE_BOARD.md) — tableau de reprise complet
- [`workspace/perplexity/ACTIVE_TASKS.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/workspace/perplexity/ACTIVE_TASKS.md) — tâches actives
