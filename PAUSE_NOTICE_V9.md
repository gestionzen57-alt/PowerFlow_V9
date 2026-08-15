# PAUSE NOTICE V9 — PowerFlow V9

> **Date** : 2026-08-15
> **État** : Capture V9 continue de fonctionner. Le système cognitif
> (V10) est en pause dans `C:\projet\V10`.

## Ce qui reste actif dans V9

- **capture_server** (port 31685) — reçoit les données de l'EA MT4
- **EA `V9_Sonde_M1.mq4`** — capture M1 sur MT4
- **DB `data/v9_forces.db`** (36 Go) — alimentée en continu
- **Cron jobs V9** — calibration, heartbeat, resolve loop (voir `docs/CRONS_INVENTORY.md`)
- **Purge auto** — `principle_evaluations` > 30j (commit `d457001`)

## Ce qui est en pause

- Le système cognitif V10 qui lisait `forces_snapshots` — voir `C:\projet\V10\PAUSE_NOTICE.md`
- Le développement de nouvelles fonctionnalités V9

## Séparation physique

V10 a été séparé dans `C:\projet\V10` le 2026-08-15. V9 redevient un dépôt
autonome avec uniquement le code V9 (capture, principes, paper trades,
calibration, dashboard).

V10 accède à `data/v9_forces.db` en lecture seule via :
```
V9_FORCES_DB_PATH=C:\projet\V9\data\v9_forces.db
```

## Pour reprendre V10

Voir `C:\projet\V10\docs\V10\V10_SYSTEM_CANON.md` — le point d'entrée unique.