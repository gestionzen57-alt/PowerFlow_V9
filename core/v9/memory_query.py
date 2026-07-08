"""memory_query.py — Moteur de requête MODE LECTURE V9 (lecture seule).

Répond à « qu'est-ce que tu vois ? » en interrogeant data/v9_forces.db.
Aucune écriture DB, aucune logique de trading, aucune modification du
pipeline existant (core/v9/config.py, orchestrator.py,
principle_engine.py, principles/*.yaml intouchés — nouveau module).

Toutes les fonctions publiques dégradent gracieusement : DB absente ou
table vide -> dict vide / liste vide, jamais d'exception.

Note de conception — `coalition_strength` et `zone_type` n'existent pas
tels quels dans le schéma : `coalition_strength` est dérivé de
`scenes.coalitions_json` (intensite_alignement max, normalisée /50 pour
rester dans [0,1]) ; `zone_type` est dérivé de `scenes.zone_json.structure`
(extension/compression/neutre) — le `zone_type` "naissance/2e_jambe/..."
calculé par principle_engine._detect_zone_type n'est pas persisté par
scène, seulement par évaluation de principe.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.market_calendar import MarketCalendar

# Session marché (market_calendar.current_session) -> libellé FR demandé.
SESSION_LABELS = {
    "tokyo": "ASIE",
    "sydney": "ASIE",
    "london": "LONDON",
    "new_york": "NY",
    "overlap_london_ny": "OVERLAP",
    "closed": "FERME",
}


def _connect(db_path: Path | None = None) -> sqlite3.Connection | None:
    path = db_path or DB_PATH
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _last_row(conn: sqlite3.Connection, table: str) -> dict | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _last_rows(conn: sqlite3.Connection, table: str, limit: int) -> list[dict]:
    if not _table_exists(conn, table):
        return []
    rows = conn.execute(
        f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def _parse_json(raw: Any) -> dict | list:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


# ── 1. État courant ──────────────────────────────────────────────────
def get_current_state(limit_minutes: int = 15, db_path: Path | None = None) -> dict[str, Any]:
    """Dernière ligne de chaque couche de la chaîne cognitive V9."""
    conn = _connect(db_path)
    if conn is None:
        return {}
    try:
        return {
            "scene": _last_row(conn, "scenes"),
            "behavior": _last_row(conn, "behaviors"),
            "window": _last_row(conn, "windows"),
            "exploitability": _last_row(conn, "exploitability"),
            "regime": _last_row(conn, "regime_snapshots"),
            "signals": _last_rows(conn, "signals", 3),
            "decisions": _last_rows(conn, "decisions", 3),
            "principle_evaluations": _last_rows(conn, "principle_evaluations", 5),
            "limit_minutes": limit_minutes,
        }
    finally:
        conn.close()


# ── 2. Scènes similaires ─────────────────────────────────────────────
def _coalition_strength(coalitions_json: Any) -> float:
    coalitions = _parse_json(coalitions_json)
    if not isinstance(coalitions, list) or not coalitions:
        return 0.0
    best = max(float(c.get("intensite_alignement") or 0.0) for c in coalitions)
    return min(best / 50.0, 1.0)


def _batch_regime_types(
    conn: sqlite3.Connection, snapshot_refs: list[str]
) -> dict[str, str | None]:
    """Régime dominant par `forces_snapshot_ref`, en un seul aller-retour DB.

    `regime_snapshots` n'a pas d'index sur `forces_snapshot_ref` (510k+ lignes) :
    une requête par scène candidate transformerait `find_similar_scenes` en
    O(candidats × table complète). On batche donc via IN(...) une fois."""
    if not snapshot_refs:
        return {}
    placeholders = ",".join("?" for _ in snapshot_refs)
    rows = conn.execute(
        f"SELECT forces_snapshot_ref, regime_type, COUNT(*) AS n FROM regime_snapshots "
        f"WHERE forces_snapshot_ref IN ({placeholders}) "
        f"GROUP BY forces_snapshot_ref, regime_type",
        snapshot_refs,
    ).fetchall()
    best: dict[str, tuple[int, str]] = {}
    for r in rows:
        ref = r["forces_snapshot_ref"]
        if ref not in best or r["n"] > best[ref][0]:
            best[ref] = (r["n"], r["regime_type"])
    return {ref: n_type[1] for ref, n_type in best.items()}


def _batch_outcomes(conn: sqlite3.Connection, scene_ids: list[str]) -> dict[str, str]:
    """Dernier outcome (WIN/LOSS) par `scene_id`, batché via IN(...)."""
    if not scene_ids:
        return {}
    placeholders = ",".join("?" for _ in scene_ids)
    rows = conn.execute(
        f"SELECT scene_id, is_win FROM decisions "
        f"WHERE scene_id IN ({placeholders}) AND is_win IS NOT NULL "
        f"ORDER BY id DESC",
        scene_ids,
    ).fetchall()
    outcomes: dict[str, str] = {}
    for r in rows:
        sid = r["scene_id"]
        if sid not in outcomes:  # première rencontre = plus récente (ORDER BY id DESC)
            outcomes[sid] = "WIN" if r["is_win"] else "LOSS"
    return outcomes


def _scene_context(
    conn: sqlite3.Connection,
    scene_row: dict,
    regime_map: dict[str, str | None] | None = None,
    outcome_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Enrichit une ligne `scenes` avec comportement/régime/zone/outcome.

    `regime_map`/`outcome_map` : lookups pré-batchés (cf. `_batch_regime_types`
    / `_batch_outcomes`) pour éviter une requête par scène quand on en score
    des centaines dans `find_similar_scenes`. Absents (None) -> requête directe
    (cas `get_current_state`/scène source, un seul appel)."""
    scene_id = scene_row.get("scene_id")
    cinematique = _parse_json(scene_row.get("cinematique_json"))
    contexte = _parse_json(scene_row.get("contexte_temporel_json"))
    zone = _parse_json(scene_row.get("zone_json"))

    behavior_row = conn.execute(
        "SELECT * FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
        (scene_id,),
    ).fetchone()
    behavior = dict(behavior_row) if behavior_row else None

    window_statut = None
    if behavior:
        w = conn.execute(
            "SELECT statut FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
            (behavior.get("behavior_id"),),
        ).fetchone()
        window_statut = w["statut"] if w else None

    if regime_map is not None:
        regime_type = regime_map.get(scene_row.get("forces_snapshot_ref"))
    else:
        regime_row = conn.execute(
            "SELECT regime_type FROM regime_snapshots WHERE forces_snapshot_ref = ? "
            "GROUP BY regime_type ORDER BY COUNT(*) DESC LIMIT 1",
            (scene_row.get("forces_snapshot_ref"),),
        ).fetchone()
        regime_type = regime_row["regime_type"] if regime_row else None

    if outcome_map is not None:
        outcome = outcome_map.get(scene_id)
    else:
        dec = conn.execute(
            "SELECT is_win FROM decisions WHERE scene_id = ? AND is_win IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (scene_id,),
        ).fetchone()
        outcome = ("WIN" if dec["is_win"] else "LOSS") if dec is not None else None

    return {
        "scene_id": scene_id,
        "timestamp": scene_row.get("timestamp"),
        "session": contexte.get("session") if isinstance(contexte, dict) else None,
        "qualification": behavior.get("qualification") if behavior else None,
        "coalition_strength": _coalition_strength(scene_row.get("coalitions_json")),
        "angle": float((cinematique or {}).get("angle") or 0.0),
        "regime_type": regime_type,
        "zone_type": zone.get("structure") if isinstance(zone, dict) else None,
        "stale": bool(scene_row.get("stale")),
        "window_statut": window_statut,
        "outcome": outcome,
    }


