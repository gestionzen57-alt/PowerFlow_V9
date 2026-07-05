# PHASE 7 — Déploiement live

## Statut
✅ Terminée, fusionnée sur `feat/v9-foundation-clean` (fast-forward, sans conflit).

## Objectif
Préparer le déploiement réel : référentiel temporel marché, port EA configurable, outillage
de vérification et test d'intégration.

## Livrables
- `core/v9/config.py` — référentiel temporel : `BROKER_UTC_OFFSET_HOURS` (3, Tickmill/FTMO GMT+3), `LOCAL_TIMEZONE` ("Europe/Paris"), `MARKET_OPEN_UTC_DAY/HOUR`, `MARKET_CLOSE_UTC_DAY/HOUR`. Port de référence `LISTEN_PORT` basculé sur `31690` (test V9 — V8 reste sur `31685` en production)
- `core/v9/market_calendar.py` — `MarketCalendar` : `is_market_open`, `current_session` (priorité overlap > london > new_york > tokyo > sydney), `next_open`, `broker_to_utc`/`utc_to_broker`, `paris_to_utc` (DST via `zoneinfo`)
- `ea/V9_Sonde_TF.mq4`, `ea/V9_Sonde_M1.mq4` — input `ServerPort` (remplace la constante Winsock figée qui codait en dur le port 31685) ; fonction `MakeSockAddr0(port)` recalculant dynamiquement l'adresse
- `ea/V9_Sonde_README.md` — section réseau mise à jour
- `scripts/deploy_v9.py` — `--check`/`--start`/`--status`/`--stop`
- `scripts/validate_ea_output.py` — validation structure + cohérence timestamp + heuristique plausibilité AUD
- `scripts/live_integration_test.py` — traversée de la chaîne complète sur DB de test dédiée, jamais d'écriture en production
- `docs/deployment/V9_DEPLOYMENT_GUIDE.md` — procédure complète

## Décisions notables
- Aucune logique d'exécution d'ordre, aucune calibration automatique des seuils (`config.py` reste la source de vérité, ajustable manuellement).
- Point ouvert non bloquant : les `.ex4` compilés existants datent d'avant l'ajout de `ServerPort` — recompilation requise avant tout déploiement réel.

## Tests
22 tests (`test_market_calendar.py`), portant le total à 118, revalidés post-fusion.

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE7.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE7.md),
[docs/deployment/V9_DEPLOYMENT_GUIDE.md](../deployment/V9_DEPLOYMENT_GUIDE.md)
