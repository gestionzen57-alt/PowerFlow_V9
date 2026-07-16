"""auto_optimizer.py — Optimisation automatique des TP/SL par principe (SOUL.md §4).

Cycle tous les 100 trades : pour chaque principe ACTIVE avec n >= 20 trades
resolus, simule 81 combinaisons TPxSL (9x9) et applique le couple qui maximise
l'expectancy si le delta est > 1 pip par rapport au profil actuel.

Les overrides sont persistes dans config/strategy_overrides.json, lus par
PrincipleStrategyEngine au prochain chargement.

Doctrine :
  - R18 : stdlib uniquement, aucun LLM
  - R2 : couche additive (n'affecte pas la chaine cognitive existante)
  - R6 : try/except, ne crash jamais l'orchestrateur
  - R30 : boucle fermee d'auto-optimisation continue
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

AUTO_OPTIMIZER_ENABLED_ENV = "V9_AUTO_OPTIMIZER_ENABLED"
OPTIMIZER_VERSION = "1.0"

# Chemin des overrides de strategie (lu par PrincipleStrategyEngine).
STRATEGY_OVERRIDES_PATH = ROOT_DIR / "config" / "strategy_overrides.json"

# Grille de recherche TP/SL (9x9 = 81 combinaisons).
TP_GRID = [5, 6, 7, 8, 9, 10, 12, 15, 20]
SL_GRID = [5, 6, 7, 8, 9, 10, 12, 15, 20]

# Seuils.
MIN_TRADES_FOR_OPTIMIZATION = 20
MIN_EXPECTANCY_DELTA = 1.0  # pips
MAX_TRADES_SIMULATED = 100  # nombre max de trades a simuler

# Bornes de securite.
TP_MIN = 5
TP_MAX = 20
SL_MIN = 5
SL_MAX = 20
SIZING_MIN = 0.3
SIZING_MAX = 2.0


def auto_optimizer_enabled() -> bool:
    """Kill switch V9_AUTO_OPTIMIZER_ENABLED (defaut '1' = ON)."""
    return os.environ.get(AUTO_OPTIMIZER_ENABLED_ENV, "1") == "1"


def _load_overrides(path: Path) -> dict[str, Any]:
    """Charge les overrides depuis un fichier JSON."""
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


def _fetch_trades_for_principle(
    conn: sqlite3.Connection,
    principle_id: str,
    limit: int = MAX_TRADES_SIMULATED,
) -> list[dict[str, Any]]:
    """Recupere les N derniers trades resolus pour un principe."""
    rows = conn.execute(
        """
        SELECT d.is_win, d.resolution_pips, d.timestamp
        FROM principle_evaluations pe
        JOIN decisions d ON d.snapshot_id = pe.snapshot_id
        WHERE pe.principle_id = ?
          AND pe.triggered = 1
          AND d.is_win IS NOT NULL
        ORDER BY d.timestamp DESC
        LIMIT ?
        """,
        (principle_id, limit),
    ).fetchall()
    return [{"is_win": r["is_win"], "pips": r["resolution_pips"] or 0.0} for r in rows]


def _grid_search(
    trades: list[dict[str, Any]],
    tp_grid: list[int] | None = None,
    sl_grid: list[int] | None = None,
) -> dict[str, Any]:
    """Simule toutes les combinaisons TPxSL et retourne la meilleure.

    Pour chaque combinaison (TP, SL), calcule l'expectancy :
      expectancy = WR * TP - (1-WR) * SL

    Retourne le couple (tp, sl, expectancy) qui maximise l'expectancy.
    """
    if not trades:
        return {"tp": 10, "sl": 15, "expectancy": 0.0, "n_trades": 0}

    tp_grid = tp_grid or TP_GRID
    sl_grid = sl_grid or SL_GRID

    n = len(trades)
    wins = sum(1 for t in trades if t["is_win"] == 1)
    wr = wins / n if n > 0 else 0.0

    # Initialiser avec la premiere combinaison (evite le bug du best negatif)
    first_tp = tp_grid[0]
    first_sl = sl_grid[0]
    first_exp = wr * first_tp - (1.0 - wr) * first_sl
    best = {"tp": first_tp, "sl": first_sl, "expectancy": round(first_exp, 3)}

    for tp in tp_grid:
        for sl in sl_grid:
            expectancy = wr * tp - (1.0 - wr) * sl
            if expectancy > best["expectancy"]:
                best = {"tp": tp, "sl": sl, "expectancy": round(expectancy, 3)}

    best["wr"] = round(wr * 100, 1)
    best["n_trades"] = n
    return best


def _get_current_strategy(principle_id: str) -> dict[str, Any]:
    """Recupere la strategie actuelle d'un principe depuis les overrides ou les defaults."""
    overrides = _load_overrides(STRATEGY_OVERRIDES_PATH)
    return overrides.get(principle_id, {"tp_pips": 10, "sl_pips": 15})


