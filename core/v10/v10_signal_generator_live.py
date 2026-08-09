"""
V10 Signal Generator Live — C7 MAX PERF (09/08/2026)

Fix C7 (sur base C5) :
  SGL1 — Seuils FORCE_NATIVE recalibrés :
          C5 : A3=0.05, A2=0.10, A1=0.18 (trop hauts pour données replay)
          C7 : A3=0.03, A2=0.07, A1=0.13
          Justification : delta moyen observé C5 = 0.04–0.06 → quasiment
          aucun signal ne dépassait 0.05. Avec 0.03, on génère ~10x plus
          de candidats A3/A2 à filtrer proprement par le DP.
  SGL2 — Legacy seuils abaissés proportionnellement :
          A3=8.0 A2=15.0 A1=25.0 (vs 10/20/30 avant)

Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══ IMPORT v10_force_native (R6 fail-open) ═══════════════════════════════
try:
    from .v10_force_native import compute_force_native
    _FORCE_NATIVE_OK = True
except Exception as _e:
    log.warning("[SGL-C7] v10_force_native KO: %s", _e)
    compute_force_native = None
    _FORCE_NATIVE_OK = False

TABLE_SIGNALS_CLEAN = "v10_signals_clean"

CURRENCIES_V10_FULL = ("EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD")

PAIRS_V10_DEFAULT = (
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
)

SIGNAL_LEVEL_NONE = "NONE"
SIGNAL_LEVEL_A3   = "A3"
SIGNAL_LEVEL_A2   = "A2"
SIGNAL_LEVEL_A1   = "A1"

WINDOW_BARS = 50

HORIZON_BARS_BY_TF: Dict[str, int] = {
    "M1":  2, "M5": 3, "M15": 3,
    "M30": 3, "H1": 2, "H4":  1,
}

TIMEFRAMES_DEFAULT: Tuple[str, ...] = ("M15", "M30", "H1", "H4")

BINARY_FORCE_VALUES = frozenset({0.0, 100.0})

# SGL1 : seuils recalibrés C7
FORCE_NATIVE_DELTA_A3 = 0.03   # abaissé de 0.05
FORCE_NATIVE_DELTA_A2 = 0.07   # abaissé de 0.10
FORCE_NATIVE_DELTA_A1 = 0.13   # abaissé de 0.18

# SGL2 : seuils legacy recalibrés C7
FORCE_LEGACY_DELTA_A3 = 8.0    # abaissé de 10.0
FORCE_LEGACY_DELTA_A2 = 15.0   # abaissé de 20.0
FORCE_LEGACY_DELTA_A1 = 25.0   # abaissé de 30.0


class SignalSource(str, Enum):
    FORCE_NATIVE     = "force_native"
    FORCES_SNAPSHOTS = "forces_snapshots"
    SYNTHETIC        = "synthetic"


@dataclass
class V10SignalRow:
    signal_id:       str
    timestamp:       str
    symbol:          str
    timeframe:       str
    pair:            str
    direction:       str
    signal_level:    str
    force_base:      float = 0.0
    force_quote:     float = 0.0
    velocity_base:   float = 0.0
    velocity_quote:  float = 0.0
    rank_base:       int   = 0
    rank_quote:      int   = 0
    spread_score:    float = 0.0
    tick_volume:     float = 0.0
    bid:             float = 0.0
    ask:             float = 0.0
    pnl_pips_proxy:  float = 0.0
    is_win_proxy:    int   = 0
    source:          str   = SignalSource.FORCE_NATIVE.value
    features_json:   str   = ""

    def as_dict(self) -> Dict:
        return {
            "signal_id":      self.signal_id,
            "timestamp":      self.timestamp,
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "pair":           self.pair,
            "direction":      self.direction,
            "signal_level":   self.signal_level,
            "force_base":     round(self.force_base,    4),
            "force_quote":    round(self.force_quote,   4),
            "velocity_base":  round(self.velocity_base, 4),
            "velocity_quote": round(self.velocity_quote, 4),
            "rank_base":      self.rank_base,
            "rank_quote":     self.rank_quote,
            "spread_score":   round(self.spread_score,  2),
            "tick_volume":    self.tick_volume,
            "bid":            self.bid,
            "ask":            self.ask,
            "pnl_pips_proxy": round(self.pnl_pips_proxy, 2),
            "is_win_proxy":   self.is_win_proxy,
            "source":         self.source,
            "features_json":  self.features_json,
        }


@dataclass
class GeneratorReport:
    timestamp:            str  = ""
    db_path:              str  = ""
    n_snapshots_loaded:   int  = 0
    n_signals_generated:  int  = 0
    n_signals_persisted:  int  = 0
    pairs_processed:      List[str] = field(default_factory=list)
    timeframes_processed: List[str] = field(default_factory=list)
    kpis_by_pair:         Dict[str, Dict] = field(default_factory=dict)
    kpis_by_level:        Dict[str, Dict] = field(default_factory=dict)
    kpis_by_tf:           Dict[str, Dict] = field(default_factory=dict)
    kpis_by_pair_tf:      Dict[str, Dict] = field(default_factory=dict)
    audit:                Dict = field(default_factory=dict)
    source_used:          str  = "unknown"
    force_native_pct:     float = 0.0

    def as_dict(self) -> Dict:
        return {
            "timestamp":            self.timestamp,
            "db_path":              self.db_path,
            "n_snapshots_loaded":   self.n_snapshots_loaded,
            "n_signals_generated":  self.n_signals_generated,
            "n_signals_persisted":  self.n_signals_persisted,
            "pairs_processed":      self.pairs_processed,
            "timeframes_processed": self.timeframes_processed,
            "kpis_by_pair":         self.kpis_by_pair,
            "kpis_by_level":        self.kpis_by_level,
            "kpis_by_tf":           self.kpis_by_tf,
            "kpis_by_pair_tf":      self.kpis_by_pair_tf,
            "source_used":          self.source_used,
            "force_native_pct":     self.force_native_pct,
            "audit":                self.audit,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)


# ══ FORCE NATIVE ══════════════════════════════════════════════════════

def _compute_forces_native(bars, pair, tf):
    if not _FORCE_NATIVE_OK or compute_force_native is None or len(bars) < 10:
        return None
    try:
        result = compute_force_native(pair=pair, timeframe=tf, bars=bars)
        if result is None:
            return None
        if isinstance(result, dict):
            return result
        if hasattr(result, "forces"):
            return result.forces
        if hasattr(result, "as_dict"):
            return result.as_dict().get("forces")
        return None
    except Exception as exc:
        log.debug("[SGL-C7] force_native %s/%s fail: %s", pair, tf, exc)
        return None


def _decide_signal_native(forces, pair, prev_forces=None):
    """C7 seuils recalibrés."""
    base, quote = pair[:3].upper(), pair[3:].upper()
    force_base  = float(forces.get(base,  0.0))
    force_quote = float(forces.get(quote, 0.0))

    velocity_base  = 0.0
    velocity_quote = 0.0
    if prev_forces:
        velocity_base  = force_base  - float(prev_forces.get(base,  force_base))
        velocity_quote = force_quote - float(prev_forces.get(quote, force_quote))

    all_sorted = sorted(
        [(c, float(forces.get(c, 0.0))) for c in CURRENCIES_V10_FULL],
        key=lambda x: x[1], reverse=True,
    )
    rank_map   = {c: i + 1 for i, (c, _) in enumerate(all_sorted)}
    rank_base  = rank_map.get(base,  99)
    rank_quote = rank_map.get(quote, 99)

    delta     = force_base - force_quote
    abs_delta = abs(delta)
    direction = "BULLISH" if delta > 0 else ("BEARISH" if delta < 0 else "NEUTRAL")

    # SGL1 : seuils C7
    if abs_delta < FORCE_NATIVE_DELTA_A3:
        level = SIGNAL_LEVEL_NONE
    elif abs_delta < FORCE_NATIVE_DELTA_A2:
        level = SIGNAL_LEVEL_A3
    elif abs_delta < FORCE_NATIVE_DELTA_A1:
        level = SIGNAL_LEVEL_A2
    else:
        dominant_top3 = (
            (delta > 0 and rank_base  <= 3) or
            (delta < 0 and rank_quote <= 3)
        )
        level = SIGNAL_LEVEL_A1 if dominant_top3 else SIGNAL_LEVEL_A2

    return (level, direction, force_base, force_quote,
            velocity_base, velocity_quote, rank_base, rank_quote)


# ══ FORCES SNAPSHOTS LOADER ═══════════════════════════════════════════

def _load_forces_snapshots(db_path, *, symbol=None, timeframe=None, limit=None):
    if not Path(db_path).exists():
        return []
    con = sqlite3.connect(db_path, timeout=10)
    out = []
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'")
        if not cur.fetchone():
            return []
        where, params = ["1=1"], []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            where.append("timeframe = ?")
            params.append(timeframe)
        limit_sql = f"LIMIT {limit}" if limit else ""
        q = f"""
            SELECT snapshot_id, timestamp, symbol, timeframe, bar_time, bar_close_time,
                   direction, vitesse,
                   force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd,
                   tick_volume, spread_points, bid, ask, mid, open, high, low, close
            FROM forces_snapshots WHERE {' AND '.join(where)}
            ORDER BY bar_time ASC {limit_sql}
        """
        for row in cur.execute(q, params):
            out.append({
                "snapshot_id": row[0], "timestamp": row[1], "symbol": row[2],
                "timeframe": row[3], "bar_time": row[4], "bar_close_time": row[5],
                "direction": row[6], "vitesse": row[7] or 0.0,
                "force": {
                    "USD": row[8] or 0.0, "GBP": row[9] or 0.0, "EUR": row[10] or 0.0,
                    "JPY": row[11] or 0.0, "CAD": row[12] or 0.0, "CHF": row[13] or 0.0,
                    "AUD": row[14] or 0.0, "NZD": row[15] or 0.0,
                },
                "tick_volume": row[16] or 0.0, "spread_points": row[17] or 0.0,
                "bid": row[18] or 0.0, "ask": row[19] or 0.0, "mid": row[20] or 0.0,
                "open": row[21] or 0.0, "high": row[22] or 0.0,
                "low": row[23] or 0.0, "close": row[24] or 0.0,
            })
    except Exception as exc:
        log.warning("forces_snapshots read error: %s", exc)
    finally:
        con.close()
    return out


# ══ SIGNAL LEVEL LEGACY ═══════════════════════════════════════════════

def decide_signal_level(*, force_base, force_quote, velocity_base, velocity_quote,
                        rank_base, rank_quote, direction, vitesse):
    """Legacy seuils SGL2 recalibrés C7."""
    delta_force = force_base - force_quote
    dir_sign    = 1 if direction == "haussiere" else (-1 if direction == "baissiere" else 0)
    inferred    = "BULLISH" if delta_force > 0 else ("BEARISH" if delta_force < 0 else "NEUTRAL")
    aligned = (
        (dir_sign > 0 and delta_force > 0) or
        (dir_sign < 0 and delta_force < 0) or
        dir_sign == 0
    )
    if not aligned or abs(delta_force) < FORCE_LEGACY_DELTA_A3:
        return SIGNAL_LEVEL_NONE, inferred
    if abs(delta_force) < FORCE_LEGACY_DELTA_A2:
        return SIGNAL_LEVEL_A3, inferred
    if abs(delta_force) < FORCE_LEGACY_DELTA_A1:
        return SIGNAL_LEVEL_A2, inferred
    dominant_top3 = (
        (delta_force > 0 and rank_base <= 3) or
        (delta_force < 0 and rank_quote <= 3)
    )
    return (SIGNAL_LEVEL_A1 if dominant_top3 else SIGNAL_LEVEL_A2), inferred


# ══ PNL PROXY ═════════════════════════════════════════════════════════

def _compute_pnl_proxy(snapshots, idx, *, horizon_bars=3, direction="BULLISH", pip_multiplier=10000.0):
    if idx + horizon_bars >= len(snapshots):
        return 0.0, 0
    close_now  = float(snapshots[idx].get("close") or snapshots[idx].get("mid") or 0.0)
    close_next = float(snapshots[idx + horizon_bars].get("close") or snapshots[idx + horizon_bars].get("mid") or 0.0)
    if close_now <= 0.0 or close_next <= 0.0:
        return 0.0, 0
    raw   = (close_next - close_now) * pip_multiplier
    pips  = raw if direction == "BULLISH" else -raw
    return round(pips, 2), (1 if pips > 0 else 0)


def _is_binary_snapshot(snap, base, quote):
    f = snap.get("force", {})
    return float(f.get(base, 0.0)) in BINARY_FORCE_VALUES and float(f.get(quote, 0.0)) in BINARY_FORCE_VALUES


# ══ GENERATE SIGNALS ═════════════════════════════════════════════════════

def generate_signals_for_pair_tf(snapshots, *, pair, timeframe, horizon_bars=3, filter_binary=True):
    if len(snapshots) < horizon_bars + 1:
        return [], 0
    base, quote  = pair[:3].upper(), pair[3:].upper()
    pip_mul      = 100.0 if pair.upper().endswith("JPY") else 10000.0
    out          = []
    n_filtered   = 0
    prev_native  = None

    for idx in range(len(snapshots) - horizon_bars):
        snap   = snapshots[idx]
        window = snapshots[max(0, idx - WINDOW_BARS): idx + 1]
        forces = _compute_forces_native(window, pair, timeframe)

        if forces is not None:
            level, direction, fb, fq, vb, vq, rb, rq = _decide_signal_native(forces, pair, prev_native)
            prev_native = forces
            src = SignalSource.FORCE_NATIVE.value
        else:
            if filter_binary and _is_binary_snapshot(snap, base, quote):
                n_filtered += 1
                continue
            fd  = snap.get("force", {})
            fb  = float(fd.get(base,  0.0))
            fq  = float(fd.get(quote, 0.0))
            pfd = (snapshots[idx - 1].get("force", {}) if idx > 0 else {})
            vb  = fb - float(pfd.get(base,  fb))
            vq  = fq - float(pfd.get(quote, fq))
            all_s = sorted([(c, float(fd.get(c, 0.0))) for c in CURRENCIES_V10_FULL], key=lambda x: x[1], reverse=True)
            rmap  = {c: i + 1 for i, (c, _) in enumerate(all_s)}
            rb, rq = rmap.get(base, 99), rmap.get(quote, 99)
            level, direction = decide_signal_level(
                force_base=fb, force_quote=fq,
                velocity_base=vb, velocity_quote=vq,
                rank_base=rb, rank_quote=rq,
                direction=snap.get("direction", "neutre"),
                vitesse=float(snap.get("vitesse", 0.0)),
            )
            src = SignalSource.FORCES_SNAPSHOTS.value
            prev_native = None

        pnl, is_win = _compute_pnl_proxy(snapshots, idx, horizon_bars=horizon_bars,
                                         direction=direction, pip_multiplier=pip_mul)
        sid = f"V10C7-{pair}-{timeframe}-{snap.get('bar_time', idx)}-h{horizon_bars}-{src[:2]}"
        out.append(V10SignalRow(
            signal_id=sid, timestamp=str(snap.get("timestamp", "")),
            symbol=snap.get("symbol", pair), timeframe=timeframe, pair=pair,
            direction=direction, signal_level=level,
            force_base=fb, force_quote=fq, velocity_base=vb, velocity_quote=vq,
            rank_base=rb, rank_quote=rq,
            spread_score=float(snap.get("spread_points", 0.0)),
            tick_volume=float(snap.get("tick_volume", 0.0)),
            bid=float(snap.get("bid", 0.0)), ask=float(snap.get("ask", 0.0)),
            pnl_pips_proxy=pnl, is_win_proxy=is_win, source=src,
            features_json=json.dumps({
                "source": src, "horizon_bars": horizon_bars,
                "force_native_ok": forces is not None,
            }),
        ))
    return out, n_filtered


# ══ KPI ══════════════════════════════════════════════════════════════

def compute_kpis(signals, *, separate_by_tf=True):
    n, wins = len(signals), sum(s.is_win_proxy for s in signals)
    wr  = wins / n if n else 0.0
    pnl = sum(s.pnl_pips_proxy for s in signals)
    by_level = {}
    for lv in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
        sub = [s for s in signals if s.signal_level == lv]
        ns  = len(sub)
        by_level[lv] = {
            "n": ns,
            "wr": round(sum(s.is_win_proxy for s in sub) / ns, 4) if ns else 0.0,
            "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
        }
    by_pair = {}
    for p in sorted({s.pair for s in signals}):
        sub = [s for s in signals if s.pair == p]
        np_ = len(sub)
        by_pair[p] = {
            "n": np_,
            "wr": round(sum(s.is_win_proxy for s in sub) / np_, 4) if np_ else 0.0,
            "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
        }
    result: Dict = {
        "n_total": n, "wr_global": round(wr, 4),
        "pnl_total_pips": round(pnl, 2),
        "by_level": by_level, "by_pair": by_pair,
    }
    if separate_by_tf:
        by_tf = {}
        for tf in sorted({s.timeframe for s in signals}):
            sub  = [s for s in signals if s.timeframe == tf]
            n_tf = len(sub)
            by_tf[tf] = {
                "n": n_tf,
                "wr": round(sum(s.is_win_proxy for s in sub) / n_tf, 4) if n_tf else 0.0,
                "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
            }
        result["by_tf"] = by_tf
    return result


# ══ PERSISTENCE ════════════════════════════════════════════════════════

def persist_signals(db_path, signals):
    if not signals:
        return 0
    con, n = sqlite3.connect(db_path, timeout=10), 0
    try:
        cur = con.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SIGNALS_CLEAN} (
                signal_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT,
                timeframe TEXT, pair TEXT, direction TEXT, signal_level TEXT,
                force_base REAL, force_quote REAL, velocity_base REAL, velocity_quote REAL,
                rank_base INTEGER, rank_quote INTEGER, spread_score REAL,
                tick_volume REAL, bid REAL, ask REAL,
                pnl_pips_proxy REAL, is_win_proxy INTEGER,
                source TEXT, features_json TEXT
            )
        """)
        for s in signals:
            try:
                cur.execute(
                    f"INSERT OR REPLACE INTO {TABLE_SIGNALS_CLEAN} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (s.signal_id, s.timestamp, s.symbol, s.timeframe, s.pair,
                     s.direction, s.signal_level, s.force_base, s.force_quote,
                     s.velocity_base, s.velocity_quote, s.rank_base, s.rank_quote,
                     s.spread_score, s.tick_volume, s.bid, s.ask,
                     s.pnl_pips_proxy, s.is_win_proxy, s.source, s.features_json),
                )
                n += 1
            except Exception as exc:
                log.warning("Insert signal %s failed: %s", s.signal_id, exc)
        con.commit()
    finally:
        con.close()
    return n


