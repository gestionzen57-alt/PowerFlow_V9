---
name: powerflow-v9-live-snapshot-doctor
category: devops
description: "Diagnostic système V9 — distingue pipeline actif (serveur qui écoute) vs flux live actif (EA connecté envoyant données fraîches). Health check complet : port, EA MT4/MT4, staleness, marché ouvert. Sortie structurée exploitable par alerte Telegram/Discord."
trigger: '"EA connecté ?" | "Le pipeline tourne mais aucun snapshot frais" | "Vérifier flux live" | "Diagnostic live V9"'
tools_needed: [terminal, read_file]
---

## 🎯 OBJECTIF

Répondre en 1 commande à la question critique du profil utilisateur :
**"est-ce que le pipeline V9 reçoit VRAIMENT des données live de l'EA, ou
est-ce que le serveur écoute juste dans le vide ?"**

Cette distinction est cruciale : un port LISTENING ne signifie rien si
l'EA MT4/MT4 n'envoie pas de snapshots. Le check doit prouver le flux
live par :

1. **Snapshots frais** : timestamp `is_closed_bar=1` < seuil de pérémption
   (35s pour M5, 365s pour H1, etc.)
2. **Diff timestamp advancing** : preuve que de nouveaux snapshots
   arrivent (pas de gel)
3. **Scènes récentes** : scènes construites sur snapshots frais
4. **Port listening + EA configuré** : double check process-level
5. **Marché ouvert** : pas de fausse alerte si Forex fermé

Contexte : `docs/STATE.md` mentionne explicitement "preuve de flux live"
comme exigence opérateur. Aucun script ne fait ce check de manière
systématique et exportable vers Telegram/Discord.

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. Port listening (ne suffit pas — vérifier aussi le flux)
netstat -an | grep 31685 | grep LISTENING


> **Note CEO 2026-07-18** : MT4 = plateforme de lecture de l'indicateur SDI (ticks/volumes spécifiques). MT5 n'est PAS implémenté.

# 2. Dernier snapshot reçu par timeframe
sqlite3 data/v9_forces.db "
SELECT timeframe, MAX(timestamp), MAX(server_time), COUNT(*),
       printf('%d sec ago', CAST((julianday('now') - julianday(MAX(timestamp))) * 86400 AS INT)) AS age
FROM forces_snapshots WHERE stale = 0
GROUP BY timeframe;"

# 3. Process Python/EA actif
tasklist | grep -iE "terminal64\.exe|python\.exe|java\.exe" | head -5
```

## 🛠️ SCRIPT `scripts/live_snapshot_doctor.py`

### Étape 1 — Health check port

```python
# scripts/live_snapshot_doctor.py
import socket
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path("data/v9_forces.db")
LISTEN_PORT = 31685  # core/v9/config.py

def check_port_listening(port: int = LISTEN_PORT, host: str = "127.0.0.1") -> dict:
    """Vérifie que le serveur V9 écoute sur le port configuré."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect((host, port))
        return {"status": "listening", "host": host, "port": port}
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return {"status": "down", "host": host, "port": port, "error": str(e)}
    finally:
        sock.close()
```

### Étape 2 — Vérification snapshots frais (preuve de flux live)

```python
# Seuils de staleness par TF (mirror de core/v9/config.py:STALE_THRESHOLDS_MS)
STALE_THRESHOLDS_S = {
    "M1": 5, "M5": 35, "M15": 95, "M30": 185,
    "H1": 365, "H4": 1450, "D1": 9000,
}


def check_fresh_snapshots(db_path: Path = DB_PATH) -> dict:
    """Pour chaque TF, retourne le timestamp du dernier snapshot frais
    (stale=0 ET is_closed_bar=1) et son âge en secondes."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute("""
            SELECT timeframe, MAX(timestamp), COUNT(*),
                   MAX(server_time)
            FROM forces_snapshots
            WHERE stale = 0 AND is_closed_bar = 1
            GROUP BY timeframe
        """).fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    result = {}
    for tf, max_ts, count, max_server in rows:
        if not max_ts:
            continue
        try:
            ts = datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        age_s = (now - ts).total_seconds()
        threshold = STALE_THRESHOLDS_S.get(tf, 3600)
        result[tf] = {
            "last_snapshot_ts": max_ts,
            "age_s": int(age_s),
            "stale_threshold_s": threshold,
            "is_fresh": age_s < threshold,
            "snapshot_count": count,
        }
    return result
```

### Étape 3 — Vérification scènes récentes (preuve d'enrichissement)

```python
def check_recent_scenes(db_path: Path = DB_PATH, lookback_minutes: int = 10) -> dict:
    """Nombre de scènes construites dans les N dernières minutes."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)).isoformat()
        rows = conn.execute("""
            SELECT s.timestamp, s.scene_id, s.coalitions_json, s.risk_assessment_json
            FROM scenes s
            WHERE s.timestamp > ?
            ORDER BY s.timestamp DESC
        """, (cutoff,)).fetchall()
    finally:
        conn.close()

    return {
        "lookback_minutes": lookback_minutes,
        "scenes_built": len(rows),
        "with_coalitions": sum(1 for r in rows if r[2] and r[2] != "[]"),
        "with_risk_assessment": sum(1 for r in rows if r[3] and r[3] != "{}"),
        "latest_scene_ts": rows[0][0] if rows else None,
    }