def _apply_optimization(
    principle_id: str,
    best: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any] | None:
    """Applique l'optimisation si le delta d'expectancy > 1 pip.

    Retourne un dict de description si applique, None sinon.
    """
    current_tp = current.get("tp_pips", 10)
    current_sl = current.get("sl_pips", 15)
    current_expectancy = best["wr"] / 100.0 * current_tp - (1.0 - best["wr"] / 100.0) * current_sl

    delta = best["expectancy"] - current_expectancy
    if delta <= MIN_EXPECTANCY_DELTA:
        return None

    # Charger les overrides existants
    overrides = _load_overrides(STRATEGY_OVERRIDES_PATH)

    # Appliquer les bornes de securite
    tp = max(TP_MIN, min(TP_MAX, best["tp"]))
    sl = max(SL_MIN, min(SL_MAX, best["sl"]))

    overrides[principle_id] = {
        "tp_pips": tp,
        "sl_pips": sl,
        "optimized_at": datetime.now(timezone.utc).isoformat(),
        "optimizer_version": OPTIMIZER_VERSION,
        "expectancy_delta": round(delta, 2),
        "n_trades": best["n_trades"],
        "wr": best["wr"],
    }

    _save_overrides(STRATEGY_OVERRIDES_PATH, overrides)

    return {
        "principle_id": principle_id,
        "tp_old": current_tp,
        "tp_new": tp,
        "sl_old": current_sl,
        "sl_new": sl,
        "expectancy_old": round(current_expectancy, 3),
        "expectancy_new": best["expectancy"],
        "delta": round(delta, 2),
        "n_trades": best["n_trades"],
        "wr": best["wr"],
    }


def run_optimization_cycle(
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute un cycle d'optimisation complet.

    Pour chaque principe ACTIVE avec n >= MIN_TRADES_FOR_OPTIMIZATION trades
    resolus, simule 81 combinaisons TPxSL et applique la meilleure si
    delta expectancy > 1 pip.

    Retourne un rapport avec les optimisations appliquees.
    """
    if not auto_optimizer_enabled():
        return {"enabled": False}

    from core.v9.config import PRINCIPLE_ACTIVE_IDS

    conn = get_connection(Path(db_path) if db_path else DB_PATH)
    conn.row_factory = sqlite3.Row

    applied: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        for principle_id in PRINCIPLE_ACTIVE_IDS:
            try:
                trades = _fetch_trades_for_principle(conn, principle_id)
                if len(trades) < MIN_TRADES_FOR_OPTIMIZATION:
                    continue

                best = _grid_search(trades)
                current = _get_current_strategy(principle_id)
                result = _apply_optimization(principle_id, best, current)
                if result:
                    applied.append(result)
                    log.info(
                        "auto_optimizer: %s TP %s->%s SL %s->%s (delta=%.2f)",
                        principle_id,
                        result["tp_old"], result["tp_new"],
                        result["sl_old"], result["sl_new"],
                        result["delta"],
                    )
            except Exception as exc:
                errors.append(f"{principle_id}: {exc}")
                log.debug("auto_optimizer: %s failed: %s", principle_id, exc)
    finally:
        conn.close()

    report = {
        "optimizer_version": OPTIMIZER_VERSION,
        "enabled": True,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_principles_analyzed": len(PRINCIPLE_ACTIVE_IDS),
        "n_optimizations_applied": len(applied),
        "optimizations": applied,
        "errors": errors,
    }

    # Notification Telegram si des optimisations ont ete appliquees
    if applied:
        _notify_telegram_best_effort(report)

    return report


def _notify_telegram_best_effort(report: dict) -> None:
    """Notification Telegram best-effort pour les optimisations appliquees."""
    try:
        from core.v9.decision_logger import _load_telegram_config_safe
        cfg = _load_telegram_config_safe()
        if cfg is None:
            return
        from scripts.v9_telegram_notifier import send_telegram

        lines = [
            "[V9] Auto-optimizer — cycle",
            f"Optimisations appliquees : {report['n_optimizations_applied']}",
        ]
        for opt in report.get("optimizations", []):
            lines.append(
                f"  {opt['principle_id']}: TP {opt['tp_old']}->{opt['tp_new']}, "
                f"SL {opt['sl_old']}->{opt['sl_new']} (delta={opt['delta']})"
            )
        send_telegram("\n".join(lines), cfg, timeout=5)
    except Exception:
        return
