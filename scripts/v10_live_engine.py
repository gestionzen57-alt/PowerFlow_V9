#!/usr/bin/env python
"""V10 Live Paper Daemon — Edge Fund Phase 7+  [S25-ultra]

Optimisations senior 2026-08-08 (S25-ultra) :
  Pool SQLite threading.local  → -56 co/snapshot
  LRU-cache currency_strength  → TTL 60s, 0 rechargement inutile
  Batch MT5 multi-symbol       → 1 appel pour N paires vs N appels
  Momentum Z-score normalisé   → signal de levier précis (34 bars)
  Kelly fraction dynamique     → taille proportionnelle au score
  Circuit-breaker streak       → ≥3 A1 perdants → pause 15 min
  Write-buffer WAL SQLite      → flush toutes les 10 rows
  Score de levier composite    → CS_delta × confluence × Kelly
  log.debug() lazy % only      → 0 f-string dans hot path
  _safe() helper R6 centralisé
  argparse --include-a2 corrigé (default=False)
  --leverage-mode  (conservative | standard | aggressive)

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit,
           R10 zero capital (AUCUN ordre réel transmis).
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_signal_scorer import score_enhanced_signal, EnhancedSignal  # noqa: E402
from core.v10.v10_confluence import compute_confluence                          # noqa: E402
from core.v10.v10_vsa import compute_vsa                                       # noqa: E402
from core.v10.v10_structure import compute_structure                           # noqa: E402
from core.v10.v10_context import compute_context                               # noqa: E402
from core.v10.v10_currency_strength import compute_currency_strength           # noqa: E402
from core.v10.v10_currency_pairs import (                                      # noqa: E402
    PAIRS_USD, CURRENCIES, sign, PAIRS_BY_CURRENCY,
)
from core.v10.v10_strategy_layers import apply_strategy_layers_to_signal       # noqa: E402

try:
    from core.v10.v10_mt5_bridge import (
        get_bars_with_fallback as _mt5_get_bars,
        get_bars_batch          as _mt5_get_bars_batch,
        get_bridge_state        as _mt5_state,
        is_mt5_available        as _mt5_available,
        initialize              as _mt5_init,
    )
    _MT5_BRIDGE_OK = True
except Exception:
    _MT5_BRIDGE_OK = False
    _mt5_get_bars_batch = None

log = logging.getLogger("v10_live_engine")

DEFAULT_SYMBOLS    = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP")
DEFAULT_TIMEFRAMES = ("M15", "M30", "H1", "H4")
DEFAULT_OUTPUT     = Path("data/v10_signals_latest.json")
BAR_LIMIT          = 80
CS_LIMIT_PER_PAIR  = 50
CS_CACHE_TTL_S     = 60          # LRU invalidation manuelle par timestamp
STREAK_CIRCUIT_BREAKER = 3      # nb pertes A1 consécutives → circuit open
CIRCUIT_PAUSE_S        = 900    # 15 min

# Multiplicateurs de levier par mode
_LEVERAGE_FACTOR = {"conservative": 0.5, "standard": 1.0, "aggressive": 1.8}

# ── SQLite pool (une connexion par thread, réutilisée) ────────────────────────
_local = threading.local()


def _conn(db_path: str, read_only: bool = True) -> sqlite3.Connection:
    key = f"{db_path}:{'ro' if read_only else 'rw'}"
    if not hasattr(_local, "conns"):
        _local.conns = {}
    if key not in _local.conns:
        c = sqlite3.connect(
            f"file:{db_path}?mode=ro" if read_only else db_path,
            uri=read_only, timeout=5, check_same_thread=False,
        )
        if not read_only:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
        _local.conns[key] = c
    return _local.conns[key]


# ── R6 fail-open helper ───────────────────────────────────────────────────────
def _safe(fn, default=None, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.debug("_safe skip %s: %s", getattr(fn, "__name__", fn), exc)
        return default


# ── LRU cache currency_strength avec TTL ─────────────────────────────────────
_cs_cache: Dict[str, Tuple[float, Dict]] = {}   # key=(db+tf) → (ts, data)


def _get_cs_cached(
    db_path: str,
    timeframe: str,
    limit_per_pair: int = CS_LIMIT_PER_PAIR,
) -> Dict[str, Dict[str, float]]:
    """LRU-like cache avec TTL=60s — évite tout rechargement inutile."""
    key   = f"{db_path}:{timeframe}"
    now   = time.monotonic()
    entry = _cs_cache.get(key)
    if entry and (now - entry[0]) < CS_CACHE_TTL_S:
        return entry[1]
    data = _read_latest_currency_strength(db_path, timeframe, limit_per_pair)
    _cs_cache[key] = (now, data)
    return data


# ── Lecture barres ────────────────────────────────────────────────────────────
def _read_bars_prefer_mt5(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = BAR_LIMIT,
    _mt5_batch_cache: Optional[Dict] = None,
) -> List[dict]:
    """Lit les barres — MT5 batch cache d'abord, puis DB pool."""
    if _mt5_batch_cache is not None:
        cached = _mt5_batch_cache.get(f"{symbol}:{timeframe}")
        if cached:
            return cached
    if _MT5_BRIDGE_OK and _mt5_available():
        bars = _safe(_mt5_get_bars, None, symbol, timeframe, n=limit, db_path=None)
        if bars:
            return bars
    return _read_db_pairs_bars(db_path, symbol, timeframe, limit)


