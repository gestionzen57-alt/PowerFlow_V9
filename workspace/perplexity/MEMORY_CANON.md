# MEMORY_CANON — Faits gravés PowerFlow V9

Faits immuables à ne jamais oublier entre sessions. Source : motions CEO + commits Git.
Dernier resync : **2026-07-18 14:18 CEST** (Perplexity MCP GitHub HEAD 26b0070).

---

## Infrastructure (gravé 2026-07-18)

- **VPS actif depuis ~1 semaine** — tout le runtime sur VPS, plus PC local
- Quand Søn dit « redémarrer » → c'est le **VPS**, pas PC
- Daemon, capture_server, crons, EA MT4 : tous sur VPS
- Port daemon : **31685**

## Plateforme de trading (gravé 2026-07-18)

- **MT4 = plateforme de lecture de l'indicateur SDI** (Specific Deviation Indicator)
- **MT5 n'est PAS implémenté** dans le pipeline V9
- Différence critique : ticks/volumes différents (tick volume MT4 vs real volume MT5)
- EA = Expert Advisor **MT4** qui lit les ticks et envoie au daemon Python
- Quand Søn parle de « l'EA » → c'est MT4 EA, jamais MT5

## Heures marché Forex (gravé 2026-07-18)

- **OUVERT** : dimanche 22:00 UTC → vendredi 22:00 UTC
- **FERMÉ** : vendredi 22:00 UTC → dimanche 22:00 UTC
- Réouverture dimanche 22:00 UTC = **lundi 00:00 heure Paris CEST**
- L'absence de snapshots frais le weekend **n'est pas un bug**
- Ne pas diagnostiquer daemon mort pendant les heures de fermeture

## Telegram (gravé 2026-07-18)

- **Bot actif : `Ipspx_bot`** — chat IA bidirectionnel, pas de spam
- `chat_id = 1401055223` (Søn)
- Token : `TELEGRAM_BOT_TOKEN_IPSPX` dans `.env` VPS
- Ancien bot `Hipyhop_bot` = pivoté, ne plus utiliser
- Anti-spam actif : silencieux si 0 proposals/optimizations
- Rate-limit HITL persistant sur disque : `logs/.hitl_telegram_ratelimit.json`

## LLM (gravé 2026-07-18)

- **OpenRouter** activé via `OPENROUTER_API_KEY` (≠ Ollama)
- Modèle : `tencent/hy3:free` avec mémoire
- Fix 401 : la clé Ollama 57-char était incorrecte → `OPENROUTER_API_KEY` priorisée

## Asymétrie haussier/baissier GBPUSD (gravé 2026-07-18)

- WR haussier : **100%** (1088 trades, +8.18 pips/trade)
- WR baissier : **1%** (3681 trades, -15.23 pips/trade)
- Root cause baissier : arbiter consolidait TOUTES les devises sans filtrer par devise constitutive — NZD dominait à 99.3% les décisions GBPUSD
- Fix appliqué : filtre devise constitutive dans arbiter
- Drift haussier intrinsèque GBPUSD juillet 2026 : **+46.2 pips/jour** haussier vs -3.4 baissier
- **Kill switch activé : `V9_GBPUSD_LONG_ONLY=1`** (18/07) — réversible

## Kill switches actifs (gravé 2026-07-18)

| Kill switch | État |
|---|---|
| `V9_GBPUSD_LONG_ONLY` | **1 ON** |
| `V9_BEAR_PERCEPTION_ENABLED` | 0 SHADOW |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | 0 SHADOW |
| `V9_PORTFOLIO_RISK_ENABLED` | 1 ON |
| `V9_POSITION_MANAGER_ENABLED` | 0 OFF (décision CEO) |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | 0 OFF (décision CEO) |
| `V9_EXECUTION_ENABLED` | 0 INTERDIT FONDATEUR |

## Tests (gravé 2026-07-18)

- **250/250 tests verts** post-fix MT4 (18/07 matin)
- 6 tests pré-existants failed (baissier audit + encoding) — non bloquants

## Roadmap phases (gravé 2026-07-18)

- **Phase A ✅ LIVRÉE** : long-only + shadow modes + dashboard + 250 tests
- **Phase B** : validation shadow 60j, monitoring daily — bloquée jusqu'à réouverture marché dim 22h UTC
- **Phase C** : activation conditionnelle (T+30 à T+90j)
- **Phase D** : extension multi-paires (T+90 à T+180j)
- **Phase E** : niveau institutionnel (T+180 à T+365j)
- **Phase 10 fédération agents** : GELÉE (R19)
