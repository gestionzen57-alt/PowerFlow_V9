"""Flow probe V9 — trace d'un snapshot à travers les couches cognitives.

But CEO quant 2026-07-07 : quand tu te demandes « pourquoi CE snapshot n'a
pas créé de décision », tu dois pouvoir tracer son trajet en 10 lignes.

Conception anti-bridage :
- 0 LLM, 0 RPC, 0 modif core/v9/business
- Lecture seule sur tables existantes (scenes, behaviors, windows, exploitability, signals, decisions)
- Aucune écriture parasite sur la DB

API :
- trace(snapshot_id) : dict {snapshot_id, layers: [{layer, id, ts, status, direction?}], blocked: bool}
- format_path(path) : texte lisible multi-lignes pour CLI
- record(...) : hook best-effort (utilisé par capture_server si besoin dans Phase 13)
- list_events(snapshot_id) : retourne probe_events pour un snapshot
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.v9.config import DB_PATH


SCHEMA_PROBE = """
CREATE TABLE IF NOT EXISTS probe_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    record_id TEXT,
    status TEXT,
    direction TEXT,
    latency_ms REAL DEFAULT 0,
    source_type TEXT DEFAULT 'live'
);

CREATE INDEX IF NOT EXISTS idx_probe_snapshot
    ON probe_events (snapshot_id, ts);