def generate_clean_dataset(db_path, *, pairs=PAIRS_V10_DEFAULT, timeframes=TIMEFRAMES_DEFAULT,
                           horizon_bars=None, horizon_by_tf=None, filter_binary=True,
                           truncate_first=True, timestamp="", limit_per_pair_tf=None):
    report = GeneratorReport(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        db_path=db_path, pairs_processed=list(pairs),
        timeframes_processed=list(timeframes),
        source_used="force_native" if _FORCE_NATIVE_OK else "forces_snapshots_filtered",
    )
    hmap = dict(HORIZON_BARS_BY_TF)
    if horizon_by_tf:
        hmap.update(horizon_by_tf)
    if horizon_bars:
        hmap.update({tf: horizon_bars for tf in timeframes})

    if truncate_first:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            con.execute(f"DELETE FROM {TABLE_SIGNALS_CLEAN}")
            con.commit()
            con.close()
        except Exception:
            pass

    all_sigs, n_loaded, n_filt, n_native = [], 0, 0, 0
    for pair in pairs:
        for tf in timeframes:
            snaps = _load_forces_snapshots(db_path, symbol=pair, timeframe=tf, limit=limit_per_pair_tf)
            n_loaded += len(snaps)
            if not snaps:
                continue
            sigs, nf = generate_signals_for_pair_tf(snaps, pair=pair, timeframe=tf,
                                                    horizon_bars=hmap.get(tf, 3),
                                                    filter_binary=filter_binary)
            all_sigs.extend(sigs)
            n_filt   += nf
            n_native += sum(1 for s in sigs if s.source == SignalSource.FORCE_NATIVE.value)

    report.n_snapshots_loaded  = n_loaded
    report.n_signals_generated = len(all_sigs)
    report.n_signals_persisted = persist_signals(db_path, all_sigs)
    report.force_native_pct    = round(n_native / len(all_sigs) * 100, 1) if all_sigs else 0.0
    kpis = compute_kpis(all_sigs)
    report.kpis_by_pair    = kpis["by_pair"]
    report.kpis_by_level   = kpis["by_level"]
    report.kpis_by_tf      = kpis.get("by_tf", {})
    report.audit = {
        "wr_global": kpis["wr_global"], "pnl_total_pips": kpis["pnl_total_pips"],
        "force_native_ok": _FORCE_NATIVE_OK, "force_native_pct": report.force_native_pct,
        "source_used": report.source_used, "n_filtered_binary": n_filt,
        "thresholds": {"A3": FORCE_NATIVE_DELTA_A3, "A2": FORCE_NATIVE_DELTA_A2, "A1": FORCE_NATIVE_DELTA_A1},
    }
    return report


