"""scripts/run_live_session_report.py — H-LIVE-REPORT (C22).

Rapport de session live V10 en 6 sections (R6 fail-open sur chacune) :

  1. top 3 paires par force delta 24h
  2. signal_level par paire/TF (A1/A2/A3/NONE)
  3. pre_wave_phase (COMPRESSION/DIVERGENCE/NEUTRAL)
  4. health_score (appel run_live_health_check.build_health)
  5. dernier trade shadow + WR rolling 20 trades
  6. timestamp + version C22

R9 JSON horodaté | R10 lecture seule (aucun ordre, aucun write métier).

Sortie : reports/live_session_<ts>.json

Doctrine : R2 additif pur, R6 fail-open, R8 seuils surchargeables,
R9 audit JSON, R10 compute only.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
DB_PATH = ROOT / "data" / "v9_forces.db"

VERSION = "C22"

# Paires suivies + TF pour la section signal_level
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD")
TIMEFRAMES = ("M30", "H1", "H4")

# Seuil divergence sigma (H7 spec : sigma[-1] > 28)
SIGMA_DIVERGENCE_THRESHOLD = 28.0

# Fenêtre WR rolling
ROLLING_WR_WINDOW = 20


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ts_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _connect(db_path: str) -> sqlite3.Connection | None:
    if not db_path or not Path(db_path).exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
        con.row_factory = sqlite3.Row
        return con
    except Exception:
        return None


def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return default if f != f else f  # NaN guard
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────────────
# 1. TOP 3 PAIRES PAR FORCE DELTA 24H
# ─────────────────────────────────────────────────────────────────────

def top_pairs_force_delta(db_path: str = str(DB_PATH), hours: int = 24) -> Dict[str, Any]:
    """Top 3 paires par |force delta| sur les N dernières heures (R6 fail-open).

    force delta d'une paire = force_base - force_quote, moyenné sur la
    fenêtre. Classement par valeur absolue → top 3.
    """
    out: Dict[str, Any] = {"ok": False, "top": [], "error": None}
    con = _connect(db_path)
    if con is None:
        out["error"] = "db_unavailable"
        return out
    try:
        cutoff_s = int(datetime.now(UTC).timestamp() - hours * 3600)
        rows = con.execute(
            """
            SELECT symbol, force_usd, force_gbp, force_eur, force_jpy,
                   force_cad, force_chf, force_aud, force_nzd
            FROM forces_snapshots
            WHERE is_closed_bar = 1 AND bar_time >= ?
            """,
            (cutoff_s,),
        ).fetchall()
        deltas: Dict[str, List[float]] = {}
        for r in rows:
            sym = r["symbol"]
            if not sym or len(sym) < 6:
                continue
            base = sym[:3].upper()
            quote = sym[3:].upper()
            forces = {
                d: _safe_float(r[f"force_{d.lower()}"])
                for d in ("USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD")
            }
            fb = forces.get(base)
            fq = forces.get(quote)
            if fb is None or fq is None:
                continue
            deltas.setdefault(sym, []).append(fb - fq)
        ranked = []
        for sym, ds in deltas.items():
            if not ds:
                continue
            avg = sum(ds) / len(ds)
            ranked.append({
                "pair": sym,
                "force_delta_24h": round(avg, 4),
                "n_snapshots": len(ds),
            })
        ranked.sort(key=lambda x: abs(x["force_delta_24h"]), reverse=True)
        out["top"] = ranked[:3]
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# 2. SIGNAL_LEVEL PAR PAIRE/TF
# ─────────────────────────────────────────────────────────────────────

def _load_bars_for_tf(db_path: str, pair: str, tf: str, limit: int = 100) -> List[Dict]:
    con = _connect(db_path)
    if con is None:
        return []
    try:
        rows = con.execute(
            """
            SELECT bar_time, open, high, low, close, tick_volume,
                   force_usd, force_gbp, force_eur, force_jpy,
                   force_cad, force_chf, force_aud, force_nzd
            FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
            ORDER BY bar_time DESC LIMIT ?
            """,
            (pair, tf, limit),
        ).fetchall()
        bars = [dict(r) for r in rows]
        bars.reverse()
        return bars
    except Exception:
        return []
    finally:
        con.close()


def signal_level_per_pair_tf(db_path: str = str(DB_PATH)) -> Dict[str, Any]:
    """Signal A1/A2/A3/NONE par (paire, TF) via SignalGeneratorLive (R6 fail-open)."""
    out: Dict[str, Any] = {"ok": False, "levels": [], "error": None}
    con = _connect(db_path)
    if con is None:
        out["error"] = "db_unavailable"
        return out
    con.close()
    try:
        from core.v10.v10_signal_generator_live import SignalGeneratorLive
        gen = SignalGeneratorLive()
        levels = []
        for pair in PAIRS:
            for tf in TIMEFRAMES:
                bars = _load_bars_for_tf(db_path, pair, tf)
                level = "NONE"
                direction = "NEUTRAL"
                if bars:
                    try:
                        sig = gen.generate(symbol=pair, timeframe=tf, bars=bars)
                        if isinstance(sig, dict):
                            level = str(sig.get("signal_level", "NONE"))
                            direction = str(sig.get("direction", "NEUTRAL"))
                    except Exception:
                        level = "NONE"
                levels.append({
                    "pair": pair, "tf": tf,
                    "signal_level": level, "direction": direction,
                })
        out["levels"] = levels
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ─────────────────────────────────────────────────────────────────────
# 3. PRE_WAVE_PHASE (COMPRESSION/DIVERGENCE/NEUTRAL)
# ─────────────────────────────────────────────────────────────────────

def pre_wave_phase_per_pair(db_path: str = str(DB_PATH)) -> Dict[str, Any]:
    """Phase pre-wave par paire (TF=H1) via detect_pre_wave (R6 fail-open).

    Mapping de l'API ZCode (pre_wave bool + compression_ratio) vers les
    3 phases de la spec H7 :
      - COMPRESSION : pre_wave=True (compression sigma détectée)
      - DIVERGENCE  : sigma_recent > seuil divergence
      - NEUTRAL     : sinon
    """
    out: Dict[str, Any] = {"ok": False, "pairs": [], "error": None}
    try:
        from core.v10.v10_fatman_wave_predictor import detect_pre_wave
        from core.v10.v10_perplexity_sigma_oracle import get_sigma_history
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    con = _connect(db_path)
    results = []
    for pair in PAIRS:
        phase = "NEUTRAL"
        detail: Dict[str, Any] = {"pair": pair, "tf": "H1"}
        try:
            sigmas = get_sigma_history(pair, "H1", n=10, db_path=db_path)
            if sigmas:
                alert = detect_pre_wave(sigmas, min_history=6, window=4)
                if alert.pre_wave:
                    phase = "COMPRESSION"
                elif alert.sigma_recent > SIGMA_DIVERGENCE_THRESHOLD:
                    phase = "DIVERGENCE"
                detail.update({
                    "sigma_recent": round(alert.sigma_recent, 3),
                    "sigma_hist": round(alert.sigma_hist, 3),
                    "compression_ratio": round(alert.compression_ratio, 3),
                    "direction": alert.direction,
                })
        except Exception:
            phase = "NEUTRAL"
        detail["pre_wave_phase"] = phase
        results.append(detail)
    if con is not None:
        con.close()
    out["pairs"] = results
    out["ok"] = True
    return out


# ─────────────────────────────────────────────────────────────────────
# 4. HEALTH_SCORE
# ─────────────────────────────────────────────────────────────────────

def health_score() -> Dict[str, Any]:
    """Score de santé live (run_live_health_check.build_health) (R6 fail-open)."""
    out: Dict[str, Any] = {"ok": False, "score": 0.0, "status": "ERROR",
                           "error": None}
    try:
        from scripts.run_live_health_check import build_health
        health = build_health()
        out["score"] = round(float(health.get("score", 0.0)), 2)
        out["status"] = str(health.get("status", "ERROR"))
        out["layers"] = health.get("layers", {})
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ─────────────────────────────────────────────────────────────────────
# 5. DERNIER TRADE SHADOW + WR ROLLING 20
# ─────────────────────────────────────────────────────────────────────

def shadow_trades_summary(db_path: str = str(DB_PATH)) -> Dict[str, Any]:
    """Dernier trade shadow + WR rolling 20 depuis paper_trades (R6 fail-open).

    Colonnes : trade_id, snapshot_id, direction, opened_at, closed_at,
    pips_simulated, is_win.
    """
    out: Dict[str, Any] = {"ok": False, "last_trade": None,
                           "rolling_wr": 0.0, "n_closed": 0, "error": None}
    con = _connect(db_path)
    if con is None:
        out["error"] = "db_unavailable"
        return out
    try:
        # Table existe ?
        has = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'"
        ).fetchone()
        if not has:
            out["error"] = "no_paper_trades_table"
            return out
        # Dernier trade
        last = con.execute(
            """
            SELECT trade_id, snapshot_id, direction, opened_at, closed_at,
                   pips_simulated, is_win
            FROM paper_trades
            ORDER BY opened_at DESC LIMIT 1
            """
        ).fetchone()
        if last:
            out["last_trade"] = {
                "trade_id": last["trade_id"],
                "direction": last["direction"],
                "opened_at": last["opened_at"],
                "closed_at": last["closed_at"],
                "pips_simulated": _safe_float(last["pips_simulated"]),
                "is_win": last["is_win"],
            }
        # WR rolling : 20 derniers trades clos
        closed = con.execute(
            """
            SELECT is_win FROM paper_trades
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at DESC LIMIT ?
            """,
            (ROLLING_WR_WINDOW,),
        ).fetchall()
        wins = sum(1 for r in closed if r["is_win"] == 1)
        n = len(closed)
        out["rolling_wr"] = round(wins / n, 4) if n else 0.0
        out["n_closed"] = n
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# 6. TIMESTAMP + VERSION + ASSEMBLAGE
# ─────────────────────────────────────────────────────────────────────

def build_session_report(db_path: str = str(DB_PATH)) -> Dict[str, Any]:
    """Assemble le rapport 6 sections (R6 fail-open global)."""
    report: Dict[str, Any] = {
        "report": "live_session_report",
        "generated_at_utc": _now_iso(),
        "version": VERSION,
        "doctrine": {"r6": "fail-open", "r9": "audit JSON", "r10": "lecture seule"},
        "meta": {"db_path": db_path, "error": None},
        "sections": {
            "top_pairs_force_delta": {},
            "signal_level_per_pair_tf": {},
            "pre_wave_phase": {},
            "health_score": {},
            "shadow_trades": {},
        },
    }
    try:
        report["sections"]["top_pairs_force_delta"] = top_pairs_force_delta(db_path)
        report["sections"]["signal_level_per_pair_tf"] = signal_level_per_pair_tf(db_path)
        report["sections"]["pre_wave_phase"] = pre_wave_phase_per_pair(db_path)
        report["sections"]["health_score"] = health_score()
        report["sections"]["shadow_trades"] = shadow_trades_summary(db_path)
    except Exception as exc:
        report["meta"]["error"] = f"{type(exc).__name__}: {exc}"
    return report


def write_report(report: Dict[str, Any], out_path: str | Path | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        out_path = REPORTS / f"live_session_{_ts_now()}.json"
    p = Path(out_path)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main() -> int:
    db_path = sys.argv[1] if len(sys.argv) > 1 else str(DB_PATH)
    report = build_session_report(db_path)
    path = write_report(report)
    print(f"[run_live_session_report] {VERSION} | {report['generated_at_utc']}")
    print(f"  rapport écrit : {path}")
    print(f"  top3 force delta : {report['sections']['top_pairs_force_delta'].get('top', [])}")
    print(f"  health : {report['sections']['health_score'].get('score', 0.0)} "
          f"({report['sections']['health_score'].get('status', 'ERROR')})")
    print(f"  shadow rolling WR ({ROLLING_WR_WINDOW}) : "
          f"{report['sections']['shadow_trades'].get('rolling_wr', 0.0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
