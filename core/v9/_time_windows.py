"""_time_windows.py — Fonctions communes pour les fenêtres temporelles V9.

Centralise le calcul des sessions forex et le split aujourd'hui / hier / 24h
glissantes utilisé par les scripts de présentation (health, brief, dashboard).

Source unique de vérité pour les sessions dans les scripts de présentation.
Les limites UTC sont :
  - ASIE        : 00-07
  - LONDRES     : 07-12
  - OVERLAP     : 12-16
  - NEW_YORK    : 16-21
  - AFTER_HOURS : 21-24

Doctrine : R6 (ne jamais lever — toute erreur DB → structure vide),
R18 (zéro LLM), R22 (lecture seule DB mode=ro strict).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ── Sessions forex ──────────────────────────────────────────────────────────

_SESSION_RANGES = [
    (0, 7, "ASIE"),
    (7, 12, "LONDRES"),
    (12, 16, "OVERLAP"),
    (16, 21, "NEW_YORK"),
    (21, 24, "AFTER_HOURS"),
]


def get_session_now(utc_dt: datetime | None = None) -> str:
    """Session forex active selon l'heure UTC.

    ASIE        : 00-07 UTC
    LONDRES     : 07-12 UTC
    OVERLAP     : 12-16 UTC
    NEW_YORK    : 16-21 UTC
    AFTER_HOURS : 21-24 UTC
    """
    h = (utc_dt or datetime.now(timezone.utc)).hour
    for lo, hi, name in _SESSION_RANGES:
        if lo <= h < hi:
            return name
    return "AFTER_HOURS"


def get_session_full_label(session: str) -> str:
    """Label complet avec emojis et plage horaire."""
    labels = {
        "ASIE": "ASIE \U0001f30f (00-07 UTC)",
        "LONDRES": "LONDRES \U0001f1ec\U0001f1e7 (07-12 UTC)",
        "OVERLAP": "OVERLAP LONDRES-NY \U0001f1ec\U0001f1e7\U0001f1fa\U0001f1f8 (12-16 UTC)",
        "NEW_YORK": "NEW YORK \U0001f1fa\U0001f1f8 (16-21 UTC)",
        "AFTER_HOURS": "AFTER-HOURS \U0001f319 (21-24 UTC)",
    }
    return labels.get(session, session)


# ── Split aujourd'hui / hier / 24h glissantes ───────────────────────────────

def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Connexion SQLite read-only (URI mode=ro)."""
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _aggregate_row(row) -> dict:
    """Transforme un row (n, wins, total_pips) en dict structuré."""
    n, wins, total_pips = row[0] or 0, row[1] or 0, row[2] or 0.0
    return {
        "n": n,
        "wr_pct": round(100.0 * wins / n, 1) if n > 0 else 0.0,
        "pips": round(total_pips, 1),
    }


def get_today_yesterday_split(db_path: Path) -> dict:
    """Split aujourd'hui vs hier (DATE UTC) sur la table ``decisions``.

    Filtre ``resolution_strategy='DYNAMIC'`` et ``is_win IS NOT NULL``.

    Returns:
        Dict avec clés ``today``, ``yesterday``, ``session_now``.
        Chaque sous-dict contient ``date``, ``n``, ``wr_pct``, ``pips``.
        ``today`` contient en plus ``session_now``.
    """
    if not Path(db_path).exists():
        return {
            "today": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0, "session_now": get_session_now()},
            "yesterday": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0},
            "error": "DB absente",
        }
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error:
        return {
            "today": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0, "session_now": get_session_now()},
            "yesterday": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0},
            "error": "DB inaccessible",
        }

    try:
        today_row = conn.execute(
            """
            SELECT COUNT(*), SUM(is_win), ROUND(SUM(resolution_pips), 1)
            FROM decisions
            WHERE DATE(timestamp) = DATE('now')
              AND is_win IS NOT NULL
              AND resolution_strategy = 'DYNAMIC'
            """
        ).fetchone()

        yesterday_row = conn.execute(
            """
            SELECT COUNT(*), SUM(is_win), ROUND(SUM(resolution_pips), 1)
            FROM decisions
            WHERE DATE(timestamp) = DATE('now', '-1 day')
              AND is_win IS NOT NULL
              AND resolution_strategy = 'DYNAMIC'
            """
        ).fetchone()

        today_date = conn.execute("SELECT DATE('now')").fetchone()[0]
        yesterday_date = conn.execute("SELECT DATE('now', '-1 day')").fetchone()[0]
    except sqlite3.Error:
        return {
            "today": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0, "session_now": get_session_now()},
            "yesterday": {"date": None, "n": 0, "wr_pct": 0.0, "pips": 0.0},
            "error": "Query échouée",
        }
    finally:
        conn.close()

    today_agg = _aggregate_row(today_row)
    today_agg["date"] = today_date
    today_agg["session_now"] = get_session_now()

    yesterday_agg = _aggregate_row(yesterday_row)
    yesterday_agg["date"] = yesterday_date

    return {
        "today": today_agg,
        "yesterday": yesterday_agg,
    }


def get_24h_rolling(db_path: Path) -> dict:
    """Fenêtre 24h glissantes sur la table ``decisions``.

    Returns:
        Dict avec ``n``, ``wr_pct``, ``pips``.
    """
    if not Path(db_path).exists():
        return {"n": 0, "wr_pct": 0.0, "pips": 0.0, "error": "DB absente"}
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error:
        return {"n": 0, "wr_pct": 0.0, "pips": 0.0, "error": "DB inaccessible"}

    try:
        row = conn.execute(
            """
            SELECT COUNT(*), SUM(is_win), ROUND(SUM(resolution_pips), 1)
            FROM decisions
            WHERE timestamp > datetime('now', '-1 day')
              AND is_win IS NOT NULL
              AND resolution_strategy = 'DYNAMIC'
            """
        ).fetchone()
    except sqlite3.Error:
        return {"n": 0, "wr_pct": 0.0, "pips": 0.0, "error": "Query échouée"}
    finally:
        conn.close()

    return _aggregate_row(row)


def get_intraday_by_session(db_path: Path) -> list[dict]:
    """Performance intraday par session forex pour aujourd'hui (UTC).

    Returns:
        Liste de dicts triés par ordre chronologique des sessions,
        chacun avec ``session``, ``n``, ``wr_pct``, ``pips``.
        Sessions sans trades sont omises.
    """
    if not Path(db_path).exists():
        return []
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error:
        return []

    try:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 7  THEN 'ASIE'
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 12 THEN 'LONDRES'
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 16 THEN 'OVERLAP'
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 21 THEN 'NEW_YORK'
                    ELSE 'AFTER_HOURS'
                END AS session,
                COUNT(*) AS n,
                SUM(is_win) AS wins,
                ROUND(SUM(resolution_pips), 1) AS total_pips
            FROM decisions
            WHERE DATE(timestamp) = DATE('now')
              AND is_win IS NOT NULL
              AND resolution_strategy = 'DYNAMIC'
            GROUP BY session
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    order = {"ASIE": 0, "LONDRES": 1, "OVERLAP": 2, "NEW_YORK": 3, "AFTER_HOURS": 4}
    result = []
    for r in rows:
        n, wins = r[1] or 0, r[2] or 0
        result.append({
            "session": r[0],
            "n": n,
            "wr_pct": round(100.0 * wins / n, 1) if n > 0 else 0.0,
            "pips": round(r[3] or 0.0, 1),
        })
    result.sort(key=lambda x: order.get(x["session"], 99))
    return result