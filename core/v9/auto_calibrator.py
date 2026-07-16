"""auto_calibrator.py — Recalibrage automatique periodique (Brief Q2, 2026-07-12).

Cycle 24h : relit les scores PrincipleScorer, detecte les sessions DYNAMIC sous
60% WR, propose ET APPLIQUE les ajustements de CONFIANCE_MIN / NB_PRINCIPES_MIN /
scales DYNAMIC / promotions SHADOW→ACTIVE / demotions ACTIVE→DORMANT.

Mode writable (par defaut) : les ajustements sont appliques dans
config/calibration_overrides.json et config/strategy_overrides.json.
Mode read-only (V9_AUTO_CALIBRATOR_WRITABLE_ENABLED=0) : comportement historique,
propose seulement.

Kill switch : V9_AUTO_CALIBRATOR_ENABLED (defaut '0' = OFF). Quand OFF,
run_calibration_cycle() reste appelable mais ne fait rien.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import DYNAMIC_PROFILES, infer_session_from_hour
from core.v9.principle_scorer import PrincipleScorer

AUTO_CALIBRATOR_ENABLED_ENV = "V9_AUTO_CALIBRATOR_ENABLED"
AUTO_CALIBRATOR_WRITABLE_ENV = "V9_AUTO_CALIBRATOR_WRITABLE_ENABLED"
AUTO_PROMOTION_ENABLED_ENV = "V9_AUTO_PROMOTION_ENABLED"

# Seuil de significativite statistique par session.
MIN_SAMPLE_SESSION = 30

# Cible WR pour le calcul de delta.
TARGET_WR_SESSION = 75.0
WR_LOW_THRESHOLD = 60.0

# Bornes de securite.
CONFIANCE_MIN_BOUNDS = (50, 90)
NB_PRINCIPES_MIN_BOUNDS = (1, 4)

# Seuils d'auto-promotion (R25'').
PROMOTION_MIN_TRIGGERS = 20
PROMOTION_MIN_CONFIDENCE = 60
DEMOTION_MAX_WR = 40.0
DEMOTION_MIN_TRADES = 50

# Chemin des overrides.
CALIBRATION_OVERRIDES_PATH = ROOT_DIR / "config" / "calibration_overrides.json"
STRATEGY_OVERRIDES_PATH = ROOT_DIR / "config" / "strategy_overrides.json"

CALIBRATOR_VERSION = "2.0"


def auto_calibrator_enabled() -> bool:
    """Kill switch V9_AUTO_CALIBRATOR_ENABLED (defaut '0' = OFF)."""
    return os.environ.get(AUTO_CALIBRATOR_ENABLED_ENV, "0") == "1"


def auto_calibrator_writable_enabled() -> bool:
    """Kill switch V9_AUTO_CALIBRATOR_WRITABLE_ENABLED (defaut '1' = ON)."""
    return os.environ.get(AUTO_CALIBRATOR_WRITABLE_ENV, "1") == "1"


def auto_promotion_enabled() -> bool:
    """Kill switch V9_AUTO_PROMOTION_ENABLED (defaut '1' = ON)."""
    return os.environ.get(AUTO_PROMOTION_ENABLED_ENV, "1") == "1"


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = get_connection(Path(db_path) if db_path else DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _load_overrides(path: Path) -> dict[str, Any]:
    """Charge les overrides depuis un fichier JSON. Retourne dict vide si absent."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_overrides(path: Path, data: dict[str, Any]) -> None:
    """Sauvegarde les overrides dans un fichier JSON (atomique)."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


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
    """Propose (et applique si writable) un ajustement de `scale` DYNAMIC par session."""
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
        delta_ratio = max(0.0, (WR_LOW_THRESHOLD - wr) / WR_LOW_THRESHOLD)
        proposed_scale = round(max(0.0, current_scale * (1.0 - min(delta_ratio, 1.0))), 2)
        proposals.append({
            "session": session, "proposed": True,
            "n": n, "wr_pct": wr, "avg_pips": b["avg_pips"],
            "current_scale": current_scale, "proposed_scale": proposed_scale,
            "rationale": (
                f"WR session {session}={wr}% < {WR_LOW_THRESHOLD}% sur {n} decisions "
                f"DYNAMIC -> scale {current_scale}->{proposed_scale}"
            ),
        })
    return proposals


def _apply_session_scale(proposals: list[dict]) -> list[dict]:
    """Applique les ajustements de scale dans calibration_overrides.json."""
    overrides = _load_overrides(CALIBRATION_OVERRIDES_PATH)
    session_scales = overrides.get("session_scales", {})
    applied = []
    for p in proposals:
        if p.get("proposed"):
            session_scales[p["session"]] = p["proposed_scale"]
            applied.append(p)
    if applied:
        overrides["session_scales"] = session_scales
        overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
        overrides["applied_by"] = "auto_calibrator"
        _save_overrides(CALIBRATION_OVERRIDES_PATH, overrides)
    return applied


def _propose_threshold_adjustments(
    global_wr_pct: float | None, n_total: int,
    current_confiance_min: int, current_nb_principes_min: int,
) -> dict[str, Any]:
    """Propose (et applique si writable) des ajustements CONFIANCE_MIN / NB_PRINCIPES_MIN."""
    if global_wr_pct is None or n_total < MIN_SAMPLE_SESSION:
        return {
            "proposed": False,
            "reason": f"n={n_total} < min={MIN_SAMPLE_SESSION}, pas de proposition",
        }

    delta_wr = global_wr_pct - TARGET_WR_SESSION
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
            f"NB_PRINCIPES_MIN {current_nb_principes_min}->{proposed_nb_principes_min}"
        ),
    }


def _apply_threshold_adjustments(adjustment: dict[str, Any]) -> None:
    """Applique les ajustements de seuils dans calibration_overrides.json."""
    if not adjustment.get("proposed"):
        return
    overrides = _load_overrides(CALIBRATION_OVERRIDES_PATH)
    overrides["confiance_min"] = adjustment["proposed_confiance_min"]
    overrides["nb_principes_min"] = adjustment["proposed_nb_principes_min"]
    overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
    overrides["applied_by"] = "auto_calibrator"
    _save_overrides(CALIBRATION_OVERRIDES_PATH, overrides)


def _propose_promotions_demotions(conn: sqlite3.Connection) -> dict[str, Any]:
    """Analyse les principes et propose promotions SHADOW→ACTIVE et demotions ACTIVE→DORMANT.

    Retourne un dict avec les listes de promotions et demotions proposees.
    Ne plante jamais si les tables DB n'existent pas (R6).
    """
    from core.v9.config import PRINCIPLE_ACTIVE_IDS
    from core.v9.principle_engine import load_principles_from_yaml

    principles = load_principles_from_yaml()
    active_ids = set(PRINCIPLE_ACTIVE_IDS)

    # Stats par principe depuis la DB (resilient aux tables manquantes)
    stats: dict[str, Any] = {}
    try:
        rows = conn.execute(
            "SELECT pe.principle_id, COUNT(*) as n_triggered, "
            "AVG(pe.confidence) as avg_confidence "
            "FROM principle_evaluations pe "
            "WHERE pe.triggered = 1 "
            "GROUP BY pe.principle_id"
        ).fetchall()
        stats = {r["principle_id"]: r for r in rows}
    except sqlite3.OperationalError:
        pass

    # WR par principe depuis decisions (resilient aux tables manquantes)
    wr_stats: dict[str, Any] = {}
    try:
        wr_rows = conn.execute(
            "SELECT pe.principle_id, "
            "COUNT(d.is_win) as n_trades, "
            "SUM(CASE WHEN d.is_win = 1 THEN 1 ELSE 0 END) as n_wins "
            "FROM principle_evaluations pe "
            "JOIN decisions d ON d.snapshot_id = pe.snapshot_id "
            "WHERE pe.triggered = 1 AND d.is_win IS NOT NULL "
            "GROUP BY pe.principle_id"
        ).fetchall()
        wr_stats = {r["principle_id"]: r for r in wr_rows}
    except sqlite3.OperationalError:
        pass

    promotions = []
    demotions = []

    for p in principles:
        pid = p.principle_id
        s = stats.get(pid, {})
        n_triggered = s.get("n_triggered", 0) or 0
        avg_conf = s.get("avg_confidence") or 0.0
        wr_s = wr_stats.get(pid, {})
        n_trades = wr_s.get("n_trades", 0) or 0
        n_wins = wr_s.get("n_wins", 0) or 0
        wr_pct = round(n_wins / n_trades * 100, 1) if n_trades >= DEMOTION_MIN_TRADES else None

        # SHADOW -> ACTIVE
        if pid not in active_ids and n_triggered >= PROMOTION_MIN_TRIGGERS and avg_conf >= PROMOTION_MIN_CONFIDENCE:
            promotions.append({
                "principle_id": pid,
                "n_triggered": n_triggered,
                "avg_confidence": round(avg_conf, 1),
                "rationale": f"n_triggered={n_triggered} >= {PROMOTION_MIN_TRIGGERS}, "
                            f"conf={avg_conf:.1f} >= {PROMOTION_MIN_CONFIDENCE}",
            })

        # ACTIVE -> DORMANT
        if pid in active_ids and wr_pct is not None and wr_pct < DEMOTION_MAX_WR:
            demotions.append({
                "principle_id": pid,
                "wr_pct": wr_pct,
                "n_trades": n_trades,
                "rationale": f"WR={wr_pct}% < {DEMOTION_MAX_WR}% sur {n_trades} trades",
            })

    return {"promotions": promotions, "demotions": demotions}


def _apply_promotions_demotions(
    proposals: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Applique les promotions et demotions en modifiant PRINCIPLE_ACTIVE_IDS.

    Note : la modification est persistee dans config.py via un patch du fichier.
    En pratique, l'auto-calibrateur ecrit dans un fichier d'override JSON
    qui est lu par config.py au demarrage.
    """
    from core.v9.config import PRINCIPLE_ACTIVE_IDS

    current = list(PRINCIPLE_ACTIVE_IDS)
    applied_promotions = []
    applied_demotions = []

    for promo in proposals.get("promotions", []):
        pid = promo["principle_id"]
        if pid not in current:
            current.append(pid)
            applied_promotions.append(pid)

    for demo in proposals.get("demotions", []):
        pid = demo["principle_id"]
        if pid in current:
            current.remove(pid)
            applied_demotions.append(pid)

    if applied_promotions or applied_demotions:
        # Persister dans un fichier d'override pour que config.py puisse le lire
        overrides = _load_overrides(CALIBRATION_OVERRIDES_PATH)
        overrides["principle_active_ids_override"] = current
        overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
        overrides["applied_by"] = "auto_calibrator"
        _save_overrides(CALIBRATION_OVERRIDES_PATH, overrides)

    return {
        "promotions_applied": applied_promotions,
        "demotions_applied": applied_demotions,
    }