```

### Étape 4 — Vérification marché ouvert

```python
def check_market_open() -> dict:
    """Vérifie si le marché Forex est ouvert (lundi-vendredi, hors fenêtre
    de fermeture)."""
    from core.v9.config import (
        MARKET_OPEN_UTC_DAY, MARKET_OPEN_UTC_HOUR,
        MARKET_CLOSE_UTC_DAY, MARKET_CLOSE_UTC_HOUR,
    )
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=lundi, 6=dimanche
    hour = now.hour

    # Python: Monday=0, Sunday=6. Config: open_day=6 (Sunday), close_day=4 (Friday).
    # Mapping : Python weekday 6 (Sunday) = config open_day 6.
    is_open = False
    reason = "fermé"
    if weekday == 6 and hour >= MARKET_OPEN_UTC_HOUR:
        is_open = True
        reason = "ouvert (dimanche >= 22h UTC)"
    elif weekday in (0, 1, 2, 3):  # lundi à jeudi
        is_open = True
        reason = "ouvert (lundi-jeudi)"
    elif weekday == 4 and hour < MARKET_CLOSE_UTC_HOUR:
        is_open = True
        reason = "ouvert (vendredi < 22h UTC)"
    elif weekday == 5:
        reason = "fermé (samedi)"

    return {
        "is_open": is_open,
        "weekday": weekday,
        "hour_utc": hour,
        "reason": reason,
    }
```

### Étape 5 — Diagnostic complet + alerte

```python
def run_diagnostic(db_path: Path = DB_PATH,
                   output_format: str = "json") -> dict:
    """Exécute tous les checks et retourne un dict structuré.
    output_format: 'json' (machine) ou 'markdown' (humain)."""
    port_check = check_port_listening()
    fresh = check_fresh_snapshots(db_path)
    recent = check_recent_scenes(db_path)
    market = check_market_open()

    # Verdict global
    any_tf_fresh = any(v.get("is_fresh") for v in fresh.values())
    port_listening = port_check["status"] == "listening"

    if not port_listening:
        verdict = "PIPELINE_DOWN"
        severity = "critical"
        action = "Redémarrer capture_server.py (ou vérifier tasklist python.exe)"
    elif not market["is_open"]:
        verdict = "MARKET_CLOSED"
        severity = "info"
        action = "Aucun flux attendu — vérification reportée à l'ouverture"
    elif not any_tf_fresh:
        verdict = "EA_NOT_CONNECTED"
        severity = "critical"
        action = "EA MT4/MT4 ne pousse pas de snapshots. Vérifier ServerPort=31685 + autorisations EA"
    elif recent["scenes_built"] == 0:
        verdict = "PIPELINE_STUCK"
        severity = "warning"
        action = "Snapshots frais mais aucune scène construite. Vérifier ENABLE_CHAIN dans config.py"
    else:
        verdict = "LIVE_FLOW_OK"
        severity = "ok"
        action = "Aucune action — pipeline opérationnel"

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "severity": severity,
        "action": action,
        "port": port_check,
        "market": market,
        "snapshots_by_tf": fresh,
        "recent_scenes": recent,
    }

    if output_format == "markdown":
        return _format_markdown(result)
    return result


