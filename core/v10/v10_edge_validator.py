"""V10 Edge Validator — Walk-Forward Statistique pour signals_history + paper_trades.

Méthode :
  - Window train : 60 jours | Window test : 20 jours | Step : 10 jours
  - Walk-forward : on avance step par step sur l'historique disponible
  - Pour chaque fenêtre test : on calcule WR, R:R, Sharpe, Max DD, n_trades

Gates edge fund (R10 capital) :
  WR A1   ≥ 62%   (upgrade vs 58% Phase 5)
  R:R     ≥ 2.0
  Sharpe  ≥ 1.5
  Max DD  ≤ 8%    (serré vs 12% Phase 5)
  Consistency : WR stable sur ≥ 3 fenêtres consécutives
  Min trades    : 50 (vs 30 Phase 5)

Verdict :
  ALL_PASS   → promotion_eligible=True
  PARTIAL    → rapport détaillé + recommandation calibration
  ALL_FAIL   → blocage R10 + rapport root_cause

API : run_walk_forward() → WalkForwardReport
  - windows : List[WindowResult]
  - aggregate_kpis, gate_results, promotion_eligible
  - R9 audit complet avec dates, n_trades, kpis par fenêtre
"""
from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
DEFAULT_WF_CONFIG = {
    "train_days": 60,
    "test_days": 20,
    "step_days": 10,
    "min_trades_per_window": 5,
    "min_total_trades": 50,
    "setup_levels": ("A1",),  # par défaut A1 uniquement
    "gates": {
        "wr_a1_min": 0.62,
        "rr_min": 2.0,
        "sharpe_min": 1.5,
        "max_dd_max": 0.08,
        "consistency_windows": 3,
    },
}


class Verdict(str, Enum):
    ALL_PASS = "ALL_PASS"
    PARTIAL = "PARTIAL"
    ALL_FAIL = "ALL_FAIL"


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class TradeResult:
    """Un trade clôturé pour walk-forward."""

    trade_id: str = ""
    timestamp: str = ""          # ISO UTC
    timestamp_epoch: int = 0    # epoch seconds
    symbol: str = ""
    direction: str = ""         # "BUY" / "SELL"
    pnl_pips: float = 0.0
    pnl: float = 0.0            # en unité capital
    setup_level: str = ""       # "A1", "A2", "A3"
    closed: bool = True


@dataclass
class WindowResult:
    """Résultat d'une fenêtre test walk-forward."""

    window_index: int = 0
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    n_trades: int = 0

    win_rate: float = 0.0
    avg_rr: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    total_pnl: float = 0.0
    passed_gates: bool = False
    gate_results: Dict[str, bool] = field(default_factory=dict)
    notes: str = ""

    def as_dict(self) -> Dict:
        return {
            "window_index": self.window_index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "n_trades": self.n_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_rr": round(self.avg_rr, 4),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "total_pnl": round(self.total_pnl, 4),
            "passed_gates": self.passed_gates,
            "gate_results": dict(self.gate_results),
            "notes": self.notes,
        }


@dataclass
class WalkForwardReport:
    """Rapport complet walk-forward."""

    symbol: Optional[str] = None
    n_windows: int = 0
    windows: List[WindowResult] = field(default_factory=list)
    aggregate_kpis: Dict[str, float] = field(default_factory=dict)
    gate_results: Dict[str, bool] = field(default_factory=dict)
    promotion_eligible: bool = False
    verdict: Verdict = Verdict.ALL_FAIL
    root_cause: str = ""
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "n_windows": self.n_windows,
            "windows": [w.as_dict() for w in self.windows],
            "aggregate_kpis": dict(self.aggregate_kpis),
            "gate_results": dict(self.gate_results),
            "promotion_eligible": self.promotion_eligible,
            "verdict": self.verdict.value,
            "root_cause": self.root_cause,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers SQL
# ─────────────────────────────────────────────────────────────────────
def _open_db(db_path: str) -> Optional[sqlite3.Connection]:
    if not Path(db_path).exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.OperationalError:
        return None