def _weak_principles(scorer: PrincipleScorer, min_trades: int = 5) -> list[dict]:
    """Combinaisons de principes sous 60% WR (informatif)."""
    try:
        top = scorer.get_top_combinations(limit=200, min_trades=min_trades)
    except sqlite3.Error:
        return []
    return [c for c in top if c.get("win_rate") is not None and c["win_rate"] < WR_LOW_THRESHOLD]


def _journal_cycle(report: dict, db_path: Path | str | None = None) -> None:
    """Journalise le cycle dans cognitive_journal."""
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
                report["timestamp_utc"], "auto_calibrator", "calibration_cycle",
                f"n_session_proposals={report['n_session_proposals']}, "
                f"threshold_proposed={report['threshold_adjustment'].get('proposed', False)}, "
                f"promotions={len(report.get('promotions_applied', []))}, "
                f"demotions={len(report.get('demotions_applied', []))}",
                json.dumps(report, ensure_ascii=False),
            ),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def _notify_telegram_best_effort(report: dict) -> None:
    """Notification best-effort."""
    try:
        from core.v9.decision_logger import _load_telegram_config_safe
        cfg = _load_telegram_config_safe()
        if cfg is None:
            return
        from scripts.v9_telegram_notifier import send_telegram

        n_prop = report["n_session_proposals"]
        thr = report["threshold_adjustment"]
        promos = report.get("promotions_applied", [])
        demos = report.get("demotions_applied", [])
        lines = [
            "[V9] Auto-calibrateur — cycle",
            f"Sessions ajustees : {n_prop}",
        ]
        if thr.get("proposed"):
            lines.append(
                f"CONFIANCE_MIN {thr['current_confiance_min']}->{thr['proposed_confiance_min']}, "
                f"NB_PRINCIPES_MIN {thr['current_nb_principes_min']}->{thr['proposed_nb_principes_min']}"
            )
        if promos:
            lines.append(f"Promotions SHADOW->ACTIVE : {', '.join(promos)}")
        if demos:
            lines.append(f"Demotions ACTIVE->DORMANT : {', '.join(demos)}")
        send_telegram("\n".join(lines), cfg, timeout=5)
    except Exception:
        return