def _similarity_score(source: dict, candidate: dict) -> float:
    score = 0.0
    if source["session"] and source["session"] == candidate["session"]:
        score += 20
    if source["qualification"] and source["qualification"] == candidate["qualification"]:
        score += 20
    if abs(source["coalition_strength"] - candidate["coalition_strength"]) <= 0.1:
        score += 15
    if abs(source["angle"] - candidate["angle"]) <= 5.0:
        score += 15
    if source["regime_type"] and source["regime_type"] == candidate["regime_type"]:
        score += 10
    if source["zone_type"] and source["zone_type"] == candidate["zone_type"]:
        score += 10
    if candidate["stale"]:
        score -= 5
    return score


def find_similar_scenes(
    scene_id: str, limit: int = 5, days_back: int = 7, db_path: Path | None = None
) -> list[dict]:
    """Top `limit` scènes des `days_back` derniers jours les plus proches
    de `scene_id`, par score de similarité combiné (session/comportement/
    coalition/angle/régime/zone, pénalité si stale)."""
    conn = _connect(db_path)
    if conn is None or not _table_exists(conn, "scenes"):
        return []
    try:
        source_row = conn.execute(
            "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
        ).fetchone()
        if source_row is None:
            return []
        source = _scene_context(conn, dict(source_row))

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        candidate_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM scenes WHERE scene_id != ? AND timestamp >= ? "
                "ORDER BY timestamp DESC LIMIT 500",
                (scene_id, cutoff),
            ).fetchall()
        ]

        snapshot_refs = list(
            {r["forces_snapshot_ref"] for r in candidate_rows if r.get("forces_snapshot_ref")}
        )
        candidate_scene_ids = [r["scene_id"] for r in candidate_rows]
        regime_map = _batch_regime_types(conn, snapshot_refs)
        outcome_map = _batch_outcomes(conn, candidate_scene_ids)

        scored = []
        for row in candidate_rows:
            ctx = _scene_context(conn, row, regime_map=regime_map, outcome_map=outcome_map)
            ctx["score"] = _similarity_score(source, ctx)
            scored.append(ctx)

        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:limit]
    finally:
        conn.close()


