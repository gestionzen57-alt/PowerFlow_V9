# VPS_RUNBOOK — Déploiement et exploitation PowerFlow V9 sur VPS H24

## Rôle de ce document

Ce runbook couvre le cycle de vie VPS : prérequis, installation, démarrage,
surveillance, backup, recovery. Il **complète** sans les dupliquer :
- `docs/deployment/V9_DEPLOYMENT_GUIDE.md` — compilation/déploiement de l'EA
  MT4 (`ea/V9_Sonde_TF.mq4`, `ea/V9_Sonde_M1.mq4`), hors périmètre ici.
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — détail des scripts
  `v9_supervisor.py` / `v9_bootstrap.py` / `v9_market_open.py` /
  `v9_session_resume.py` (outillage machine locale Windows).
- `docs/checkpoints/CHECKPOINT_20260707_VPS_READY.md` — arbitrages
  d'architecture VPS (§5 AGENTIC_MAP.md) : orchestrateur central Option A,
  reviewer HITL Telegram, persistance SQLite WAL, réutilisation EA MT4 sans
  modification, watchdog + heartbeat, rollback par bascule DNS.

Ce que ce document ne couvre pas : logique de trading, exécution d'ordre
(interdit fondateur avant Phase 12), configuration Hermes (voir profil
`powerflow` séparément — hors dépôt V9).

## Prérequis VPS

- **Python 3.11+** — aucune dépendance externe requise pour la chaîne
  `core/v9/*` (stdlib uniquement : `sqlite3`, `asyncio`, `zoneinfo`, etc.).
- **SQLite** — via le module stdlib `sqlite3` ; le binaire CLI `sqlite3`
  est utile pour le debug mais pas requis en exploitation.
- **Port 31685** — port de référence V9 (`core/v9/config.py:LISTEN_PORT`).
  Par défaut le serveur de capture est bindé sur `LISTEN_HOST = 127.0.0.1`
  (loopback uniquement) : aucune ouverture pare-feu externe n'est
  nécessaire tant que le terminal MT4 tourne **sur le même VPS** que
  `capture_server` (c'est l'architecture retenue — voir Option A ci-dessus,
  réutilisation EA sans modification). N'ouvrir 31685 vers l'extérieur que
  si l'architecture change (MT4 sur une machine distincte).
- MT4 (terminal + EA compilés) si le VPS héberge aussi le terminal —
  voir `V9_DEPLOYMENT_GUIDE.md`.

## Installation

```bash
git clone <repo> /opt/v9   # ou chemin choisi, référencé ci-après par $V9_ROOT
cd /opt/v9
python -m pip install -e .   # si un pyproject/setup existe ; sinon rien à installer (stdlib only)
```

Fichiers **non versionnés** à provisionner manuellement sur le VPS (voir
`.gitignore`) :
- `config/telegram.json` (`BOT_TOKEN` / `CHAT_ID`) — requis par
  `scripts/v9_telegram_notifier.py` et `scripts/v9_heartbeat.py --heartbeat`.
- `data/v9_forces.db` — soit une base neuve (créée au premier `init_all_dbs`
  par `capture_server`), soit une base migrée depuis le poste local via
  `scripts/v9_vps_seed.py` (voir section Backup).

## Démarrage

```bash
export V9_ROOT=/opt/v9
bash scripts/v9_vps_bootstrap.sh
```

Le script :
1. Vérifie la présence de `data/v9_forces.db`.
2. Démarre `capture_server` en arrière-plan (PID dans `logs/v9_capture.pid`).
3. Démarre `scripts/v9_meta_agent.py --watch` (scan patterns/10min, cycle
   d'apprentissage/60min — lecture seule sur le bus d'événements, propose
   sans jamais agir, doctrine R25').
4. Liste les crons Hermes actifs (`hermes cron list`).

**Note d'architecture** : `core/v9/agent_bus.py` n'est **pas** démarré comme
service séparé — c'est une bibliothèque pure (`publish`/`subscribe`/`poll`
sur `data/v9_forces.db`), sans mode démon. Elle est appelée en-process par
les agents qui consomment le bus (meta-agent aujourd'hui, autres agents à
venir), pas exécutée à part.

## Surveillance (Telegram)

Deux mécanismes indépendants, tous deux en `no_agent: true` côté Hermes
(aucun LLM dans la boucle, exécution script pure) :

- **Heartbeat / watchdog** — `scripts/v9_heartbeat.py --heartbeat` en cron
  (toutes les 5 min recommandé). Vérifie port 31685 occupé + fraîcheur DB +
  compteur d'échecs consécutifs ; alerte Telegram après 3 échecs. Après une
  intervention manuelle, réinitialiser le compteur :
  `python scripts/v9_heartbeat.py --reset`.
- **Notifications signaux** — `scripts/v9_telegram_notifier.py --once`,
  déjà déclaré côté Hermes (cron `telegram_notifier_v9`, `* * * * *`).

## Backup

- **Code** : Git est la source de vérité (règle 14 doctrine) — rien à
  sauvegarder séparément, `git pull` suffit à restaurer l'état du dépôt.
- **DB** (`data/v9_forces.db`) : générer une copie allégée et cohérente
  (WAL-safe) via :
  ```bash
  python scripts/v9_vps_seed.py --dest backups/v9_forces_$(date +%Y%m%d).db --days 7
  ```
  Purge les événements > 7 jours, VACUUM, réindexe — adapté à un transfert
  ou un snapshot périodique sans embarquer tout l'historique.
- **Secrets** (`config/telegram.json`, clé API mem0/Hermes) : jamais dans
  Git — à sauvegarder séparément (gestionnaire de secrets ou copie chiffrée
  hors dépôt), en dehors du périmètre de ce runbook.

## Recovery

1. **Process mort / port bloqué** : relancer `bash scripts/v9_vps_bootstrap.sh`.
   Si le port 31685 reste occupé par un process orphelin (incident déjà
   documenté sur le poste local, voir `workspace/perplexity/INCIDENTS.md`
   2026-07-05), identifier et arrêter le PID avant de relancer.
2. **DB corrompue ou à réinitialiser** : restaurer depuis le dernier backup
   `backups/v9_forces_YYYYMMDD.db` (copier vers `data/v9_forces.db`), puis
   `python scripts/v9_heartbeat.py --reset`.
3. **Rollback complet vers le poste local** (option 6a retenue,
   `CHECKPOINT_20260707_VPS_READY.md`) : bascule DNS `vps.powerflow.local`
   vers le poste local, puis `git pull && python scripts/v9_ops.py` côté
   local pour reprendre la main.

## Écarts constatés à corriger avant mise en production VPS

Découverts lors de la consolidation de ce runbook, hors périmètre des
scripts livrés ici :
- Les crons Hermes `v9_principle_alert_hourly`, `v9_resolve_daemon_5min` et
  `telegram_notifier_v9` référencent des scripts absents de
  `D:\hermes\profiles\powerflow\scripts\` (seul `v9_read_wrapper.sh` existe
  et suit le bon pattern : wrapper `.sh` qui `cd` vers le dépôt V9 puis
  appelle le script Python réel). Les 3 wrappers manquants sont à créer
  sur ce modèle avant d'activer ces crons sur le VPS.
- `scripts/v9_db_hygiene.py` référence `scripts/_db_md5_backup.py`
  (`--backup` obligatoire avec `--apply`) qui n'existe pas dans le dépôt —
  à créer ou à retirer de la documentation du script.
