---
name: powerflow-v9-live-ops
description: "Opérations live V9 — déploiement EA, démarrage pipeline, observation, calibration, diagnostic sur Windows."
category: devops
tags: [v9, live, ops, deployment, windows, v9_ops]
statut: actif
derniere_maj: 2026-07-09
version: 0.0.1
note_chantier: aligne au HEAD b256faa (878 tests, supervision H24 LIVE)
---
# PowerFlow V9 — Live Operations

## Purpose

Standardized procedures for running the PowerFlow V9 capture pipeline live on Windows. Covers EA deployment on MT4, server lifecycle, flux validation, observation, and calibration.

## Point d'entrée unique

Depuis commit `89cc425` (2026-07-06), **toutes les commandes opérationnelles** passent par `scripts/v9_ops.py` :

```powershell
python scripts\v9_ops.py <commande>
```

| Commande | Action | Script délégué |
|---|---|---|
| `check` | Vérification pré-déploiement | `deploy_v9.py --check` |
| `start` | Démarrage serveur | `deploy_v9.py --start` |
| `stop` | Arrêt serveur | `deploy_v9.py --stop` |
| `restart` | stop + start automatique | compose stop + start |
| `status` | État du système | `deploy_v9.py --status` |
| `boot` | Bootstrap complet | `v9_bootstrap.py --boot` |
| `market-open` | Ouverture marché | `v9_market_open.py --market-open` |
| `health` | Health snapshot | `v9_supervisor.py --health` |
| `dashboard` | Dashboard one-shot | `v9_dashboard.py --once` |
| `watch` | Dashboard live (5s) | `v9_dashboard.py --interval 5` |
| `signals` | Dashboard signaux | `v9_dashboard.py --watch signals` |
| `decisions` | Dashboard décisions | `v9_dashboard.py --watch decisions` |
| `calibrate` | Analyse + suggestions seuils | `v9_calibration.py --analyze` |
| `principles` | Hit rate principes | `v9_calibration.py --principes` |
| `stats` | Statistiques globales | `v9_calibration.py --stats` |
| `validate-ea` | Valider message EA | `validate_ea_output.py --once` |
| `log` | Log tail PowerShell | `Get-Content -Wait` |
| `chain-regen` | Régénération chaîne | `regenerate_chain.py` |

## Port canonique

**31685** — port de référence V9 définitif. Les EA V9 utilisent `ServerPort=31685` par défaut (input dans le code EA). `core/v9/config.py` : `LISTEN_PORT = 31685`.

Le port 31690 et la mention V8 ont été supprimés des docs le 2026-07-06. Il n'y a plus de coexistence V8/V9.

## Séquence de démarrage live

### 0. Prérequis machine de trading

- MT4 Tickmill installé, connecté au serveur (GMT+3)
- Indicateur `SDI TCSWL 600+` chargé et fonctionnel sur les charts
- Les EA `V9_Sonde_TF.mq4` et `V9_Sonde_M1.mq4` compilés dans `MQL4/Experts/`

### 1. Attacher les EA (7 charts GBPUSD)

| Chart | EA | Inputs |
|---|---|---|
| GBPUSD M1 | `V9_Sonde_M1.mq4` | `ServerPort=31685`, `BrokerUTCOffsetHours=3`, `ReplayOnInit=false` |
| GBPUSD M5 | `V9_Sonde_TF.mq4` | `ServerPort=31685`, `ShiftIndex=1`, `RefreshSeconds=1` |
| GBPUSD M15 | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD M30 | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD H1 | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD H4 | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD D1 | `V9_Sonde_TF.mq4` | idem M5, ReplayBars réduit (200) |

Vérifier le **smiley vert** en haut à droite de chaque chart.

### 2. Démarrer le serveur Python

```powershell
cd D:\Projet\V9
python scripts\v9_ops.py start
```

### 3. Vérifier le flux live

```powershell
python scripts\v9_ops.py log
```

Le log doit montrer des lignes `[INFO] scene_builder:` ou `[INFO] DB:` avec des timestamps qui avancent.

**⚠️ Critère fiable** : le serveur écoute le port même sans EA connecté. Un port LISTENING ne prouve PAS qu'un EA envoie des données. **La seule preuve de flux live est l'apparition d'un nouveau snapshot avec timestamp avançant dans le log dans les 60s.**

### 4. Valider

```powershell
python scripts\v9_ops.py validate-ea
python scripts\v9_ops.py watch
```

### 5. Calibration (après n≥200 M5+ live)

```powershell
python scripts\v9_ops.py calibrate
python scripts\v9_ops.py principles
python scripts\v9_ops.py stats
```

## Distinguer flux live vs replay

| Indice | Live | Replay |
|---|---|---|
| Timestamp dernière snapshot | Avance (~60s M1, ~5min M5) | Fixe (daté du run de regenerate_chain) |
| `is_closed_bar` | 0 (bougie en cours M1) | 1 (bougies fermées) |
| Nouveaux snapshots en observation | Oui (toutes les ~60s) | Non (stable) |
| `source` | `MT4_SDI` (même valeur) | `MT4_SDI` (même valeur) |
| Stale sur les 10 derniers | ~0-1/10 | Dépend du rapport signal/seuil |
| `ReplayOnInit` dans le log | Pas de replay massif | Pic de 600 snapshots au démarrage |