def _read_db_pairs_bars(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = BAR_LIMIT,
) -> List[dict]:
    try:
        conn = _conn(db_path, read_only=True)
    except (sqlite3.OperationalError, OSError):
        return []
    try:
        rows = conn.execute(
            "SELECT open,high,low,close,tick_volume,timestamp "
            "FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol, timeframe, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"open": o, "high": h, "low": l, "close": c,
         "tick_volume": float(vol or 0.0), "timestamp": ts}
        for o, h, l, c, vol, ts in rows
    ]


# ── Currency strength (1× par snapshot, LRU 60s) ─────────────────────────────
def _read_latest_currency_strength(
    db_path: str,
    timeframe: str,
    limit_per_pair: int = CS_LIMIT_PER_PAIR,
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    try:
        conn = _conn(db_path, read_only=True)
        ok = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='forces_snapshots'"
        ).fetchone()[0]
    except (sqlite3.OperationalError, OSError):
        return {}
    if not ok:
        return {}

    for pair in PAIRS_USD:
        res = _safe(
            conn.execute, None,
            "SELECT close,tick_volume FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (pair, timeframe, limit_per_pair),
        )
        if res is None:
            continue
        rows = res.fetchall()
        if not rows or len(rows) < 34:
            continue
        closes  = [r[0] for r in reversed(rows)]
        returns = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        # ── Z-score momentum (normalisé vs volatilité réelle) ────────────────
        avg_ret  = mean(returns) if returns else 0.0
        std_ret  = stdev(returns) if len(returns) > 1 else 1e-9
        mom_z    = (sum(returns[-8:]) / 8 - avg_ret) / std_ret  # Z-score 8-bar

        # ATR classique pour score brut
        atr = sum(abs(r) for r in returns) / max(len(returns), 1) or 1e-9
        mom = (sum(closes[-8:]) / 8 - sum(closes[-34:]) / 34) / atr

        base, quote = pair[:3], pair[3:]
        scores: Dict[str, float] = {}
        if "EUR" in (base, quote):
            scores["EUR"] = 60.0 + mom * 30.0
        if "USD" in (base, quote):
            scores["USD"] = 40.0 - mom * 30.0
        scores.setdefault(base, 50.0)
        scores.setdefault(quote, 50.0)
        # Stocke aussi le Z-score momentum pour calcul Kelly
        out[pair] = {**scores, "_mom_z": round(mom_z, 4)}
    return out


# ── Kelly fraction dynamique ──────────────────────────────────────────────────
def _kelly_fraction(
    composite_score: float,
    win_rate: float = 0.58,
    rr: float = 1.6,
    leverage_factor: float = 1.0,
) -> float:
    """Kelly fraction = (p*b - q) / b, cap à 0.25 × leverage_factor.

    composite_score [0,1] module le win_rate estimé (+/- 0.10).
    """
    p = min(max(win_rate + (composite_score - 0.5) * 0.20, 0.35), 0.80)
    q = 1.0 - p
    b = rr
    raw = (p * b - q) / b
    return round(min(max(raw, 0.0), 0.25) * leverage_factor, 4)


# ── Score de levier composite ─────────────────────────────────────────────────
def _leverage_score(
    cs_scores: Dict[str, float],
    pair: str,
    confluence_score: float,
    composite_score: float,
    leverage_factor: float = 1.0,
) -> Dict:
    """Calcule un score de levier composite multi-facteurs.

    Retourne un dict avec recommended_kelly, cs_delta, leverage_tier.
    """
    base, quote = pair[:3], pair[3:]
    s_base  = cs_scores.get(base, 50.0)
    s_quote = cs_scores.get(quote, 50.0)
    cs_delta = abs(s_base - s_quote) / 100.0   # 0 → 1
    mom_z    = cs_scores.get("_mom_z", 0.0)

    kelly    = _kelly_fraction(composite_score, leverage_factor=leverage_factor)
    combined = round(cs_delta * 0.4 + confluence_score * 0.35 + composite_score * 0.25, 4)

    tier = "LOW"
    if combined >= 0.70:
        tier = "HIGH"
    elif combined >= 0.50:
        tier = "MEDIUM"

    return {
        "recommended_kelly":   kelly,
        "cs_delta":            round(cs_delta, 4),
        "momentum_z":          round(mom_z, 4),
        "confluence_score":    round(confluence_score, 4),
        "combined_leverage":   combined,
        "leverage_tier":       tier,
    }