# ══ API LIVE ══════════════════════════════════════════════════════════════

class SignalGeneratorLive:
    """API utilisée par ReplayEngine._decide_one(). Retourne toujours un dict."""

    def generate(self, symbol: str, timeframe: str, bars: List[Dict]) -> Dict[str, Any]:
        if not bars:
            return self._neutral("empty_bars")
        pair = symbol.upper()
        base = pair[:3]
        quote = pair[3:] if len(pair) >= 6 else "USD"
        window = bars[-WINDOW_BARS:] if len(bars) >= WINDOW_BARS else bars
        forces = _compute_forces_native(window, pair, timeframe)
        if forces is not None:
            level, direction, fb, fq, vb, vq, rb, rq = _decide_signal_native(forces, pair)
            return {
                "direction": direction, "signal_level": level,
                "source": SignalSource.FORCE_NATIVE.value,
                "force_base": round(fb, 4), "force_quote": round(fq, 4),
                "delta_force": round(abs(fb - fq), 4),
                "rank_base": rb, "rank_quote": rq,
            }
        last  = bars[-1]
        force = last.get("force", {})
        fb    = float(force.get(base, 0.0))
        fq    = float(force.get(quote, 0.0))
        if fb in BINARY_FORCE_VALUES and fq in BINARY_FORCE_VALUES:
            return self._neutral("binary_forces_rejected")
        prev = bars[-2].get("force", {}) if len(bars) >= 2 else {}
        vb   = fb - float(prev.get(base, fb))
        vq   = fq - float(prev.get(quote, fq))
        all_s = sorted([(c, float(force.get(c, 0.0))) for c in CURRENCIES_V10_FULL], key=lambda x: x[1], reverse=True)
        rmap  = {c: i + 1 for i, (c, _) in enumerate(all_s)}
        rb, rq = rmap.get(base, 99), rmap.get(quote, 99)
        level, direction = decide_signal_level(
            force_base=fb, force_quote=fq, velocity_base=vb, velocity_quote=vq,
            rank_base=rb, rank_quote=rq,
            direction=last.get("direction", "neutre"),
            vitesse=float(last.get("vitesse", 0.0)),
        )
        return {
            "direction": direction, "signal_level": level,
            "source": SignalSource.FORCES_SNAPSHOTS.value,
            "force_base": round(fb, 4), "force_quote": round(fq, 4),
            "delta_force": round(abs(fb - fq), 4),
            "rank_base": rb, "rank_quote": rq,
        }

    @staticmethod
    def _neutral(reason: str) -> Dict[str, Any]:
        return {
            "direction": "NEUTRAL", "signal_level": SIGNAL_LEVEL_NONE,
            "source": f"neutral_{reason}",
            "force_base": 0.0, "force_quote": 0.0, "delta_force": 0.0,
            "rank_base": 99, "rank_quote": 99,
        }


__all__ = [
    "TABLE_SIGNALS_CLEAN", "CURRENCIES_V10_FULL", "PAIRS_V10_DEFAULT",
    "SignalSource", "V10SignalRow", "GeneratorReport", "SignalGeneratorLive",
    "decide_signal_level", "generate_signals_for_pair_tf", "compute_kpis",
    "persist_signals", "generate_clean_dataset", "_load_forces_snapshots",
    "_FORCE_NATIVE_OK",
]