**Piège** : les EA ont `ReplayOnInit=true` par défaut. Au démarrage, ils rejouent 600 bougies d'historique. Ces snapshots ressemblent à du live (timestamps récents) mais sont du replay de bougies passées. Attendre ~2 minutes après le démarrage pour observer le vrai flux live.

## validate-ea sous Windows

`python scripts\v9_ops.py validate-ea` fonctionne en mode automatique :

1. Tente un `bind()` TCP sur le port 31685
2. Si le port est libre → écoute et attend 1 message EA (mode diagnostic terrain)
3. Si le port est occupé (serveur de capture actif) → **fallback DB** : lit le dernier `forces_snapshots` depuis la DB et le reformate en JSON EA

Le fallback DB évite le `WinError 10013` (bind interdit par `SO_REUSEADDR` sous Windows quand 2 processus partagent un port).

```powershell
# Par défaut : TCP → fallback DB si port occupé
python scripts\v9_ops.py validate-ea

# Forcer TCP (échoue si port occupé)
python scripts\validate_ea_output.py --once --force-tcp

# Forcer lecture DB
python scripts\validate_ea_output.py --once --from-db
```

## Log tail Windows

```powershell
# Recommandé
python scripts\v9_ops.py log

# Équivalent PowerShell natif
Get-Content -Path D:\Projet\V9\logs\v9_capture.log -Wait -Tail 20
```

## Diagnostic rapide

```powershell
# 1. Vérifier que le serveur écoute
python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',31685)); print('OK'); s.close()"

# 2. Vérifier les snapshots récents
python -c "
import sqlite3
c=sqlite3.connect(r'D:\Projet\V9\data\v9_forces.db')
r=c.execute('SELECT timestamp,timeframe FROM forces_snapshots ORDER BY timestamp DESC LIMIT 3').fetchall()
for ts,tf in r: print(f'{ts} {tf}')
c.close()
"

# 3. Vérifier l'âge du dernier snapshot (secondes)
python -c "
from datetime import datetime,timezone
import sqlite3
c=sqlite3.connect(r'D:\Projet\V9\data\v9_forces.db')
ts=c.execute('SELECT MAX(timestamp) FROM forces_snapshots').fetchone()[0]
c.close()
age=(datetime.now(timezone.utc)-datetime.fromisoformat(ts.replace('Z','+00:00'))).total_seconds()
print(f'Dernier snapshot age: {age:.0f}s')
"

# 4. Vérifier les logs en temps réel
python scripts\v9_ops.py log
```

## Problèmes connus

| Symptôme | Cause | Solution |
|---|---|---|
| Port 31685 occupé au démarrage | Process stale sans PID file | `python scripts\v9_ops.py stop` puis `python scripts\v9_ops.py start` |
| Aucun snapshot après 2 minutes | EA pas déployé ou port EA ≠ port Python | Vérifier `ServerPort` dans les inputs EA (doit être 31685) |
| validate-ea : `WinError 10013` | Le serveur de capture occupe déjà le port | Utiliser `v9_ops.py validate-ea` (fallback DB auto) ou `--from-db` |
| Snapshots M1 stale=60% | Seuil STALE_GATE=5s, intervalle M1 ticking=~60s | **Normal** — le taux de stale historique inclut le replay initial. Les derniers snapshots sont frais (dashboard montre 0%). |
| Pas de signal/décision | Régime NEUTRE majoritaire (62%), `aucune_action` systématique | **Normal** en session Londres calme. Pas une anomalie. |
| ANTAGONIST_NODE à 0% | H1 et M5 alignés (même direction) | **Normal** — le principe exige une divergence H1≠M5. |
| COALITION_NODE <0.3% | Conditions `state=ACCUMULATING/LEAKING` + `coalition_strength>=0.5` rarement réunies | **Normal** — le hit rate augmentera sur des marchés à plus forte volatilité. |
| `regenerate_chain.py` refuse de s'exécuter | DB dérivée non vide | Ajouter `--replace-derived` pour purger puis régénérer |

## Pitfalls

- ❌ Confondre "pipeline actif" (serveur qui écoute) avec "flux live actif" (EA connecté). Vérifier avec `python scripts\v9_ops.py log` — un nouveau snapshot doit apparaître dans les 60s.
- ❌ Utiliser `deploy_v9.py` directement au lieu de `v9_ops.py` — `v9_ops.py` est le point d'entrée unique depuis `89cc425`.
- ❌ Attendre qu'un principe se déclenche immédiatement après un restart — les node_rule sont scopés M5+. Attendre l'arrivée d'un snapshot M5+ (prochaine bougie clôturée).
- ❌ Oublier de redémarrer le serveur après une modification de `orchestrator.py` (zone_detector, etc.) — utiliser `python scripts\v9_ops.py restart`.
- ❌ Appliquer les suggestions de `--analyze` sans attendre n≥200 snapshots M5+ purement live. Les suggestions mélangent replay + live — les distributions sont faussées par la majorité replay.
- ❌ Surveiller le stale M1 comme indicateur de santé du flux — le stale M1 historique est ~60% à cause du replay initial. Surveiller les 10 derniers snapshots M1 (stale ~0-1/10) comme indicateur réel.
- ❌ Confondre la machine de capture (D:\Projet\V9) avec la machine de trading MT4. Les EA doivent être déployés sur la machine qui exécute MT4/MT5. Le serveur Python écoute sur 127.0.0.1 — si MT4 est sur une autre machine, le bind doit être sur 0.0.0.0.