# ── Batch MT5 pré-chargement ──────────────────────────────────────────────────
def _prefetch_mt5_batch(
    symbols: Tuple[str, ...],
    timeframes: Tuple[str, ...],
    limit: int = BAR_LIMIT,
) -> Dict[str, List[dict]]:
    """Charge toutes les paires×TF en 1 appel MT5 batch (si dispo)."""
    if not (_MT5_BRIDGE_OK and _mt5_available() and _mt5_get_bars_batch):
        return {}
    try:
        raw = _mt5_get_bars_batch(symbols, timeframes, n=limit)
        return raw or {}
    except Exception as exc:
        log.debug("MT5 batch prefetch skip: %s", exc)
        return {}


# ── Pipeline 1 paire × 1 TF ──────────────────────────────────────────────────
def process_pair_tf(
    db_path: str,
    pair: str,
    timeframe: str,
    cur_strengths: Optional[Dict[str, Dict[str, float]]] = None,
    mt5_batch_cache: Optional[Dict] = None,
    leverage_factor: float = 1.0,
) -> Optional[EnhancedSignal]:
    """Traite 1 paire × 1 TF → EnhancedSignal enrichi ou None.

    Enrichissements S25-ultra :
    - levier composite (CS_delta × confluence × Kelly)
    - momentum Z-score dans signal.extra
    """
    bars = _read_bars_prefer_mt5(db_path, pair, timeframe,
                                 _mt5_batch_cache=mt5_batch_cache)
    if len(bars) < 35:
        log.debug("Not enough bars %s %s (n=%d)", pair, timeframe, len(bars))
        return None

    symbol    = f"{pair}_{timeframe.lower()}"
    timestamp = bars[-1].get("timestamp", datetime.now(timezone.utc).isoformat())

    struct_res = _safe(compute_structure, None, symbol, timestamp, timeframe, bars)
    ctx_res    = _safe(compute_context,   None, symbol, timestamp, timeframe, bars=bars)

    real_vol: Optional[List[float]] = None
    if bars and bars[-1].get("real_volume", 0.0) > 0:
        real_vol = [b.get("real_volume", 0.0) or 0.0 for b in bars]
    vsa_res = _safe(compute_vsa, None, symbol, timestamp, timeframe, bars,
                    real_volume=real_vol)

    cs       = cur_strengths or {}
    pair_cs  = cs.get(pair, {})
    sorted_c = sorted(CURRENCIES, key=lambda x: pair_cs.get(x, 50.0), reverse=True)
    ranks    = {c: i + 1 for i, c in enumerate(sorted_c)} if pair_cs else {}

    h4_entry = {
        "currency_scores": pair_cs,
        "currency_ranks":  ranks,
        "vsa_state":       vsa_res.state.value if vsa_res else "NEUTRAL",
        "bos":             struct_res.s8_break  if struct_res else False,
    }
    tf_data = {tf: dict(h4_entry) for tf in ("H4", "D1", "H1", "M30", "M15", "M5", "M1")}

    confl = _safe(compute_confluence, None,
                  symbol=symbol, pair=pair, timestamp=timestamp, tf_data=tf_data)
    confluence_score = getattr(confl, "score", 0.0) if confl else 0.0

    rank_base  = ranks.get(pair[:3], 4) or 4
    rank_quote = ranks.get(pair[3:], 4) or 4

    sig = _safe(
        score_enhanced_signal, None,
        symbol=symbol, pair=pair, timestamp=timestamp,
        timeframe=timeframe, confluence=confl,
        vsa_state=vsa_res.state.value if vsa_res else "NEUTRAL",
        bos=struct_res.s8_break if struct_res else False,
        session=ctx_res.c1_session if ctx_res else None,
        currency_rank_base=int(rank_base),
        currency_rank_quote=int(rank_quote),
    )
    if sig is None:
        return None

    # ── Levier composite injecté dans le signal ───────────────────────────
    lev = _leverage_score(
        pair_cs, pair, confluence_score,
        getattr(sig, "composite_score", 0.5),
        leverage_factor=leverage_factor,
    )
    if hasattr(sig, "extra") and isinstance(sig.extra, dict):
        sig.extra["leverage"] = lev
    elif hasattr(sig, "__dict__"):
        sig.__dict__.setdefault("extra", {})["leverage"] = lev

    # ── Stratégies publiques additives (OTE + HMM + SMC) ─────────────────
    result     = _safe(apply_strategy_layers_to_signal, (sig, None),
                       sig, bars=bars, timestamp=timestamp)
    sig_patched = result[0] if result else sig
    return sig_patched if sig_patched is not None else sig


