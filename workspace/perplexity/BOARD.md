# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider.
**Resync Perplexity 2026-07-18 14:18 CEST — HEAD 26b0070 lu depuis MCP GitHub.**

## Statut global V9 — 2026-07-18 14h18 CEST

**Infrastructure** : tout sur **VPS** depuis ~1 semaine (plus PC local). Quand Søn dit « redémarrer » → VPS.

**Marché Forex** : **FERMÉ** depuis vendredi 22h UTC. Réouverture **dimanche 22h UTC** (= lundi 00h00 Paris CEST). L'absence de données fraîches est **normale** ce weekend.

**Capture server** : MORT depuis ~09h00 UTC ce matin (dernier bar M5 = 23:57 UTC vendredi). Sera redémarré après réouverture dimanche soir. **Pas un bug — weekend Forex.**

**Plateforme** : **MT4** (≠ MT5) = lecture indicateur SDI. MT5 non implémenté. EA sur MT4.

**Bot Telegram actif** : `Ipspx_bot` (chat_id `1401055223`). Token via `TELEGRAM_BOT_TOKEN_IPSPX` dans `.env` VPS.

**LLM** : OpenRouter (`tencent/hy3:free`), clé `OPENROUTER_API_KEY`. Rate-limit HITL persistant sur disque (`logs/.hitl_telegram_ratelimit.json`).

## Kill switches (état réel config/v9_kill_switches.env)

| Kill switch | État | Note |
|---|---|---|
| `V9_GBPUSD_LONG_ONLY` | **1 (ON)** | Activé 18/07 — neutralise puits baissier |
| `V9_BEAR_PERCEPTION_ENABLED` | **0 (SHADOW)** | Calcule skip/exit sans appliquer — Phase B |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | **0 (SHADOW)** | Gated R22 — Phase B |
| `V9_PORTFOLIO_RISK_ENABLED` | **1 (ON)** | Défaut ON |
| `V9_POSITION_MANAGER_ENABLED` | **0 (OFF)** | Décision CEO requise |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | **0 (OFF)** | Décision CEO requise |
| `V9_EXECUTION_ENABLED` | **0 (INTERDIT)** | Fondateur — jamais |

## Dernier commit structurant
[`26b0070`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/26b0070ee283a41d3f0a5ab17ce7843406548fff) — fix(telegram): notifier 400 + LLM OpenRouter + rate-limit HITL persistant (18/07/2026 09:23 UTC)

## Performance live (paper trade réel, forward-test)
- WR GBPUSD **haussier : 100%** (1088 trades, +8.18 pips/trade) ✅
- WR GBPUSD **baissier : 1%** (3681 trades) → neutralisé par `long_only` ✅
- 250/250 tests verts

## Phase actuelle — Phase B (validation shadow)
**Phase A LIVRÉE** (2026-07-18) : long-only ON + shadow modes + dashboard baissier + 250 tests.
**Phase B en attente** d'ouverture marché dimanche 22h UTC :
- B1 : Redémarrer capture server (P0 immédiat après réouverture)
- B2 : Daily monitoring long_only
- B3 : Validation BearPerception 60 jours
- B4 : Validation filtre devise 60 jours

## Blocages
- **Capture server mort** — normal (marché fermé weekend). Action P0 : restart dimanche ~22h UTC.
- **2 décisions CEO pendantes** : activer `V9_POSITION_MANAGER_ENABLED=1` et `V9_MARKET_REGIME_GLOBAL_ENABLED=1`.

## Prochaines actions
1. Dimanche 22h UTC : `git pull VPS` + restart pipeline (capture_server + daemon)
2. Lundi matin : vérifier premier snapshot frais + décisions GBPUSD long-only
3. T+7j : revue monitoring Phase B (WR haussier ≥ 95% ?)
4. T+30j : décision activation BearPerception si validation OK

## Ce qui est gelé
- **Phase 10** (fédération d'agents) — gelée R19, ne démarre pas avant stabilisation live Phase 9
- **Phase 12** (exécution réelle) — interdit fondateur
- **Skills auto-générés / agents spécialisés** — hors périmètre actuel

## Références pivots
- [`docs/STATE.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/STATE.md) — source de vérité vivante
- [`workspace/perplexity/memory/DECISIONS_LOG.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/workspace/perplexity/memory/DECISIONS_LOG.md) — historique §6.12
- [`docs/monitoring/MONITORING_LONG_ONLY_2026-07-18.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/monitoring/MONITORING_LONG_ONLY_2026-07-18.md) — suivi Phase B
- [`docs/deployment/V9_DEPLOYMENT_GUIDE.md`](https://github.com/gestionzen57-alt/PowerFlow_V9/blob/feat/v9-foundation-clean/docs/deployment/V9_DEPLOYMENT_GUIDE.md)
