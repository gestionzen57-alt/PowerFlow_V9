# AGENTS.md — PowerFlow V9 (mémoire workspace ZCode)

> **Séparation V9/V10 effectuée le 2026-08-15.**
> V10 est désormais dans `C:\projet\V10` (dépôt autonome).
> V9 reste ici — capture EA MT4, principes, paper trades, DB v9_forces.db.
> Voir `PAUSE_NOTICE_V9.md` pour le contexte de la pause.

## Mission V9

PowerFlow V9 est le **système de capture et d'analyse** des forces de devises.
Il capture les données via l'EA MT4 (`ea/V9_Sonde_M1.mq4`), les stocke dans
`data/v9_forces.db`, et applique les principes YAML (44 ACTIVE + 9 SHADOW).

V9 continue de fonctionner : capture_server (port 31685), pipeline,
calibration, paper trades. Le système cognitif V10 qui lisait ces données
est en pause dans `C:\projet\V10`.

## Documents pivots

| Document | Rôle |
|---|---|
| `AGENTS.md` | Ce fichier — état système V9 |
| `docs/DOCTRINE.md` | 30 règles V9 (R0-R30) |
| `docs/ARCHITECTURE.md` | Architecture pipeline V9 |
| `docs/DECISIONS_LOG.md` | Décisions structurantes |
| `data/v9_forces.db` | Source de données (36 Go, 30 tables) |

## Commandes rapides

```bash
python scripts/v9_calibration.py --analyze      # Lecture marché
python scripts/v9_dashboard.py --watch decisions --once
python -m pytest tests/ -q                        # Tests V9
python scripts/v9_sync_state.py                   # Régénère AGENT.md
```

## Capture (infrastructure active)

- `ea/V9_Sonde_M1.mq4` — EA MQL4 capture M1 sur MT4
- `core/v9/capture_server.py` — serveur TCP port 31685
- `data/v9_forces.db` — 36 Go, table `forces_snapshots` (332k lignes)
- Cron jobs V9 (voir `docs/CRONS_INVENTORY.md`)

## Règles critiques V9

- R7 : tests verts avant commit
- R14 : Git = source de vérité
- R10 : kill switch capital (DD max 10%)

## Bus agent V9

Le bus `data/v9_agent_bus.db` connecte ZCode, Hermes et Claude CLI :

```bash
python scripts/agent_bus_cli.py pending
python scripts/agent_bus_cli.py poll <profile> --source zcode
python scripts/agent_bus_cli.py stats --hours 24
```