def _load_paper_trades(db_path: str, symbol: Optional[str] = None) -> List[TradeResult]:
    """Charge paper_trades depuis la DB V9.

    Robuste à plusieurs schémas :
      - V8 : id, symbol, direction, pnl_pips, pnl, closed_at, setup_level
      - V9 : trade_id, snapshot_id, direction, pips_net_of_spread, pips_simulated,
              closed_at, symbol (pas de setup_level, on infère A1)
    """
    con = _open_db(db_path)
    if con is None:
        return []
    out: List[TradeResult] = []
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'")
        if not cur.fetchone():
            return []
        cur.execute("PRAGMA table_info(paper_trades)")
        cols = {c[1] for c in cur.fetchall()}

        # Sélection dynamique
        select_parts = []
        if "id" in cols:
            select_parts.append(("id", "id"))
        elif "trade_id" in cols:
            select_parts.append(("trade_id", "trade_id"))
        if "symbol" in cols:
            select_parts.append(("symbol", "symbol"))
        if "direction" in cols:
            select_parts.append(("direction", "direction"))
        # pnl : pnl/pips_simulated/...
        if "pnl" in cols:
            select_parts.append(("pnl", "pnl"))
        elif "pips_simulated" in cols:
            select_parts.append(("pnl", "pips_simulated as pnl"))
        if "pnl_pips" in cols:
            select_parts.append(("pnl_pips", "pnl_pips"))
        elif "pips_net_of_spread" in cols:
            select_parts.append(("pnl_pips", "pips_net_of_spread as pnl_pips"))

        # timestamp
        ts_col = None
        for cand in ("closed_at", "close_time", "opened_at", "open_time", "timestamp"):
            if cand in cols:
                ts_col = cand
                break
        if ts_col:
            select_parts.append((ts_col, ts_col))
        if "setup_level" in cols:
            select_parts.append(("setup_level", "setup_level"))

        if not ts_col:
            return []

        where = "WHERE 1=1"
        params: list = []
        if symbol and "symbol" in cols:
            where += " AND symbol=?"
            params.append(symbol)
        cols_sql = ", ".join(s for _, s in select_parts)
        query = f"SELECT {cols_sql} FROM paper_trades {where} ORDER BY {ts_col} ASC"

        def _idx(key):
            for i, (k, _) in enumerate(select_parts):
                if k == key:
                    return i
            return None

        idx_id = _idx("id") if "id" in cols else _idx("trade_id")
        idx_symbol = _idx("symbol")
        idx_direction = _idx("direction")
        idx_pnl = _idx("pnl")
        idx_pnl_pips = _idx("pnl_pips")
        idx_ts = _idx(ts_col)
        idx_lvl = _idx("setup_level")

        for row in cur.execute(query, params):
            tr_id = row[idx_id] if idx_id is not None else ""
            sym = row[idx_symbol] if idx_symbol is not None else ""
            direction = row[idx_direction] if idx_direction is not None else ""
            pnl_val = row[idx_pnl] if idx_pnl is not None else 0.0
            pips_val = row[idx_pnl_pips] if idx_pnl_pips is not None else 0.0
            ts_val = row[idx_ts]
            lvl = row[idx_lvl] if idx_lvl is not None else "A1"
            ts_iso = ""
            ts_epoch = 0
            try:
                if isinstance(ts_val, str):
                    ts_iso = ts_val.replace(" ", "T")
                    if "Z" not in ts_iso and "+" not in ts_iso:
                        ts_iso += "+00:00"
                    dt = datetime.fromisoformat(ts_iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts_epoch = int(dt.timestamp())
                    ts_iso = dt.isoformat()
                elif isinstance(ts_val, (int, float)):
                    ts_epoch = int(ts_val)
                    ts_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat()
            except Exception:
                pass
            out.append(TradeResult(
                trade_id=str(tr_id),
                timestamp=ts_iso,
                timestamp_epoch=ts_epoch,
                symbol=str(sym) if sym else "",
                direction=str(direction) if direction else "",
                pnl_pips=float(pips_val or 0),
                pnl=float(pnl_val or 0),
                setup_level=str(lvl) if lvl else "A1",
                closed=True,
            ))
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# Métriques par fenêtre
# ─────────────────────────────────────────────────────────────────────
def _metrics_for_window(trades: List[TradeResult], rr_target: float = 2.0) -> Dict[str, float]:
    """Calcule win_rate, avg_rr, sharpe, max_dd, total_pnl."""
    if not trades:
        return {
            "win_rate": 0.0,
            "avg_rr": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 1.0,
            "total_pnl": 0.0,
            "n_trades": 0,
        }
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    n = len(trades)
    win_rate = len(wins) / n if n else 0
    # avg_rr simplifié : avg(win / |loss|) avec risqué target = 1
    if losses:
        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0.0
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses))
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0.0
    else:
        avg_rr = (rr_target if wins else 0.0)
    # Equity curve simplifiée : somme cumulée
    eq: List[float] = []
    cumul = 0.0
    for t in trades:
        cumul += t.pnl
        eq.append(cumul)
    peak = -1e18
    max_dd_pct = 0.0
    if eq:
        for e in eq:
            peak = max(peak, e)
            if peak > 0:
                dd = (peak - e) / peak
                if dd > max_dd_pct:
                    max_dd_pct = dd
    # Sharpe : mean(pnl) / std(pnl) sur fenêtre × sqrt(252 daily ou plus)
    pnls = [t.pnl for t in trades]
    if len(pnls) > 1:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = math.sqrt(var) if var > 0 else 0.0
        # Annualisation heuristique : sqrt(n_trades_per_year) si ~250 jour/year
        sharpe = (mean / sd * math.sqrt(252.0)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "total_pnl": cumul,
        "n_trades": n,
    }


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def run_walk_forward(
    *,
    db_path: str = "data/v9_forces.db",
    symbol: Optional[str] = None,
    config: Optional[Dict] = None,
    seed: Optional[int] = None,
) -> WalkForwardReport:
    """Walk-forward sur signals_history + paper_trades.

    Parameters
    ----------
    db_path : chemin DB (défaut "data/v9_forces.db").
    symbol : ex "EURUSD" ou None = tous.
    config : override WF_CONFIG.

    Returns
    -------
    WalkForwardReport complet.
    """
    cfg = dict(DEFAULT_WF_CONFIG)
    if config:
        # Deep merge gates
        if "gates" in config:
            cfg["gates"].update(config["gates"])
        cfg.update({k: v for k, v in config.items() if k != "gates"})

    rep = WalkForwardReport(symbol=symbol, audit={"config_used": cfg, "seed": seed})

    trades = _load_paper_trades(db_path, symbol=symbol)
    rep.audit["n_trades_loaded"] = len(trades)
    rep.audit["db_path"] = db_path

    # Si aucun trade → verdict immédiat
    if not trades:
        rep.verdict = Verdict.ALL_FAIL
        rep.root_cause = "no_trades_loaded (DB absente ou table paper_trades vide)"
        return rep

    # Filtre par setup_levels
    levels = cfg.get("setup_levels", ("A1",))
    if isinstance(levels, str):
        levels = (levels,)
    levels_set = set(levels)
    trades_filt = [t for t in trades if t.setup_level in levels_set]
    rep.audit["n_trades_after_level_filter"] = len(trades_filt)

    if not trades_filt:
        rep.verdict = Verdict.ALL_FAIL
        rep.root_cause = f"no_trades_for_level(s)={list(levels)}"
        return rep

    # Tri par timestamp
    trades_filt.sort(key=lambda t: t.timestamp_epoch)
    rep.audit["first_trade_epoch"] = trades_filt[0].timestamp_epoch
    rep.audit["last_trade_epoch"] = trades_filt[-1].timestamp_epoch

    # Construction des fenêtres walk-forward
    train_days = int(cfg["train_days"])
    test_days = int(cfg["test_days"])
    step_days = int(cfg["step_days"])
    min_total = int(cfg["min_total_trades"])
    min_n_window = int(cfg["min_trades_per_window"])

    if len(trades_filt) < min_total:
        rep.verdict = Verdict.ALL_FAIL
        rep.root_cause = (
            f"insufficient_total_trades: {len(trades_filt)} < min_total {min_total}"
        )
        return rep

    first_ts = trades_filt[0].timestamp_epoch
    last_ts = trades_filt[-1].timestamp_epoch
    day = 86400

    # On démarre le test à first_ts + train_days
    windows: List[WindowResult] = []
    test_start_ts = first_ts + train_days * day
    while test_start_ts + test_days * day <= last_ts:
        train_end_ts = test_start_ts
        test_end_ts = test_start_ts + test_days * day
        train_start_ts = train_end_ts - train_days * day

        # Trades du set test
        test_trades = [
            t for t in trades_filt
            if train_end_ts <= t.timestamp_epoch < test_end_ts
        ]
        if test_trades:
            m = _metrics_for_window(test_trades)
            wr = m["win_rate"]
            pass_str = bool(wr >= cfg["gates"]["wr_a1_min"])
            wr_ok = m["win_rate"] >= cfg["gates"]["wr_a1_min"]
            rr_ok = m["avg_rr"] >= cfg["gates"]["rr_min"]
            sh_ok = m["sharpe"] >= cfg["gates"]["sharpe_min"]
            dd_ok = m["max_drawdown_pct"] <= cfg["gates"]["max_dd_max"]
            passed = wr_ok and rr_ok and sh_ok and dd_ok
            w = WindowResult(
                window_index=len(windows),
                train_start=datetime.fromtimestamp(train_start_ts, tz=timezone.utc).isoformat(),
                train_end=datetime.fromtimestamp(train_end_ts, tz=timezone.utc).isoformat(),
                test_start=datetime.fromtimestamp(train_end_ts, tz=timezone.utc).isoformat(),
                test_end=datetime.fromtimestamp(test_end_ts, tz=timezone.utc).isoformat(),
                n_trades=m["n_trades"],
                win_rate=m["win_rate"],
                avg_rr=m["avg_rr"],
                sharpe=m["sharpe"],
                max_drawdown_pct=m["max_drawdown_pct"],
                total_pnl=m["total_pnl"],
                passed_gates=passed,
                gate_results={
                    "wr_a1_min": wr_ok,
                    "rr_min": rr_ok,
                    "sharpe_min": sh_ok,
                    "max_dd_max": dd_ok,
                },
                notes="",
            )
            if m["n_trades"] < min_n_window:
                w.notes = f"low_trades={m['n_trades']}"
            windows.append(w)
        test_start_ts += step_days * day

    rep.windows = windows
    rep.n_windows = len(windows)

    if not windows:
        rep.verdict = Verdict.ALL_FAIL
        rep.root_cause = "no_test_windows_constructed"
        return rep

    # Agrégat : moyenne pondérée par n_trades
    total_n = sum(w.n_trades for w in windows)
    if total_n > 0:
        wr_agg = sum(w.win_rate * w.n_trades for w in windows) / total_n
        rr_agg = sum(w.avg_rr * w.n_trades for w in windows) / total_n
        sh_agg = sum(w.sharpe * w.n_trades for w in windows) / total_n
        dd_agg = sum(w.max_drawdown_pct * w.n_trades for w in windows) / total_n
        pnl_agg = sum(w.total_pnl for w in windows)
    else:
        wr_agg = rr_agg = sh_agg = dd_agg = pnl_agg = 0.0

    rep.aggregate_kpis = {
        "win_rate": wr_agg,
        "avg_rr": rr_agg,
        "sharpe": sh_agg,
        "max_drawdown_pct": dd_agg,
        "total_pnl": pnl_agg,
        "n_trades_total": total_n,
        "n_windows_passed": sum(1 for w in windows if w.passed_gates),
    }

    # Gates au niveau agrégat
    g_w = cfg["gates"]
    agg_wr_ok = wr_agg >= g_w["wr_a1_min"]
    agg_rr_ok = rr_agg >= g_w["rr_min"]
    agg_sh_ok = sh_agg >= g_w["sharpe_min"]
    agg_dd_ok = dd_agg <= g_w["max_dd_max"]
    # Consistency : WR stable sur ≥ g_w['consistency_windows'] consécutives
    consistency_min = int(g_w["consistency_windows"])
    consistency_ok = False
    streak = 0
    best_streak = 0
    for w in windows:
        if w.passed_gates:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
    consistency_ok = best_streak >= consistency_min

    rep.gate_results = {
        "wr_a1_min": agg_wr_ok,
        "rr_min": agg_rr_ok,
        "sharpe_min": agg_sh_ok,
        "max_dd_max": agg_dd_ok,
        "consistency": consistency_ok,
    }

    # Verdict
    n_pass = sum(1 for x in rep.gate_results.values() if x)
    n_total = len(rep.gate_results)
    if n_pass == n_total:
        rep.verdict = Verdict.ALL_PASS
        rep.promotion_eligible = True
        rep.root_cause = "tous_gates_passed"
    elif n_pass >= n_total * 0.6:
        rep.verdict = Verdict.PARTIAL
        rep.promotion_eligible = False
        rep.root_cause = f"{n_pass}/{n_total} gates passés — recalibration Bayesian recommandée"
    else:
        rep.verdict = Verdict.ALL_FAIL
        rep.promotion_eligible = False
        rep.root_cause = f"{n_pass}/{n_total} gates passés — R10 BLOQUÉ, root cause = recalibration"

    rep.audit["n_windows_passed"] = rep.aggregate_kpis["n_windows_passed"]
    rep.audit["best_streak_passed"] = best_streak
    return rep


__all__ = [
    "WalkForwardReport",
    "WindowResult",
    "TradeResult",
    "Verdict",
    "DEFAULT_WF_CONFIG",
    "run_walk_forward",
    "_metrics_for_window",
    "_load_paper_trades",
]