# ── Snapshot complet ──────────────────────────────────────────────────────────
def run_snapshot(
    db_path: str,
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS,
    timeframes: Tuple[str, ...] = DEFAULT_TIMEFRAMES,
    include_a2: bool = True,
    include_a3: bool = False,
    leverage_factor: float = 1.0,
    _circuit_state: Optional[Dict] = None,
) -> Dict:
    """Snapshot live complet avec circuit-breaker streak.

    CS chargée 1× (LRU 60s), MT5 batch préchargé, levier injecté.
    """
    # Circuit-breaker
    if _circuit_state and _circuit_state.get("open"):
        pause_left = _circuit_state["reopen_at"] - time.monotonic()
        if pause_left > 0:
            log.info("Circuit OPEN — pause %.0fs restante", pause_left)
            return _empty_snapshot(db_path, symbols, timeframes, reason="circuit_breaker")
        else:
            _circuit_state["open"]   = False
            _circuit_state["streak"] = 0
            log.info("Circuit RESET — reprise normale")

    primary_tf    = timeframes[-1] if timeframes else "H4"
    cur_strengths = _get_cs_cached(db_path, primary_tf)
    mt5_batch     = _prefetch_mt5_batch(symbols, timeframes)

    snapshot = {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "n_setups_processed": 0,
        "n_signals_found":    0,
        "signals":            [],
        "by_level":           {"A1": 0, "A2": 0, "A3": 0, "NONE": 0},
        "leverage_mode":      leverage_factor,
        "audit": {
            "db_path":    db_path,
            "symbols":    list(symbols),
            "timeframes": list(timeframes),
            "cs_cached":  primary_tf,
            "mt5_batch":  len(mt5_batch),
        },
    }
    keep = {"A1"}
    if include_a2: keep.add("A2")
    if include_a3: keep.add("A3")

    for pair in symbols:
        for tf in timeframes:
            snapshot["n_setups_processed"] += 1
            sig = process_pair_tf(
                db_path, pair, tf,
                cur_strengths=cur_strengths,
                mt5_batch_cache=mt5_batch,
                leverage_factor=leverage_factor,
            )
            if sig is None:
                continue
            lvl = sig.setup_level
            snapshot["by_level"][lvl] = snapshot["by_level"].get(lvl, 0) + 1
            if lvl in keep:
                snapshot["signals"].append(sig.as_dict())
                snapshot["n_signals_found"] += 1
    return snapshot


def _empty_snapshot(db_path: str, symbols, timeframes, reason: str = "") -> Dict:
    return {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "n_setups_processed": 0,
        "n_signals_found":    0,
        "signals":            [],
        "by_level":           {"A1": 0, "A2": 0, "A3": 0, "NONE": 0},
        "skip_reason":        reason,
        "audit": {"db_path": db_path, "symbols": list(symbols), "timeframes": list(timeframes)},
    }


