"""auto_calibrator.py — Recalibrage automatique periodique (Brief Q2, 2026-07-12).

Cycle 24h : relit les scores PrincipleScorer (recompute = lecture des
scores actuels, ne reimplemente pas la logique de scoring), detecte les
sessions DYNAMIC sous 60% WR, propose des ajustements de CONFIANCE_MIN /
NB_PRINCIPES_MIN. AUCUN AUTO-APPLY : toute proposition est journalisee
(cognitive_journal, meme table que meta_agent.py) et notifiee best-effort
sur Telegram (meme pattern que le branching HITL, Brief O3,
_load_telegram_config_safe) — jamais appliquee automatiquement au code.

Meme discipline que PrincipleScorer/TraderMiniWeigher : lecture seule sur
la DB decisions (R18, 0 reseau sauf Telegram best-effort et non-bloquant),
ne leve jamais (regle 6), tolerante a l'absence de donnees.

Kill switch : V9_AUTO_CALIBRATOR_ENABLED (defaut '0' = OFF). Quand OFF,
run_calibration_cycle() reste appelable (utile pour les tests) mais ne
journalise ni ne notifie rien — retourne {'enabled': False}.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import DYNAMIC_PROFILES, infer_session_from_hour
from core.v9.principle_scorer import PrincipleScorer

AUTO_CALIBRATOR_ENABLED_ENV = "V9_AUTO_CALIBRATOR_ENABLED"

# Seuil de significativite statistique par session (coherent avec R30 /
# v9_recalibrate_arbiter.py --min-decisions).
MIN_SAMPLE_SESSION = 30

# Cible WR pour le calcul de delta de proposition (meme logique que
# v9_recalibrate_arbiter.py _propose_adjustment).
TARGET_WR_SESSION = 75.0
WR_LOW_THRESHOLD = 60.0

# Bornes de securite sur les propositions de seuils (jamais appliquees
# automatiquement — juste des garde-fous sur le contenu de la proposition).
CONFIANCE_MIN_BOUNDS = (50, 90)
NB_PRINCIPES_MIN_BOUNDS = (1, 4)

CALIBRATOR_VERSION = "1.0"


def auto_calibrator_enabled() -> bool:
    """Kill switch V9_AUTO_CALIBRATOR_ENABLED (defaut '0' = OFF)."""
    return os.environ.get(AUTO_CALIBRATOR_ENABLED_ENV, "0") == "1"


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = get_connection(Path(db_path) if db_path else DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _session_wr_buckets(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """WR par session sur les decisions DYNAMIC resolues (lecture seule)."""
    rows = conn.execute(
        "SELECT timestamp, is_win, resolution_pips FROM decisions "
        "WHERE action = 'preparer_entree' AND resolution_strategy = 'DYNAMIC' "
        "AND is_win IS NOT NULL"
    ).fetchall()

    buckets: dict[str, dict[str, Any]] = {
        s: {"n": 0, "wins": 0, "pips_total": 0.0} for s in DYNAMIC_PROFILES
    }
    for row in rows:
        try:
            ts = datetime.fromisoformat((row["timestamp"] or "").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue
        session = infer_session_from_hour(ts.hour)
        if session not in buckets:
            continue
        buckets[session]["n"] += 1
        if row["is_win"]:
            buckets[session]["wins"] += 1
        buckets[session]["pips_total"] += row["resolution_pips"] or 0.0

    for session, b in buckets.items():
        n = b["n"]
        b["wr_pct"] = round(b["wins"] / n * 100, 1) if n else None
        b["avg_pips"] = round(b["pips_total"] / n, 2) if n else None
        b["current_scale"] = DYNAMIC_PROFILES[session]["scale"]
    return buckets


def _propose_session_scale_adjustments(buckets: dict[str, dict[str, Any]]) -> list[dict]:
    """Propose (jamais applique) un ajustement de `scale` DYNAMIC par session
    sous-performante (WR < 60%, n >= MIN_SAMPLE_SESSION)."""
    proposals: list[dict] = []
    for session, b in sorted(buckets.items()):
        n = b["n"]
        if n < MIN_SAMPLE_SESSION or b["wr_pct"] is None:
            proposals.append({
                "session": session, "proposed": False,
                "reason": f"n={n} < min={MIN_SAMPLE_SESSION}",
            })
            continue
        wr = b["wr_pct"]
        if wr >= WR_LOW_THRESHOLD:
            proposals.append({
                "session": session, "proposed": False,
                "reason": f"wr={wr}% >= seuil {WR_LOW_THRESHOLD}%", "wr_pct": wr, "n": n,
            })
            continue
        current_scale = b["current_scale"]
        # Reduction proportionnelle a l'ecart sous le seuil, plafonnee.
        delta_ratio = max(0.0, (WR_LOW_THRESHOLD - wr) / WR_LOW_THRESHOLD)
        proposed_scale = round(max(0.0, current_scale * (1.0 - min(delta_ratio, 1.0))), 2)
        proposals.append({
            "session": session, "proposed": True,
            "n": n, "wr_pct": wr, "avg_pips": b["avg_pips"],
            "current_scale": current_scale, "proposed_scale": proposed_scale,
            "rationale": (
                f"WR session {session}={wr}% < {WR_LOW_THRESHOLD}% sur {n} decisions "
                f"DYNAMIC -> scale propose {current_scale}->{proposed_scale} "
                "(reduction proportionnelle, JAMAIS appliquee automatiquement)."
            ),
        })
    return proposals


def _propose_threshold_adjustments(
    global_wr_pct: float | None, n_total: int,
    current_confiance_min: int, current_nb_principes_min: int,
) -> dict[str, Any]:
    """Propose (jamais applique) des ajustements CONFIANCE_MIN / NB_PRINCIPES_MIN
    bases sur l'ecart entre WR global observe et la cible (meme logique de
    delta que v9_recalibrate_arbiter.py)."""
    if global_wr_pct is None or n_total < MIN_SAMPLE_SESSION:
        return {
            "proposed": False,
            "reason": f"n={n_total} < min={MIN_SAMPLE_SESSION}, pas de proposition",
        }

    delta_wr = global_wr_pct - TARGET_WR_SESSION
    # WR sous la cible -> resserrer (CONFIANCE_MIN monte, NB_PRINCIPES_MIN monte).
    # WR au-dessus -> marge pour assouplir legerement (bornes dures ci-dessous).
    lo_c, hi_c = CONFIANCE_MIN_BOUNDS
    proposed_confiance_min = max(lo_c, min(hi_c, current_confiance_min - round(delta_wr * 0.2)))

    lo_p, hi_p = NB_PRINCIPES_MIN_BOUNDS
    proposed_nb_principes_min = current_nb_principes_min
    if global_wr_pct < WR_LOW_THRESHOLD:
        proposed_nb_principes_min = max(lo_p, min(hi_p, current_nb_principes_min + 1))

    return {
        "proposed": True,
        "global_wr_pct": global_wr_pct,
        "n_total": n_total,
        "current_confiance_min": current_confiance_min,
        "proposed_confiance_min": proposed_confiance_min,
        "current_nb_principes_min": current_nb_principes_min,
        "proposed_nb_principes_min": proposed_nb_principes_min,
        "rationale": (
            f"WR global={global_wr_pct}% (cible {TARGET_WR_SESSION}%) sur {n_total} decisions "
            f"-> CONFIANCE_MIN {current_confiance_min}->{proposed_confiance_min}, "
            f"NB_PRINCIPES_MIN {current_nb_principes_min}->{proposed_nb_principes_min} "
            "(proposition seule, jamais appliquee automatiquement — validation manuelle requise)."
        ),
    }


def _weak_principles(scorer: PrincipleScorer, min_trades: int = 5) -> list[dict]:
    """Combinaisons de principes sous 60% WR (informatif, pas de proposition
    de modification YAML — hors perimetre de ce brief)."""
    try:
        top = scorer.get_top_combinations(limit=200, min_trades=min_trades)
    except sqlite3.Error:
        return []
    return [c for c in top if c.get("win_rate") is not None and c["win_rate"] < WR_LOW_THRESHOLD]


def _journal_cycle(report: dict, db_path: Path | str | None = None) -> None:
    """Journalise le cycle dans cognitive_journal (meme table que
    meta_agent.py, data/v9_agent_bus.db) — best-effort, ne bloque jamais."""
    try:
        from core.v9.agent_bus import AGENT_BUS_DB_PATH
        conn = get_connection(AGENT_BUS_DB_PATH)
    except Exception:
        return
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cognitive_journal ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, agent TEXT, "
            "event_type TEXT, lessons TEXT, metadata TEXT)"
        )
        conn.execute(
            "INSERT INTO cognitive_journal (ts, agent, event_type, lessons, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                report["timestamp_utc"], "auto_calibrator", "calibration_proposal",
                f"n_session_proposals={report['n_session_proposals']}, "
                f"threshold_proposed={report['threshold_adjustment'].get('proposed', False)}",
                json.dumps(report, ensure_ascii=False),
            ),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def _notify_telegram_best_effort(report: dict) -> None:
    """Notification best-effort — reutilise _load_telegram_config_safe
    (core/v9/decision_logger.py, Brief O3). Ne bloque jamais le cycle."""
    try:
        from core.v9.decision_logger import _load_telegram_config_safe
        cfg = _load_telegram_config_safe()
        if cfg is None:
            return
        from scripts.v9_telegram_notifier import send_telegram

        n_prop = report["n_session_proposals"]
        thr = report["threshold_adjustment"]
        lines = [
            "[V9] Auto-calibrateur — cycle 24h",
            f"Sessions proposees : {n_prop}",
        ]
        if thr.get("proposed"):
            lines.append(
                f"CONFIANCE_MIN {thr['current_confiance_min']}->{thr['proposed_confiance_min']}, "
                f"NB_PRINCIPES_MIN {thr['current_nb_principes_min']}->{thr['proposed_nb_principes_min']}"
            )
        lines.append("Aucune application automatique — validation manuelle requise.")
        send_telegram("\n".join(lines), cfg, timeout=5)
    except Exception:
        return


def run_calibration_cycle(
    db_path: Path | str | None = None,
    confiance_min: int = 70,
    nb_principes_min: int = 2,
    notify: bool = False,  # Mode silencieux (CEO 2026-07-13) : True→False, pas de spam Telegram
    journal: bool = True,
) -> dict[str, Any]:
    """Execute un cycle de calibration complet (lecture + proposition,
    JAMAIS d'ecriture sur config/risk_manager). Retourne le rapport.

    Si le kill switch est OFF, retourne immediatement {'enabled': False}
    sans lire la DB ni notifier — reste appelable en toute securite.
    """
    if not auto_calibrator_enabled():
        return {"enabled": False}

    conn = _connect(db_path)
    try:
        buckets = _session_wr_buckets(conn)
        session_proposals = _propose_session_scale_adjustments(buckets)

        n_total = sum(b["n"] for b in buckets.values())
        n_wins = sum(b["wins"] for b in buckets.values())
        global_wr = round(n_wins / n_total * 100, 1) if n_total else None

        threshold_adjustment = _propose_threshold_adjustments(
            global_wr, n_total, confiance_min, nb_principes_min,
        )

        scorer = PrincipleScorer(db_path=Path(db_path) if db_path else DB_PATH)
        weak_principles = _weak_principles(scorer)
    finally:
        conn.close()

    report = {
        "calibrator_version": CALIBRATOR_VERSION,
        "enabled": True,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session_buckets": buckets,
        "session_proposals": session_proposals,
        "n_session_proposals": sum(1 for p in session_proposals if p.get("proposed")),
        "global_wr_pct": global_wr,
        "n_total_decisions": n_total,
        "threshold_adjustment": threshold_adjustment,
        "weak_principle_combinations": weak_principles,
        "auto_apply": False,
    }

    if journal:
        _journal_cycle(report, db_path)
    if notify:
        _notify_telegram_best_effort(report)

    return report