# ── 3. Historique des déclenchements YAML ────────────────────────────
def get_yaml_triggers_history(hours: int = 24, db_path: Path | None = None) -> dict[str, Any]:
    """Compteurs par principe (count / confiance moyenne / direction
    dominante) sur les `hours` dernières heures, + top 5."""
    conn = _connect(db_path)
    if conn is None or not _table_exists(conn, "principle_evaluations"):
        return {}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT principle_id, direction, confidence FROM principle_evaluations "
            "WHERE triggered = 1 AND timestamp >= ?",
            (cutoff,),
        ).fetchall()

        raw: dict[str, dict[str, Any]] = {}
        for r in rows:
            pid = r["principle_id"]
            entry = raw.setdefault(pid, {"count": 0, "confidences": [], "directions": {}})
            entry["count"] += 1
            if r["confidence"] is not None:
                entry["confidences"].append(r["confidence"])
            direction = r["direction"] or "indetermine"
            entry["directions"][direction] = entry["directions"].get(direction, 0) + 1

        per_principle: dict[str, dict[str, Any]] = {}
        for pid, entry in raw.items():
            confs = entry["confidences"]
            dominante = max(entry["directions"], key=entry["directions"].get) if entry["directions"] else None
            per_principle[pid] = {
                "count": entry["count"],
                "confiance_moyenne": round(sum(confs) / len(confs), 1) if confs else None,
                "direction_dominante": dominante,
            }

        top5 = sorted(per_principle.items(), key=lambda kv: kv[1]["count"], reverse=True)[:5]
        return {
            "hours": hours,
            "per_principle": per_principle,
            "top5": [pid for pid, _ in top5],
        }
    finally:
        conn.close()


# ── 4. Narration marché (5-6 lignes FR) ──────────────────────────────
def get_market_narrative(db_path: Path | None = None) -> str:
    """Synthèse lisible en français de l'état courant du marché vu par V9."""
    now = datetime.now(timezone.utc)
    is_open = MarketCalendar.is_market_open(now)
    session = MarketCalendar.current_session(now)
    marche_label = "OUVERT" if is_open else "FERME"
    session_label = SESSION_LABELS.get(session, session.upper())

    state = get_current_state(db_path=db_path)
    scene = state.get("scene") or {}
    behavior = state.get("behavior") or {}
    window = state.get("window") or {}
    regime = state.get("regime") or {}
    signals = state.get("signals") or []

    zone = _parse_json(scene.get("zone_json"))
    scene_type = zone.get("structure", "inconnue") if isinstance(zone, dict) else "inconnue"
    comportement = behavior.get("qualification") or "inconnu"
    fenetre = window.get("statut") or "absente"
    regime_type = regime.get("regime_type") or "inconnu"
    regime_state = regime.get("cassure_type") or "stable"

    n_signaux = len(signals)
    n_haussier = sum(1 for s in signals if s.get("direction") == "haussiere")
    n_baissier = sum(1 for s in signals if s.get("direction") == "baissiere")

    yaml_hist = get_yaml_triggers_history(db_path=db_path)
    top_ids = yaml_hist.get("top5", [])[:2]
    top_str = ", ".join(
        f"{pid} ({yaml_hist['per_principle'][pid]['count']} fois)" for pid in top_ids
    ) or "aucun"

    similar_line = "Mémoire : aucune scène courante à comparer"
    if scene.get("scene_id"):
        similar = find_similar_scenes(scene["scene_id"], db_path=db_path)
        outcomes = [s["outcome"] for s in similar if s.get("outcome")]
        dernier = outcomes[0] if outcomes else "inconnu"
        similar_line = (
            f"Mémoire : {len(similar)} scènes similaires trouvées, "
            f"dernier outcome similaire = {dernier}"
        )

    lines = [
        f"Marché {marche_label} — Session {session_label}",
        f"Scène : {scene_type} — {comportement} — {fenetre}",
        f"Régime : {regime_type} — {regime_state}",
        f"Signaux : {n_signaux} directionnels ({n_haussier} haussier / {n_baissier} baissier)",
        f"Top principes : {top_str}",
        similar_line,
    ]
    return "\n".join(lines)
