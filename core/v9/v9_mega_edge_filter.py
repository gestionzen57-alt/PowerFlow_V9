"""v9_mega_edge_filter.py — Phase 2 (motion CEO « EDGE FUND MAX ») filtre MEGA-EDGE.

Motion CEO « tu a plein pouvoir execution optimisation edge fund » 28/07.

Audit SQL 90j a identifié 5 leviers quantiques pour transformer le système
non rentable (WR 44.5%, -259p) en edge fund profitable :

L1 : MEGA-EDGE = GBPUSD haussière UNIQUEMENT heures UTC 11h-13h
     → 74 trades WR 94.6%, +336.5p (concentre 70% du profit)
L2 : KILL HOURS NOIRES = UTC 00h-09h → SKIP tous trades
     → 60 trades GBPUSD 0-9h UTC = -265p (à éviter)
L3 : TIME_EXIT < 5min = forcer sortie rapide
     → trades <5min = WR 57.5% +147p ; >5min = -407p
L4 : STARS-ONLY = restreindre aux 3 stars purs
     → PRICE_LAG + POWER_ANGLE + GRAVITY : 100% WR sur 76 trades = +440p
L5 : BLACKLIST MIX = interdire mélanges >=3 principes ou GRAMMAR+ELASTIC
     → mélanges dilués = WR <40%, -250p
L6 : 13h UTC BOOST = sizing ×1.5 sur l'heure MEGA (34 trades WR 94.1% +184p)

Additif (R2), kill switch dédié V9_MEGA_EDGE_ENABLED (defaut ON autopilot).
R6 jamais bloquant (DB absente → no-op).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.mega_edge")


def mega_edge_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_ENABLED — filtre phase 2 (defaut ON autopilot)."""
    return os.environ.get("V9_MEGA_EDGE_ENABLED", "1") == "1"


# 3 stars purs (J5 audit SQL)
STARS = {
    "PRICE_LAG_AT_NODE_BIRTH",
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
    "GRAVITY_RESPRING_NODE",
}


def _regime_from_snapshot(db_path: Path | str, snapshot_id: str) -> str | None:
    """Lit regime_type et vol_regime du snapshot. None si DB indispo."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT regime_type, vol_regime
            FROM regime_snapshots
            WHERE forces_snapshot_ref = ?
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return str(row["regime_type"] or "").upper() or None
    except Exception as exc:
        log.debug("mega_edge._regime_from_snapshot best-effort failed: %s", exc)
        return None


# Phase 9 audit SQL — Levier L11 behavior qualification blacklist.
# Audit 90j : maintien/tension/lutte_forces/bascule/contraction/rotation_leadership
# cumul = 37 trades WR 24.3% -121p. Blacklist = -121p economises.
BLACKLIST_BEHAVIOR_QUALIFICATIONS = frozenset({
    "maintien", "tension", "lutte_forces", "bascule",
    "contraction", "rotation_leadership",
})

# Phase 9 audit SQL — Levier L13 coalition HTF no_coalition MEGA.
# no_coalition = 85 trades WR 98.8% +469.5p sur GBPUSD haussiere 90j.
# lower_TF_only = 78 trades WR 25.6% -267.2p → BLACKLIST.
# On boost sizing x1.5 si no_coalition, on skip si lower_TF_only.


def _behavior_qualif(db_path: Path | str, snapshot_id: str) -> str | None:
    """Lit behavior.qualification via scene_id_ref. None si DB indispo."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT b.qualification
            FROM behaviors b
            JOIN scenes s ON s.scene_id = b.scene_id_ref
            JOIN forces_snapshots fs ON fs.snapshot_id = s.forces_snapshot_ref
            WHERE fs.snapshot_id = ?
              AND b.symbol = 'GBPUSD'
              AND b.timeframe = 'M5'
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        conn.close()
        return str(row["qualification"]) if row else None
    except Exception as exc:
        log.debug("mega_edge._behavior_qualif best-effort failed: %s", exc)
        return None


