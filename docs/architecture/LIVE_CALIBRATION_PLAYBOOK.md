# Axe 6 — Live calibration playbook (réouverture dimanche 22h UTC)

> **Audit edgefund V9 — Axe 6/8** · OPUS Claude Code · 2026-07-19.
> Contexte : marché fermé jusqu'à dim 22h UTC. Motion long-only active.

## Principe directeur

Après le reframing (Axe 1) : le désastre du 17/07 était une **boucle** (85 %) + un
**régime baissier défavorable** (reste), pas un défaut du système. La réouverture doit donc
(a) garantir que la boucle **ne peut pas** se reproduire, (b) valider l'edge **haussier** en
live, (c) couper vite si l'edge live diverge du backtest.

## Checklist de réouverture

### T+0 — avant l'ouverture (dim 21h30 UTC)

| # | Contrôle | Attendu | Commande |
|---|---|---|---|
| 1 | `capture_server` up | port LISTENING | `python scripts/agent_bus_cli.py stats` / netstat |
| 2 | EA MT connecté | snapshots frais < 60s | `python scripts/v9_calibration.py --analyze` |
| 3 | **Loop breaker ON** | `V9_LOOP_BREAKER_ENABLED=1` | ⚠️ **activer** (défaut OFF) |
| 4 | Long-only ON | `V9_GBPUSD_LONG_ONLY=1`, `V9_NO_BAISSIERE=1` | déjà actifs |
| 5 | Trader mini ON | `V9_TRADER_MINI_ENABLED=1` | vérifier |
| 6 | Tokens Telegram | révoqués + rotés (Axe 7) | BotFather |

### T+1h — premier snap live

- Comparer décisions live vs paper_trades ouverts. **Densité < 10 trades / 15 min / paire**
  (sinon le loop breaker doit avoir bloqué → vérifier les logs).
- WR haussier premières N entrées ≥ 80 %.

### T+24h — bilan haussier-only

- WR haussier ≥ 90 % (backtest 93 %, live précédent 98,8 %).
- DD 24h ≥ −200 pips. Aucune entrée baissière (long-only).

### T+7j — validation edge

- WR haussier ≥ 90 % sur ≥ 100 trades **out-of-sample** (le seul chiffre qui compte).
- Si tenu : candidat à élargir (diversification Axe 3, ou ré-autoriser baissier **par
  régime** seulement).

## Kill switches d'urgence (watchdog)

Seuils recommandés, à câbler dans `core/v9/v9_live_watchdog.py` (R2 additif, kill switch
`V9_LIVE_WATCHDOG_ENABLED`, lecture seule sur `paper_trades`) :

| Déclencheur | Seuil | Action automatique |
|---|---|---|
| Drawdown 24h | < **−200 pips** | `V9_TRADER_MINI_ENABLED=0` + alerte Telegram |
| WR live (fenêtre 50 trades) | < **80 %** | `V9_TRADER_MINI_ENABLED=0` + alerte |
| WR live (fenêtre 50 trades) | < **60 %** | `V9_GBPUSD_LONG_ONLY=0`→arrêt total + alerte P0 |
| Densité (loop guard) | > **10 trades / 15 min / paire** | déjà couvert par `v9_loop_breaker` |

> Le watchdog est **spécifié ici mais non encore implémenté** (`v9_live_watchdog.py`
> absent du repo). Décision CEO requise : le construire (module + tests, ~1 session) ou
> piloter manuellement via ces seuils pour la première réouverture. Recommandation :
> **manuel pour dimanche** (le loop breaker + long-only couvrent le risque catastrophe),
> **watchdog automatisé en T+1 semaine** une fois l'edge live confirmé.

## Score Axe 6

| Critère | Cible | Résultat |
|---|---|---|
| Playbook 3 phases | oui | ✅ T+0 / T+1h / T+24h / T+7j |
| 3 seuils d'arrêt | oui | ✅ DD −200, WR<80, WR<60 |
| Watchdog livré | bonus | ⚠️ **spécifié**, implémentation renvoyée à décision CEO |
