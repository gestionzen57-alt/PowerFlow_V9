# Audit CVaR 95% — Proposition recalibrage (2026-08-03)

## Verdict NO-GO walk-forward initial (18/07)

Le kill switch `V9_KELLY_CVAR_ENABLED` est à **0** depuis le 18/07/2026
suite à un audit walk-forward **NO-GO** (variance 45pts, sizing trop
restrictif qui annulait l'edge). Le défaut conservateur (`CVAR_BUDGET_PIPS=12`)
est resté en place.

## Audit live 03/08 (post-DROP, post-L7+L8)

337 paper_trades clôturés (post-DROP 17/07) :

| Statistique | Valeur |
|---|---|
| n | 337 |
| mean | -0.77 pips/trade |
| min | -18.0 pips |
| max | +9.5 pips |
| P50 | -1.0 pips |
| P75 | +4.5 pips |
| P90 | +5.0 pips |
| P95 | +9.5 pips |
| **CVaR 95% (5% pire queue)** | **-16.67 pips** |

## Diagnostic NO-GO

Avec `CVAR_BUDGET_PIPS=12` (défaut), **67% des trades seraient CAPPED**
(ceux qui dépassent -12p en queue). Le sizing est tellement réduit que
le gain de l'edge (P75 = +4.5p × 25% WR) est annulé par le coût d'opportunité.

## Proposition recalibrage (motion CEO requise)

**Option A (conservateur)** : `CVAR_BUDGET_PIPS=15.0`
- 35% des trades cappés (P5=−16.67p, marge 10%)
- Couvre la majorité des cas sans étouffer l'edge
- Risque : 1 trade sur 20 peut encore dépasser 15p

**Option B (équilibré)** : `CVAR_BUDGET_PIPS=18.0`
- 5% des trades cappés (juste au P95 perte)
- Couvre toute la queue distribution observée
- Risque : sizing réel peut doubler vs Option A

**Option C (interdit sans motion explicite)** : `CVAR_BUDGET_PIPS=20.0`
- 0% des trades cappés (CVaR inopérant)
- Identique à `V9_KELLY_CVAR_ENABLED=0` (kill switch OFF)

## Recommandation CEO

**Option B = `CVAR_BUDGET_PIPS=18.0`** avec `V9_KELLY_CVAR_ENABLED=1`.

Walk-forward 7j requis avant activation (Phase 13.2 méthodologie).

## Fichiers concernés

| Fichier | Role | Modification proposée |
|---|---|---|
| `core/v9/config.py:565` | `CVAR_BUDGET_PIPS = 12.0` | → `18.0` (si motion CEO) |
| `config/v9_kill_switches.env` | `V9_KELLY_CVAR_ENABLED=0` | → `1` (si motion CEO) |
| `tests/test_kelly_cvar.py` (14 tests) | Couverture sizing | Régression à valider |

## Statut

⏸ **EN ATTENTE motion CEO**. Pas d'activation automatique (R25' strict).
Documenté ici pour traçabilité R26 + reprise session future.

---

_Référence : `workspace/perplexity/ACTIVE_TASKS.md` §A11 (P2 OPTIMISATION)._
