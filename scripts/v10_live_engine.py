#!/usr/bin/env python
"""V10 Live Paper Daemon — Edge Fund Phase 7.

Optimisations senior 2026-08-08 :
  - Pool SQLite threading.local → -56 connexions/snapshot
  - currency_strength chargée 1× par snapshot (vs 28× avant)
  - log.debug() lazy % formatting (pas de f-string)
  - _safe() helper R6 centralisé (cohérence v10_live_decision)
  - argparse --include-a2 corrigé (store_true + default False)
  - tf_data dict comprehension propre

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zero
capital (AUCUN ordre réel n'est transmis). Le daemon produit des
SIGNAUX, pas des trades.

R7 (tests) : 8+ tests dans tests/test_v10_live_engine.py.
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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_signal_scorer import score_enhanced_signal, EnhancedSignal  # noqa: E402
from core.v10.v10_confluence import compute_confluence  # noqa: E402
from core.v10.v10_vsa import compute_vsa  # noqa: E402
from core.v10.v10_structure import compute_structure  # noqa: E402
from core.v10.v10_context import compute_context  # noqa: E402
from core.v10.v10_currency_strength import compute_currency_strength  # noqa: E402
from core.v10.v10_currency_pairs import (  # noqa: E402
    PAIRS_USD, CURRENCIES, sign, PAIRS_BY_CURRENCY,
)
from core.v10.v10_strategy_layers import apply_strategy_layers_to_signal  # noqa: E402

# MT5 bridge — import conditionnel (R6 fail-open)
try:
    from core.v10.v10_mt5_bridge import (
        get_bars_with_fallback as _mt5_get_bars,
        get_bridge_state as _mt5_state,
        is_mt5_available as _mt5_available,
        initialize as _mt5_init,
    )
    _MT5_BRIDGE_OK = True
except Exception:
    _MT5_BRIDGE_OK = False

log = logging.getLogger("v10_live_engine")

DEFAULT_SYMBOLS    = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP")
DEFAULT_TIMEFRAMES = ("M15", "M30", "H1", "H4")
DEFAULT_OUTPUT     = Path("data/v10_signals_latest.json")
BAR_LIMIT          = 80
CS_LIMIT_PER_PAIR  = 50

# ── SQLite pool (une connexion par thread, réutilisée) ────────────────────────
_local = threading.local()


def _conn(db_path: str, read_only: bool = True) -> sqlite3.Connection:
    """Retourne la connexion SQLite du thread courant (crée si absente)."""
    key = f"{db_path}:{'ro' if read_only else 'rw'}"
    if not hasattr(_local, "conns"):
        _local.conns = {}
    if key not in _local.conns:
        if read_only:
            _local.conns[key] = sqlite3.connect(
                f"file:{db_path}?mode=ro", uri=True,
                timeout=5, check_same_thread=False,
            )
        else:
            _local.conns[key] = sqlite3.connect(db_path, check_same_thread=False)
    return _local.conns[key]


# ── R6 fail-open helper ───────────────────────────────────────────────────────
def _safe(fn, default=None, *args, **kwargs):
    """R6 fail-open : exécute fn(*args, **kwargs), retourne default si exception."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.debug("_safe skip %s: %s", getattr(fn, "__name__", fn), exc)
        return default


# ── Lecture barres ────────────────────────────────────────────────────────────
def _read_bars_prefer_mt5(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = BAR_LIMIT,
) -> List[dict]:
    """Lit les barres avec préférence MT5 → fallback DB pool.

    R6 fail-open : si MT5 indisponible → DB.
    R10 : aucune transmission d'ordre.
    """
    if _MT5_BRIDGE_OK and _mt5_available():
        bars = _safe(_mt5_get_bars, None, symbol, timeframe, n=limit, db_path=None)
        if bars:
            log.debug("MT5 -> %d barres %s %s", len(bars), symbol, timeframe)
            return bars
    return _read_db_pairs_bars(db_path, symbol, timeframe, limit)