def _format_markdown(result: dict) -> str:
    md = [f"# V9 Live Doctor — {result['timestamp_utc']}\n"]
    md.append(f"## Verdict: **{result['verdict']}** ({result['severity']})")
    md.append(f"_Action_: {result['action']}\n")
    md.append(f"## Port {result['port']['port']}: {result['port']['status']}")
    md.append(f"## Marché: {result['market']['reason']}\n")
    md.append("## Snapshots par TF")
    md.append("| TF | Age (s) | Seuil (s) | Frais | Count |")
    md.append("|---|---:|---:|:---:|---:|")
    for tf, v in result["snapshots_by_tf"].items():
        md.append(f"| {tf} | {v['age_s']} | {v['stale_threshold_s']} | "
                  f"{'✅' if v['is_fresh'] else '❌'} | {v['snapshot_count']} |")
    md.append(f"\n## Scènes récentes (10 min): {result['recent_scenes']['scenes_built']} construites")
    return "\n".join(md) + "\n"
```

### Étape 6 — Cron d'alerte

```bash
# cron toutes les 5 min : alerte si verdict != LIVE_FLOW_OK et severity != info
*/5 * * * * cd /d/Projet/V9 && python scripts/live_snapshot_doctor.py --format json \
  | jq -r 'select(.severity == "critical" or .severity == "warning") | .verdict' \
  | xargs -I{} curl -X POST https://api.telegram.org/bot<TOKEN>/sendMessage \
      -d chat_id=<CHAT_ID> -d text="⚠️ V9 LIVE: {}"
```

## ⚠️ Pièges identifiés (sessions 2026-07-06, S2-S3)

### Bug silencieux « signaux directionnels sans décision » (S2 commit d2f6c60)
- **Symptôme** : `signals` contient `direction != None` mais `decisions.direction IS NOT NULL` reste à 0.
- **Cause** : `DecisionLogger._load_signal()` faisait `ORDER BY id DESC LIMIT 1`. Un signal non-directionnel créé tôt pour le snapshot était élu au lieu du signal directionnel ultérieur.
- **Fix** : `ORDER BY (directionnel AND exploitable) DESC, id DESC` — pertinence décisionnelle d'abord.
- **Diagnostic live** : `SELECT COUNT(*) FROM signals WHERE direction IS NOT NULL AND direction != 'neutre';` doit matcher `SELECT COUNT(DISTINCT snapshot_id) FROM decisions WHERE direction IS NOT NULL;` (modulo rangées legacy).

### Idempotence decisions (S3 commit 3d42b6c)
- **Symptôme** : `decision_id = timestamp+uuid` changeait à chaque `.log()` → `INSERT OR REPLACE` créait une nouvelle rangée (3697 → 3960 sur 3 rejoues).
- **Fix** : `decision_id = uuid5(snapshot_id).hex[:12]` (déterministe) + pré-check `_action_quality()` (preparer_entree=3 > surveiller=2 > observer=1 > aucune_action=0).
- **Vérification live** : `SELECT decision_id, COUNT(*) FROM decisions WHERE snapshot_id=? GROUP BY 1;` doit retourner 1.

### Gardien permanent (S3 commit 85b40fe)
`tests/test_pipeline_end_to_end.py` détecte régression sur les 5 bugs silencieux S2. À ajouter à toute CI : `python -m pytest tests/test_pipeline_end_to_end.py -v` doit rester vert.

---

## ✅ VALIDATION

```bash
# 1. Le script tourne en <2s et produit un verdict clair
time python scripts/live_snapshot_doctor.py --format markdown | head -15

# 2. Le verdict est cohérent avec l'état réel (à comparer avec observations manuelles)
sqlite3 data/v9_forces.db "SELECT MAX(timestamp) FROM forces_snapshots WHERE timeframe='M5' AND stale=0;"

# 3. Les 5 verdicts distincts sont testables (LIVE_FLOW_OK, PIPELINE_DOWN, MARKET_CLOSED, EA_NOT_CONNECTED, PIPELINE_STUCK)
python -c "
from scripts.live_snapshot_doctor import check_port_listening, check_fresh_snapshots, check_market_open
print('port:', check_port_listening())
print('fresh M5:', check_fresh_snapshots().get('M5'))
print('market:', check_market_open())
"
```

## 📚 RÉFÉRENCES

- `core/v9/config.py:STALE_THRESHOLDS_MS` : seuils de staleness par TF (lignes 28-36)
- `core/v9/config.py:LISTEN_PORT` : 31685
- `core/v9/config.py:MARKET_OPEN_UTC_DAY/HOUR` : ouverture dimanche 22h UTC
- Skill connexe : `powerflow-v9-live-ops` (opérations manuelles démarrage/arrêt),
  cette skill est le watchdog automatique
- User profile : exigence explicite de "preuves de flux live (timestamps qui avancent, is_closed_bar=0)"