def run_calibration_cycle(
    db_path: Path | str | None = None,
    confiance_min: int = 70,
    nb_principes_min: int = 2,
    notify: bool = False,
    journal: bool = True,
    auto_apply: bool | None = None,  # None = use kill switch default
) -> dict[str, Any]:
    """Execute un cycle de calibration complet (lecture + application).

    Si auto_apply est True (ou si le kill switch V9_AUTO_CALIBRATOR_WRITABLE_ENABLED
    est a 1), les ajustements sont appliques dans les fichiers d'override.
    Sinon, comportement historique read-only (propose seulement).

    Si le kill switch V9_AUTO_CALIBRATOR_ENABLED est OFF, retourne {'enabled': False}.
    """
    if not auto_calibrator_enabled():
        return {"enabled": False}

    writable = auto_apply if auto_apply is not None else auto_calibrator_writable_enabled()
    promotion_active = auto_promotion_enabled()

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

        # Promotions/demotions
        promo_proposals = _propose_promotions_demotions(conn) if promotion_active else {"promotions": [], "demotions": []}

        # Application
        applied_scales = []
        promotions_applied = []
        demotions_applied = []

        if writable:
            applied_scales = _apply_session_scale(session_proposals)
            if threshold_adjustment.get("proposed"):
                _apply_threshold_adjustments(threshold_adjustment)
            if promotion_active:
                result = _apply_promotions_demotions(promo_proposals, db_path)
                promotions_applied = result["promotions_applied"]
                demotions_applied = result["demotions_applied"]
    finally:
        conn.close()

    report = {
        "calibrator_version": CALIBRATOR_VERSION,
        "enabled": True,
        "writable": writable,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session_buckets": buckets,
        "session_proposals": session_proposals,
        "n_session_proposals": sum(1 for p in session_proposals if p.get("proposed")),
        "applied_scales": applied_scales,
        "global_wr_pct": global_wr,
        "n_total_decisions": n_total,
        "threshold_adjustment": threshold_adjustment,
        "weak_principle_combinations": weak_principles,
        "promotion_proposals": promo_proposals,
        "promotions_applied": promotions_applied,
        "demotions_applied": demotions_applied,
        "auto_apply": writable,
    }

    if journal:
        _journal_cycle(report, db_path)
    if notify:
        _notify_telegram_best_effort(report)

    return report