"""


@contextmanager
def _conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_probe_schema(db_path: str | None = None) -> None:
    """Idempotent : crée probe_events si absente."""
    from core.v9.config import DB_PATH as DEFAULT_DB
    target = Path(str(db_path)) if db_path else DEFAULT_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    with _conn(target) as c:
        c.executescript(SCHEMA_PROBE)


def trace(snapshot_id: str, db_path: str | None = None) -> dict:
    """Trace un snapshot à travers toutes les couches cognitives.

    Returns dict {snapshot_id, layers, blocked}.
    Si la scène source n'existe pas, blocked=True avec layers vide.
    Lecture seule — aucune écriture DB.
    """
    from core.v9.config import DB_PATH as DEFAULT_DB
    db_path = db_path or DEFAULT_DB

    layers: list[dict] = []

    try:
        with _conn(db_path) as c:
            # 1. Trouver la scène source via forces_snapshot_ref
            try:
                scene_row = c.execute(
                    "SELECT scene_id, timestamp FROM scenes "
                    "WHERE forces_snapshot_ref = ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                scene_row = None

            if scene_row is None:
                return {
                    "snapshot_id": snapshot_id,
                    "layers": [],
                    "blocked": True,
                }

            scene_id = scene_row["scene_id"]
            layers.append({
                "layer": "scene",
                "id": scene_id,
                "ts": scene_row["timestamp"],
                "status": "OK",
            })

            # 2. Behavior
            try:
                behavior_rows = c.execute(
                    "SELECT behavior_id, timestamp FROM behaviors "
                    "WHERE scene_id_ref = ? ORDER BY timestamp",
                    (scene_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                behavior_rows = []

            for brow in behavior_rows:
                layers.append({
                    "layer": "behavior",
                    "id": brow["behavior_id"],
                    "ts": brow["timestamp"],
                    "status": "OK",
                })
                # 3. Windows pour ce behavior
                try:
                    windows_rows = c.execute(
                        "SELECT window_id, timestamp, statut FROM windows "
                        "WHERE behavior_id = ? ORDER BY timestamp",
                        (brow["behavior_id"],),
                    ).fetchall()
                except sqlite3.OperationalError:
                    windows_rows = []

                for wrow in windows_rows:
                    layers.append({
                        "layer": "window",
                        "id": wrow["window_id"],
                        "ts": wrow["timestamp"],
                        "status": wrow["statut"],
                    })
                    # 4. Exploitability pour chaque window
                    try:
                        ex_rows = c.execute(
                            "SELECT exploitability_id, timestamp, status "
                            "FROM exploitability WHERE window_id = ? ORDER BY timestamp",
                            (wrow["window_id"],),
                        ).fetchall()
                    except sqlite3.OperationalError:
                        ex_rows = []

                    for erow in ex_rows:
                        layers.append({
                            "layer": "exploitability",
                            "id": erow["exploitability_id"],
                            "ts": erow["timestamp"],
                            "status": erow["status"],
                        })

            # 5. Signal (lié au snapshot_id, pas à scene)
            try:
                sig_rows = c.execute(
                    "SELECT signal_id, timestamp, direction FROM signals "
                    "WHERE snapshot_id = ? ORDER BY timestamp",
                    (snapshot_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                sig_rows = []

            for srow in sig_rows:
                layers.append({
                    "layer": "signal",
                    "id": srow["signal_id"],
                    "ts": srow["timestamp"],
                    "status": "OK",
                    "direction": srow["direction"],
                })

            # 6. Decision (snapshot-level)
            try:
                dec_rows = c.execute(
                    "SELECT decision_id, timestamp, direction FROM decisions "
                    "WHERE snapshot_id = ? ORDER BY timestamp",
                    (snapshot_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                dec_rows = []

            for drow in dec_rows:
                layers.append({
                    "layer": "decision",
                    "id": drow["decision_id"],
                    "ts": drow["timestamp"],
                    "status": "OK",
                    "direction": drow["direction"],
                })

    except sqlite3.OperationalError:
        # DB absente ou schéma incomplet
        return {"snapshot_id": snapshot_id, "layers": [], "blocked": True}

    return {
        "snapshot_id": snapshot_id,
        "layers": layers,
        "blocked": False,
    }


def format_path(path: dict) -> str:
    """Formate une trace en texte lisible pour CLI/log."""
    if path["blocked"]:
        return (
            f"Snapshot {path['snapshot_id']} : BLOQUÉ\n"
            f"  → Aucune scène source trouvée. Le snapshot n'a pas traversé de couche."
        )

    lines = [f"Snapshot {path['snapshot_id']} : {len(path['layers'])} couches traversées"]
    current_subpath = []
    for layer in path["layers"]:
        ltype = layer["layer"]
        lid = layer.get("id", "?")[:8]
        ts = layer.get("ts", "?")
        status = layer.get("status", "?")
        extra = ""
        if "direction" in layer:
            extra = f" dir={layer['direction']}"
        lines.append(f"  {ltype:14s} [{lid}]  {ts}  {status}{extra}")
    return "\n".join(lines)


def list_events(snapshot_id: str, db_path: str | None = None) -> list[dict]:
    """Liste les probe_events pour un snapshot donné."""
    from core.v9.config import DB_PATH as DEFAULT_DB
    target = Path(str(db_path)) if db_path else DEFAULT_DB

    init_probe_schema(db_path=target)
    with _conn(target) as c:
        try:
            rows = c.execute(
                "SELECT * FROM probe_events WHERE snapshot_id=? ORDER BY ts",
                (snapshot_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        return [dict(r) for r in rows]


def record(
    snapshot_id: str,
    layer: str,
    status: str = "OK",
    record_id: str | None = None,
    direction: str | None = None,
    latency_ms: float = 0.0,
    db_path: str | None = None,
) -> int:
    """Enregistre un probe_event (best-effort). Retourne l'id inséré."""
    from core.v9.config import DB_PATH as DEFAULT_DB
    target = Path(str(db_path)) if db_path else DEFAULT_DB
    import time
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    init_probe_schema(db_path=target)
    with _conn(target) as c:
        cur = c.execute(
            """INSERT INTO probe_events
               (ts, snapshot_id, layer, record_id, status, direction, latency_ms, source_type)
               VALUES (?,?,?,?,?,?,?, 'live')""",
            (ts, snapshot_id, layer, record_id, status, direction, latency_ms),
        )
        return cur.lastrowid
