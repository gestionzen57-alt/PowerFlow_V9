# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider.
**Resync Opus 2026-07-19 ~15h50 UTC — session réouverture (prépa P0 + réconciliation kill switches, marché encore fermé).**

## Statut global V9 — 2026-07-19 ~15h50 UTC

**Infrastructure** : tout sur **VPS** depuis ~1 semaine (plus PC local). Quand Søn dit « redémarrer » → VPS.

**Marché Forex** : **FERMÉ** — réouverture **dimanche 19/07 ~22h UTC** (= lundi 00h00 Paris CEST).
Session lancée ~15h UTC → observation live T+1h **différée** à la réouverture. Prépa P0 faite :
kill switches réconciliés + `V9_PaperTradeLoop` refit (FILE_NOT_FOUND → OK, charge l'env propre).

**Capture server** : capture du snapshot BOARD précédent (14h18 CEST) parlait de
« mort depuis ~09h00 UTC ». Pas de preuve technique d'un daemon vivant dans
cette session Hermes, donc on **conserve l'alerte** jusqu'à preuve du contraire
(à vérifier à la réouverture dimanche). **Pas un bug — weekend Forex.**

**Plateforme** : **MT4** (≠ MT5) = lecture indicateur SDI. MT5 non implémenté. EA sur MT4.

**Bot Telegram actif** : `Ipspx_bot` (chat_id `1401055223`). Token via `TELEGRAM_BOT_TOKEN_IPSPX` dans `.env` VPS. **Notifier dynamique livré** (commit `66bca85`) — prompt système lit live l'état V9 au lieu d'un snapshot figé.

**LLM** : OpenRouter (`tencent/hy3:free`), clé `OPENROUTER_API_KEY`. Rate-limit HITL persistant sur disque (`logs/.hitl_telegram_ratelimit.json`).

## Kill switches (état réel config/v9_kill_switches.env — réconcilié 2026-07-19 ~15h50 UTC)

> **Réconciliation pré-réouverture (motion CEO « aligner sur §1 »)** : le fichier avait dérivé
> à `=1` sur 4 switches (mtime 10:30 UTC) vs cette table + §1 checklist. Remis à 0. Dérive
> dormante (order_executor non câblé au live, order_queue vide), corrigée avant refit P0.1.

| Kill switch | État | Note |
|---|---|---|
| `V9_GBPUSD_LONG_ONLY` | **1 (ON)** | Activé 18/07 — neutralise puits baissier |
| `V9_NO_BAISSIERE` | **1 (ON)** | Global no-short (motion 18/07) — conservé |
| `V9_BEAR_PERCEPTION_ENABLED` | **0 (SHADOW)** | Réconcilié 19/07 (était dérivé à 1) — Phase B |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | **0 (SHADOW)** | Gated R22 — Phase B |
| `V9_PORTFOLIO_RISK_ENABLED` | **1 (ON)** | Défaut ON |
| `V9_POSITION_MANAGER_ENABLED` | **0 (OFF)** | Réconcilié 19/07 (était dérivé à 1) — décision CEO requise |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | **0 (OFF)** | Réconcilié 19/07 (était dérivé à 1) — décision CEO requise |
| `V9_EXECUTION_ENABLED` | **0 (INTERDIT)** | Réconcilié 19/07 (était dérivé à 1) — Fondateur, jamais |

## Dernier commit structurant
[`a4acfac`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/a4acfac) — chore(v9): refresh data/strategy_pole (auto-calibrator post-commit) · 18/07/2026 21:35 UTC

Précédents significatifs de la journée :
- `66bca85` feat(v9): notifier Telegram dynamique + prompt Opus audit edgefund (motion §17h45)
- `fbca486` feat(v9): regime gate + CVaR sizing + CVD tick-level (chantiers A/B/C, kill switches OFF)
- `152d418` feat(v9): câblage V9_DYNAMIC_TP_SL + activation kill_switches (motion §17h15)

## Performance live (paper trade réel, forward-test)
- WR GBPUSD **haussier : 100%** (1088 trades, +8.18 pips/trade) ✅
- WR GBPUSD **baissier : 1%** (3681 trades) → neutralisé par `long_only` ✅
- 250/250 tests verts (snapshot 14h18 CEST — **non re-canon** ce soir, run complet ~7 min hors scope)
- 12 tests supplémentaires notifier interactif (commit `66bca85`, run isolé 7.97s OK)

## Phase actuelle — Phase B (validation shadow)
**Phase A LIVRÉE** (2026-07-18) : long-only ON + shadow modes + dashboard baissier + 250 tests.
**Journée additifs** (Opus + Hermes 2026-07-18 §17h15→21h35) :
- A — Regime gate primaire, kill switch `V9_REGIME_GATE_ENABLED=0`
- B — CVaR sizing institutionnel, kill switch `V9_KELLY_CVAR_ENABLED=0` (caveat NO-GO walk-forward Kelly)
- C — CVD tick-level MT4, kill switch `V9_CVD_ENABLED=0` (migration DB standalone)
- Notifier Telegram dynamique (état live, routing data, `reply_markup`)

**Phase B en attente** d'ouverture marché dimanche 22h UTC :
- B1 : Redémarrer capture server (P0 immédiat après réouverture)
- B2 : Daily monitoring long_only
- B3 : Validation BearPerception 60 jours
- B4 : Validation filtre devise 60 jours
- B5 : Audit edgefund (motion §17h45 « prompt Opus » — en attente validation CEO)

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