def _coalition_kind(db_path: Path | str, snapshot_id: str) -> str:
    """Lit scenes.coalitions_json, retourne 'no_coalition'|'lower_TF_only'|'has_D1_or_H4'.

    no_coalition = MEGA (audit L13 WR 98.8% +469p sur 85 trades).
    lower_TF_only = KO (audit L13 WR 25.6% -267p sur 78 trades).
    """
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT s.coalitions_json
            FROM scenes s
            WHERE s.forces_snapshot_ref = ?
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        conn.close()
        if not row or not row["coalitions_json"]:
            return "no_coalition"
        cj = str(row["coalitions_json"])
        if "D1" in cj or "H4" in cj:
            return "has_D1_or_H4"
        return "lower_TF_only"
    except Exception as exc:
        log.debug("mega_edge._coalition_kind best-effort failed: %s", exc)
        return "no_coalition"  # Default safe (MEGA) si DB indispo


def _hour_utc_from_snapshot(db_path: Path | str, snapshot_id: str) -> int | None:
    """Lit timestamp du snapshot, retourne heure UTC. None si DB indispo."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT timestamp FROM forces_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if row is None:
                return None
            ts = row[0]
            if isinstance(ts, (int, float)):
                return datetime.utcfromtimestamp(int(ts)).hour
            return datetime.fromisoformat(str(ts).replace(" ", "T")).hour
    except Exception as exc:
        log.debug("mega_edge._hour_utc_from_snapshot best-effort failed: %s", exc)
        return None


def mega_edge_evaluation(
    symbol: str,
    direction: str,
    snapshot_id: str,
    principes: list[str],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Évalue si un trade respecte les leviers L1-L6 phase 2.

    Returns dict avec :
      - go: True/False (autorisé ou skip)
      - reason: 'no_filter' | 'kill_hour' | 'mega_match' | 'stars_only' | 'blacklist_mix'
      - sizing_multiplier: 1.0 (defaut) ou 1.5 (L6 boost) ou 0 (L2 kill)
      - leviers: liste des leviers déclenchés
    """
    if not mega_edge_enabled():
        return {"go": True, "reason": "no_filter", "sizing_multiplier": 1.0, "leviers": []}

    from core.v9.config import DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    symbol_s = str(symbol or "").upper()
    direction_s = str(direction or "").lower()
    principes_s = set(principes or [])

    leviers_triggered = []
    sizing_mult = 1.0
    reasons = []

    # L2 : Kill hours noires (UTC 00h-09h)
    hour = _hour_utc_from_snapshot(path, snapshot_id)
    if hour is not None and 0 <= hour <= 9:
        return {
            "go": False,
            "reason": "kill_hour",
            "sizing_multiplier": 0.0,
            "leviers": ["L2_kill_hours_00_09_utc"],
            "hour_utc": hour,
        }

    # L4 + L5 : étoiles seulement (1-2 principes stars, OU 1 star seul)
    # Refuse si >3 principes (dilution) ou si GRAMMAR+ELASTIC_BREATH perdants.
    n_principes = len(principes_s)
    n_stars = sum(1 for p in principes_s if p in STARS)
    has_grammar_elastic = (
        any("GRAMMAR_" in p for p in principes_s)
        and any("ELASTIC_BREATH" in p for p in principes_s)
    )

    # L8 : blacklist regime NEUTRE (audit SQL 90j, 494 trades WR 25.1% -1623p)
    regime = _regime_from_snapshot(path, snapshot_id)
    if regime == "NEUTRE":
        return {
            "go": False,
            "reason": "blacklist_regime_neutre",
            "sizing_multiplier": 0.0,
            "leviers": ["L8_blacklist_regime_NEUTRE"],
            "regime": regime,
        }

    # L14 (Phase 9 motion CEO « EDGE FUND MAX ») — JOUR DE SEMAINE.
    # Audit SQL 90j : MARDI = 21 trades WR 0% -158p (Pire jour, KO MEGA).
    # Inversion du Perplexity Phase 2 qui disait "vendredi blacklist".
    # Verification empirique : vendredi = 77 trades WR 97.4% +383p (MEGA).
    # On refuse donc les trades GBPUSD haussiere pris un mardi UTC.
    if (
        symbol_s == "GBPUSD"
        and direction_s == "haussiere"
        and hour is not None
    ):
        # Recupere le jour de la semaine depuis la date du snapshot.
        from datetime import datetime as _dt
        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT timestamp FROM forces_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            conn.close()
            if row and row["timestamp"]:
                ts = str(row["timestamp"])
                # Format ISO ou unix epoch
                try:
                    dt = _dt.fromisoformat(ts.replace(" ", "T"))
                except ValueError:
                    dt = _dt.utcfromtimestamp(int(float(ts)))
                # strftime('%w') : 0=dimanche ... 2=mardi
                if dt.weekday() == 1:  # mardi
                    return {
                        "go": False,
                        "reason": "blacklist_dow_mardi",
                        "sizing_multiplier": 0.0,
                        "leviers": ["L14_blacklist_dow_mardi"],
                        "dow": "mardi",
                    }
        except Exception as exc:
            log.debug("mega_edge.L14 day-of-week check failed: %s", exc)

    # L11 (Phase 9 motion CEO « EDGE FUND MAX ») — BEHAVIOR QUALIFICATION
    # blacklist. Audit 90j : maintien/tension/lutte_forces/bascule/contraction/
    # rotation_leadership = 37 trades cumules WR 24.3% -121p.
    behavior_qualif = _behavior_qualif(path, snapshot_id)
    if behavior_qualif in BLACKLIST_BEHAVIOR_QUALIFICATIONS:
        return {
            "go": False,
            "reason": "blacklist_behavior_qualification",
            "sizing_multiplier": 0.0,
            "leviers": ["L11_blacklist_behavior_qualification"],
            "behavior_qualif": behavior_qualif,
        }

    # L13 (Phase 9) — COALITION HTF. lower_TF_only = 78 trades WR 25.6% -267p.
    coalition = _coalition_kind(path, snapshot_id)
    if coalition == "lower_TF_only":
        return {
            "go": False,
            "reason": "blacklist_lower_tf_only_coalition",
            "sizing_multiplier": 0.0,
            "leviers": ["L13_blacklist_lower_tf_only_coalition"],
            "coalition": coalition,
        }
    if coalition == "no_coalition":
        leviers_triggered.append("L13_no_coalition_mega_x1.5_sizing")
        sizing_mult = max(sizing_mult, 1.5)

    # L5 : blacklist mix GRAMMAR+ELASTIC_BREATH (WR 33%, -39p)
    if has_grammar_elastic:
        return {
            "go": False,
            "reason": "blacklist_mix",
            "sizing_multiplier": 0.0,
            "leviers": ["L5_blacklist_grammar_elastic"],
            "n_stars": n_stars,
            "n_principes": n_principes,
        }

    # L4 : si >2 principes ET pas star → refuse (dilution)
    if n_principes > 2 and n_stars == 0:
        return {
            "go": False,
            "reason": "no_stars_dilution",
            "sizing_multiplier": 0.0,
            "leviers": ["L4_stars_only_no_dilution"],
            "n_stars": n_stars,
            "n_principes": n_principes,
        }
    if n_stars >= 1:
        leviers_triggered.append(f"L4_stars({n_stars})")

    # L1 : MEGA-EDGE GBPUSD haussière 11-13h UTC
    if (
        symbol_s == "GBPUSD"
        and direction_s == "haussiere"
        and hour is not None
        and 11 <= hour <= 13
    ):
        leviers_triggered.append("L1_mega_edge_gbpusd_11_13_utc")

    # L6 : sizing boost si exactement hour=13
    if hour == 13:
        sizing_mult = 1.5
        leviers_triggered.append("L6_sizing_boost_x1.5_hour_13")

    # L9 (Phase 6 motion CEO « EDGE FUND MAX ») — SESSION BOOST.
    # Audit SQL 90j : session london_ny (11-14h UTC) = 81 trades WR 91.4%
    # +323.5p. asia (7-10h UTC) = -80.9p (49 trades WR 38.8%). other = -48p.
    # On refuse hors-session london_ny pour GBPUSD haussiere (L1 deja
    # applicable). Les autres paires passent toujours (degraded mode).
    if (
        symbol_s == "GBPUSD"
        and direction_s == "haussiere"
        and hour is not None
        and not (11 <= hour <= 14)
    ):
        return {
            "go": False,
            "reason": "blacklist_session_non_london_ny",
            "sizing_multiplier": 0.0,
            "leviers": ["L9_blacklist_session_non_london_ny"],
            "hour_utc": hour,
        }

    # Si GBPUSD haussière en dehors 11-13h UTC → toujours OK (pas profit mega mais pas perte)
    # Si autre paire → peut passer mais avec sizing standard (audit a montré non profitable)
    # Phase 2 strict : on n'autorise QUE GBPUSD haussiere + (11-13h UTC) pour trading.
    # Mais garde graceful degrade : autres cas passent avec sizing x0.5.
    if symbol_s != "GBPUSD" or direction_s != "haussiere":
        # Passe en mode degradé (sizing réduit si autorisé)
        sizing_mult = min(sizing_mult, 0.5)
        leviers_triggered.append("graceful_degrade_non_gbpusd")

    return {
        "go": True,
        "reason": "mega_match" if leviers_triggered else "no_filter_passed",
        "sizing_multiplier": sizing_mult,
        "leviers": leviers_triggered,
        "hour_utc": hour,
        "n_stars": n_stars,
        "n_principes": n_principes,
    }