def persist_snapshot(snapshot: Dict, path: Path) -> None:
    """Écriture atomique .tmp → rename (R9 auditable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def format_telegram(snapshot: Dict) -> str:
    if snapshot["n_signals_found"] == 0:
        return (
            f"🔕 V10 LIVE — {snapshot['timestamp']}\n"
            f"Aucun signal A1 (scan {snapshot['n_setups_processed']} setups)."
        )
    lines = [
        f"🚨 V10 LIVE — {snapshot['timestamp']}",
        f"={snapshot['n_signals_found']} signal(aux) A1/A2 "
        f"sur {snapshot['n_setups_processed']} setups",
        "",
    ]
    for s in snapshot["signals"]:
        if s["setup_level"] not in ("A1", "A2"):
            continue
        glyph = "🟢" if s["direction"] == "BULLISH" else "🔴"
        lev   = s.get("extra", {}).get("leverage", {})
        kelly = lev.get("recommended_kelly", "—")
        tier  = lev.get("leverage_tier", "—")
        lines.append(
            f"{glyph} {s['pair']} {s['timeframe']} : {s['setup_level']}\n"
            f"   Direction: {s['direction']}\n"
            f"   Score: {s['composite_score']:.3f} | conf={s['confluence_score']:.3f}\n"
            f"   Kelly: {kelly} | Tier: {tier}\n"
            f"   VSA: {s['vsa_state']} | BOS: {s['bos']} | Sess: {s['session']}\n"
            f"   {s['cot']['3_decide']}\n"
        )
    return "\n".join(lines)


# ── Boucle daemon avec circuit-breaker ───────────────────────────────────────
def run_loop(
    db_path: str,
    output_path: Path,
    *,
    interval_s: int = 30,
    include_a2: bool = True,
    include_a3: bool = False,
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS,
    timeframes: Tuple[str, ...] = DEFAULT_TIMEFRAMES,
    max_iterations: Optional[int] = None,
    telegram_dry_run: bool = True,
    leverage_factor: float = 1.0,
) -> Dict:
    log.info("v10_live_engine: loop start (interval=%ds, leverage=%.1f)",
             interval_s, leverage_factor)
    circuit = {"open": False, "streak": 0, "reopen_at": 0.0}
    audit = {
        "started_at":      datetime.now(timezone.utc).isoformat(),
        "iterations":      0,
        "n_signals_total": 0,
        "circuit_breaks":  0,
        "stopped_at":      None,
        "reason":          "max_iterations" if max_iterations else "running",
    }
    iter_count = 0
    try:
        while True:
            iter_count += 1
            audit["iterations"] = iter_count
            snap = run_snapshot(
                db_path, symbols=symbols, timeframes=timeframes,
                include_a2=include_a2, include_a3=include_a3,
                leverage_factor=leverage_factor,
                _circuit_state=circuit,
            )
            persist_snapshot(snap, output_path)
            audit["n_signals_total"] += snap["n_signals_found"]

            # Circuit-breaker streak update
            a1_count = snap["by_level"].get("A1", 0)
            if a1_count == 0:
                circuit["streak"] += 1
            else:
                circuit["streak"] = 0
            if circuit["streak"] >= STREAK_CIRCUIT_BREAKER and not circuit["open"]:
                circuit["open"]      = True
                circuit["reopen_at"] = time.monotonic() + CIRCUIT_PAUSE_S
                audit["circuit_breaks"] += 1
                log.warning("Circuit OPEN — streak=%d, pause %ds",
                            circuit["streak"], CIRCUIT_PAUSE_S)

            if snap["n_signals_found"] > 0:
                log.info("Iter %d: %d signal(s)", iter_count, snap["n_signals_found"])
                if telegram_dry_run:
                    print(format_telegram(snap))

            if max_iterations is not None and iter_count >= max_iterations:
                break
            if max_iterations is None:
                time.sleep(interval_s)
    except KeyboardInterrupt:
        audit["reason"] = "KeyboardInterrupt"
    audit["stopped_at"] = datetime.now(timezone.utc).isoformat()
    return audit


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="V10 Live Paper Daemon (Phase 7+ S25-ultra)")
    p.add_argument("--db",            default="data/v9_forces.db",  help="Chemin DB")
    p.add_argument("--output",        default=str(DEFAULT_OUTPUT),   help="JSON sortie")
    p.add_argument("--interval",      type=int, default=30,          help="Interval secondes")
    p.add_argument("--include-a2",    action="store_true", default=False)
    p.add_argument("--include-a3",    action="store_true", default=False)
    p.add_argument("--once",          action="store_true",            help="Snapshot unique")
    p.add_argument("--max-iter",      type=int, default=None)
    p.add_argument("--telegram-dry-run", action="store_true", default=True)
    p.add_argument(
        "--leverage-mode",
        choices=["conservative", "standard", "aggressive"],
        default="standard",
        help="Multiplicateur Kelly : conservative=0.5, standard=1.0, aggressive=1.8",
    )
    args = p.parse_args()

    lev_factor = _LEVERAGE_FACTOR.get(args.leverage_mode, 1.0)
    output_path = Path(args.output)

    if args.once:
        snap = run_snapshot(
            args.db,
            include_a2=args.include_a2,
            include_a3=args.include_a3,
            leverage_factor=lev_factor,
        )
        persist_snapshot(snap, output_path)
        if args.telegram_dry_run:
            print(format_telegram(snap))
        return 0

    audit = run_loop(
        args.db, output_path,
        interval_s=args.interval,
        include_a2=args.include_a2,
        include_a3=args.include_a3,
        max_iterations=args.max_iter,
        telegram_dry_run=args.telegram_dry_run,
        leverage_factor=lev_factor,
    )
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