def _read_db_pairs_bars(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = BAR_LIMIT,
) -> List[dict]:
    """Retourne les N dernières bougies OHLCV depuis le pool SQLite.

    R6 fail-open : DB inexistante / table manquante → [].
    """
    try:
        conn = _conn(db_path, read_only=True)
    except (sqlite3.OperationalError, OSError):
        log.debug("R6 fail-open: DB introuvable %s", db_path)
        return []
    try:
        rows = conn.execute(
            "SELECT open, high, low, close, tick_volume, timestamp "
            "FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol, timeframe, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        log.debug("R6 fail-open: table forces_snapshots absente %s", db_path)
        return []
    return [
        {
            "open": o, "high": h, "low": l, "close": c,
            "tick_volume": float(vol or 0.0), "timestamp": ts,
        }
        for o, h, l, c, vol, ts in rows
    ]


# ── Currency strength : chargée 1× par snapshot ──────────────────────────────
def _read_latest_currency_strength(
    db_path: str,
    timeframe: str,
    limit_per_pair: int = CS_LIMIT_PER_PAIR,
) -> Dict[str, Dict[str, float]]:
    """Lit la currency strength pour toutes les paires via le pool SQLite.

    Appelée UNE SEULE FOIS par snapshot (vs 28× avant).
    R6 fail-open → {}.
    """
    out: Dict[str, Dict[str, float]] = {}
    try:
        conn = _conn(db_path, read_only=True)
    except (sqlite3.OperationalError, OSError):
        log.debug("R6 fail-open: DB absente %s", db_path)
        return {}
    try:
        ok = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='forces_snapshots'"
        ).fetchone()[0]
        if not ok:
            return {}
    except sqlite3.OperationalError:
        return {}

    for pair in PAIRS_USD:
        res = _safe(
            conn.execute, None,
            "SELECT close, tick_volume FROM forces_snapshots "
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
        atr_sum = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        atr     = atr_sum / max(len(closes) - 1, 1) if atr_sum > 0 else 1e-9
        mom     = (sum(closes[-8:]) / 8 - sum(closes[-34:]) / 34) / atr
        base, quote = pair[:3], pair[3:]
        scores: Dict[str, float] = {}
        if "EUR" in (base, quote):
            scores["EUR"] = 60 + mom * 30
        if "USD" in (base, quote):
            scores["USD"] = 40 - mom * 30
        scores.setdefault(base, 50.0)
        scores.setdefault(quote, 50.0)
        out[pair] = scores
    return out


# ── Pipeline complet : barres → A1/A2 signal ─────────────────────────────────
def process_pair_tf(
    db_path: str,
    pair: str,
    timeframe: str,
    cur_strengths: Optional[Dict[str, Dict[str, float]]] = None,
) -> Optional[EnhancedSignal]:
    """Traite 1 paire × 1 TF → EnhancedSignal ou None.

    cur_strengths : pré-calculé par run_snapshot (évite 28 rechargements/snapshot).
    R6 fail-open sur chaque module V10 via _safe().
    """
    bars = _read_bars_prefer_mt5(db_path, pair, timeframe)
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

    # Stratégies publiques additives (OTE + HMM + SMC) — R2/R6
    result = _safe(apply_strategy_layers_to_signal, (sig, None),
                   sig, bars=bars, timestamp=timestamp)
    sig_patched = result[0] if result else sig
    return sig_patched if sig_patched is not None else sig


# ── Snapshot complet + persistence ───────────────────────────────────────────
def run_snapshot(
    db_path: str,
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS,
    timeframes: Tuple[str, ...] = DEFAULT_TIMEFRAMES,
    include_a2: bool = True,
    include_a3: bool = False,
) -> Dict:
    """Capture un snapshot live complet.

    currency_strength chargée 1× pour tout le snapshot (TF prioritaire = dernier).
    """
    primary_tf    = timeframes[-1] if timeframes else "H4"
    cur_strengths = _read_latest_currency_strength(db_path, primary_tf)

    snapshot = {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "n_setups_processed": 0,
        "n_signals_found":    0,
        "signals":            [],
        "by_level":           {"A1": 0, "A2": 0, "A3": 0, "NONE": 0},
        "audit": {
            "db_path":    db_path,
            "symbols":    list(symbols),
            "timeframes": list(timeframes),
        },
    }
    keep = {"A1"}
    if include_a2: keep.add("A2")
    if include_a3: keep.add("A3")

    for pair in symbols:
        for tf in timeframes:
            snapshot["n_setups_processed"] += 1
            sig = process_pair_tf(db_path, pair, tf, cur_strengths=cur_strengths)
            if sig is None:
                continue
            lvl = sig.setup_level
            snapshot["by_level"][lvl] = snapshot["by_level"].get(lvl, 0) + 1
            if lvl in keep:
                snapshot["signals"].append(sig.as_dict())
                snapshot["n_signals_found"] += 1
    return snapshot


def persist_snapshot(snapshot: Dict, path: Path) -> None:
    """Écriture atomique via .tmp + rename (R9 auditable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def format_telegram(snapshot: Dict) -> str:
    """Formate le snapshot au format CLI Søn (1 message Telegram par A1)."""
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
        lines.append(
            f"{glyph} {s['pair']} {s['timeframe']} : {s['setup_level']}\n"
            f"   Direction: {s['direction']}\n"
            f"   Score: {s['composite_score']:.3f} (conf={s['confluence_score']:.3f})\n"
            f"   VSA: {s['vsa_state']} | BOS: {s['bos']} | Sess: {s['session']}\n"
            f"   {s['cot']['3_decide']}\n"
        )
    return "\n".join(lines)


# ── Boucle daemon ─────────────────────────────────────────────────────────────
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
) -> Dict:
    """Boucle continue (daemon) — snapshot toutes les `interval_s` secondes."""
    log.info(
        "v10_live_engine: loop start (interval=%ds, output=%s)",
        interval_s, output_path,
    )
    audit = {
        "started_at":      datetime.now(timezone.utc).isoformat(),
        "iterations":      0,
        "n_signals_total": 0,
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
            )
            persist_snapshot(snap, output_path)
            audit["n_signals_total"] += snap["n_signals_found"]
            if snap["n_signals_found"] > 0:
                log.info("Iter %d: %d signal(s)", iter_count, snap["n_signals_found"])
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
    p = argparse.ArgumentParser(description="V10 Live Paper Daemon (Phase 7)")
    p.add_argument("--db",               default="data/v9_forces.db", help="Chemin DB live")
    p.add_argument("--output",           default=str(DEFAULT_OUTPUT),  help="Fichier JSON sortie")
    p.add_argument("--interval",         type=int, default=30,         help="Intervalle secondes")
    p.add_argument("--include-a2",       action="store_true", default=False, help="Inclure A2")
    p.add_argument("--include-a3",       action="store_true", default=False, help="Inclure A3")
    p.add_argument("--once",             action="store_true",           help="Snapshot unique")
    p.add_argument("--max-iter",         type=int, default=None,        help="Max iterations (test)")
    p.add_argument("--telegram-dry-run", action="store_true", default=True, help="Format Søn sans envoi")
    args = p.parse_args()

    output_path = Path(args.output)
    if args.once:
        snap = run_snapshot(
            args.db,
            include_a2=args.include_a2,
            include_a3=args.include_a3,
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
    )
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