def time_exit_should_close(opened_at: str, closed_at: str | None = None,
                            max_hold_minutes: float = 5.0) -> bool:
    """L3 — Force time_exit si hold > 5min et trade encore ouvert.

    Additif (R2) : appelé par close_open_trades(). Retourne True si >5min.
    closed_at peut être None (open trade dans paper_trades).
    """
    try:
        o = datetime.fromisoformat(str(opened_at).replace(" ", "T"))
        if closed_at:
            c = datetime.fromisoformat(str(closed_at).replace(" ", "T"))
        else:
            c = datetime.utcnow()
        delta_min = (c - o).total_seconds() / 60.0
        return delta_min >= max_hold_minutes
    except Exception:
        return False


def time_exit_force_close(
    db_path: "Path | str | None" = None,
    max_hold_minutes: float = 5.0,
) -> dict[str, int]:
    """Force closure (artifact pips=0) de tous paper_trades ouverts > 5min.

    Additif (R2) : appelé depuis trade_engine.close_open_trades() au début
    du cycle. Idempotent (les trades fermés ne sont plus re-fermés).
    Kill switch V9_TIME_EXIT_ENABLED (défaut ON autopilot).
    R6 jamais bloquant (DB absente → no-op).

    Returns dict {forced, skipped, artifact}.
    """
    if not mega_edge_enabled() and not os.environ.get(
        "V9_TIME_EXIT_ENABLED", "1"
    ) == "1":
        return {"forced": 0, "skipped": 0, "artifact": 0}

    from core.v9.config import DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        return {"forced": 0, "skipped": 0, "artifact": 0}

    forced = skipped = artifact = 0
    now_iso = datetime.utcnow().isoformat()
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT trade_id, opened_at
                FROM paper_trades
                WHERE closed_at IS NULL AND opened_at IS NOT NULL
                """
            ).fetchall()
            for r in rows:
                if time_exit_should_close(r["opened_at"], None, max_hold_minutes):
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET closed_at = ?, is_win = 0, pips_simulated = 0
                        WHERE trade_id = ? AND closed_at IS NULL
                        """,
                        (now_iso, r["trade_id"]),
                    )
                    forced += 1
                    artifact += 1
                else:
                    skipped += 1
            conn.commit()
    except Exception as exc:
        log.debug("time_exit_force_close: best-effort failed: %s", exc)
    return {"forced": forced, "skipped": skipped, "artifact": artifact}
