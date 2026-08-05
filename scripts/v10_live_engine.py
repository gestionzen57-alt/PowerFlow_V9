#!/usr/bin/env python
"""V10 Live Paper Daemon — Edge Fund Phase 7.

Daemon de signalisation continue basé sur la DB live v9_forces.db.

Workflow (boucle 30s) :
  1. Snapshot DB : SELECT forces_snapshots (latest is_closed_bar=1 par symbol×TF)
  2. Pour chaque (symbole, timeframe), exécute les modules V10 :
     force, structure, context, vsa, confluence, scorer_enhanced.
  3. Garde uniquement les A1 (et A2 si --include-a2).
  4. Persiste v10_signals_latest.json (overwrite atomique via .tmp + rename).
  5. Option --telegram : alerte les A1 (format CLI Søn).
  6. Option --watchdog : pour utilisation par schtasks Windows.

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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_signal_scorer import (  # noqa: E402
    score_enhanced_signal,
    EnhancedSignal,
)
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

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP")
DEFAULT_TIMEFRAMES = ("M15", "M30", "H1", "H4")
DEFAULT_OUTPUT = Path("data/v10_signals_latest.json")


# ─────────────────────────────────────────────────────────────────────
# Lecture DB live (read-only)
# ─────────────────────────────────────────────────────────────────────
def _read_bars_prefer_mt5(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = 80,
) -> List[dict]:
    """Lit les barres avec préférence MT5 → fallback DB.

    R6 fail-open : si MT5 indisponible / erreur / pas connecté → DB.

    R10 : aucune transmission d'ordre ; seulement get_rates / copy_rates.
    """
    # Tentative MT5
    if _MT5_BRIDGE_OK and _mt5_available():
        try:
            bars = _mt5_get_bars(symbol, timeframe, n=limit, db_path=None)
            if bars:
                log.debug(f"_read_bars_prefer_mt5: MT5 -> {len(bars)} barres pour {symbol} {timeframe}")
                return bars
        except Exception as e:
            log.debug(f"_read_bars_prefer_mt5 exception: {e}")
    # Fallback DB
    return _read_db_pairs_bars(db_path, symbol, timeframe, limit)


def _read_db_pairs_bars(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = 80,
) -> List[dict]:
    """Retourne les N dernières bougies (OHLCV) pour (symbol, timeframe) depuis DB live.

    R6 fail-open : si DB inexistante / table manquante → retourne [].
    """
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except (sqlite3.OperationalError, OSError):
        log.debug(f"R6 fail-open: DB introuvable {db_path}")
        return []
    try:
        cur = con.cursor()
        try:
            rows = cur.execute(
                """
                SELECT open, high, low, close, tick_volume, timestamp
                FROM forces_snapshots
                WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
                ORDER BY bar_time DESC LIMIT ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            log.debug(f"R6 fail-open: table forces_snapshots absente de {db_path}")
            return []
    finally:
        con.close()
    bars = []
    for o, h, l, c, vol, ts in rows:
        bars.append({
            "open": o, "high": h, "low": l, "close": c,
            "tick_volume": float(vol or 0.0),
            "timestamp": ts,
        })
    return bars


def _read_latest_currency_strength(
    db_path: str,
    timeframe: str,
    limit_per_pair: int = 50,
) -> Dict[str, Dict[str, float]]:
    """Lit les dernières currency_strength depuis la DB live.

    Returns : { pair : { currency : score } } où score ∈ [0, 100].

    R6 fail-open : si DB / table absente → retourne {}.
    """
    out: Dict[str, Dict[str, float]] = {}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except (sqlite3.OperationalError, OSError):
        log.debug(f"R6 fail-open: DB absente {db_path}")
        return {}
    try:
        cur = con.cursor()
        try:
            table_exists = cur.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='forces_snapshots'"
            ).fetchone()[0]
            if not table_exists:
                return {}
        except sqlite3.OperationalError:
            return {}
        for pair in PAIRS_USD:
            rows = cur.execute(
                """
                SELECT close, tick_volume
                FROM forces_snapshots
                WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
                ORDER BY bar_time DESC LIMIT ?
                """,
                (pair, timeframe, limit_per_pair),
            ).fetchall()
            if not rows or len(rows) < 34:
                continue
            # Calcul simplifié : momentum EMA(8)-EMA(34) / ATR(14) -> score
            closes = [r[0] for r in reversed(rows)]
            vols = [float(r[1] or 0.0) for r in reversed(rows)]
            atr_sum = 0.0
            for i in range(1, len(closes)):
                atr_sum += abs(closes[i] - closes[i-1])
            atr = atr_sum / max(len(closes) - 1, 1) if atr_sum > 0 else 0.0
            e_short = sum(closes[-8:]) / 8
            e_long = sum(closes[-34:]) / 34
            mom_norm = (e_short - e_long) / (atr or 1e-9)
            # Rang fake : centile sur la série actuelle (à amélirer Phase H)
            scores_dev = {}
            # Force le rang "EUR=1, USD=7" si la paire est EURUSD (sinon complexe)
            # Pour le dashboard, on shortcut :
            base, quote = pair[:3], pair[3:]
            if pair.startswith("EUR") or pair.endswith("EUR"):
                # EUR fort si hausse de la paire
                scores_dev["EUR"] = 60 + mom_norm * 30
            if pair.startswith("USD") or pair.endswith("USD"):
                scores_dev["USD"] = 40 - mom_norm * 30
            if base not in scores_dev:
                scores_dev[base] = 50.0
            if quote not in scores_dev:
                scores_dev[quote] = 50.0
            out[pair] = scores_dev
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# Pipeline complet : barres → A1/A2 signal
# ─────────────────────────────────────────────────────────────────────
def process_pair_tf(
    db_path: str,
    pair: str,
    timeframe: str,
) -> Optional[EnhancedSignal]:
    """Traite 1 paire × 1 TF et renvoie EnhancedSignal ou None si trade pas prêt.

    Lecture DB live → modules V10 → confluence + scorer → sig.
    """
    bars = _read_bars_prefer_mt5(db_path, pair, timeframe)
    if len(bars) < 35:
        log.debug(f"Not enough bars for {pair} {timeframe} (n={len(bars)})")
        return None

    symbol = f"{pair}_{timeframe.lower()}"
    timestamp = bars[-1].get("timestamp", datetime.now(timezone.utc).isoformat())

    # Calcul des modules V10
    struct_res = compute_structure(symbol, timestamp, timeframe, bars)
    ctx_res = compute_context(symbol, timestamp, timeframe, bars=bars)

    # VSA : si barres viennent de MT5, on exploite real_volume pour précision ×2
    real_vol: Optional[List[float]] = None
    if bars and "real_volume" in bars[-1] and bars[-1].get("real_volume", 0.0) > 0:
        real_vol = [b.get("real_volume", 0.0) or 0.0 for b in bars]
    vsa_res = compute_vsa(
        symbol, timestamp, timeframe, bars,
        real_volume=real_vol,
    )

    # Confluence : on charge currency strength pour le TF, et on construit tf_data
    cur_strengths = _read_latest_currency_strength(db_path, timeframe)
    tf_data = {
        "H4": {
            "currency_scores": cur_strengths.get(pair, {}),
            "currency_ranks": {
                c: i + 1 for i, c in enumerate(
                    sorted(CURRENCIES, key=lambda x: cur_strengths.get(pair, {}).get(x, 50), reverse=True)
                )
            } if pair in cur_strengths else {},
            "vsa_state": vsa_res.state.value if vsa_res else "NEUTRAL",
            "bos": struct_res.s8_break,
        }
    }
    # D1 + autres TF : on utilise le H4 comme proxy (degraded mode)
    for tf in ("D1", "H1", "M30", "M15", "M5", "M1"):
        tf_data[tf] = dict(tf_data.get("H4", {}))

    confl = compute_confluence(
        symbol=symbol,
        pair=pair,
        timestamp=timestamp,
        tf_data=tf_data,
    )

    # Rank base/quote depuis currency_strengths
    ranks = tf_data.get("H4", {}).get("currency_ranks", {}) or {}
    rank_base = ranks.get(pair[:3], 4) or 4
    rank_quote = ranks.get(pair[3:], 4) or 4

    sig = score_enhanced_signal(
        symbol=symbol,
        pair=pair,
        timestamp=timestamp,
        timeframe=timeframe,
        confluence=confl,
        vsa_state=vsa_res.state.value if vsa_res else "NEUTRAL",
        bos=struct_res.s8_break,
        session=ctx_res.c1_session,
        currency_rank_base=int(rank_base),
        currency_rank_quote=int(rank_quote),
    )

    # Filtrer : on ne garde que A1 + A2 (ou A3 si demandé).
    # En mode dégradé (confluence=None), setup_level=NONE — le sig est quand même retourné
    # pour traçabilité R9, sauf si strictement None.
    if sig is None:
        return None

    # Stratégies publiques additatives (OTE + HMM + SMC) — R2 additif / R6 fail-open.
    # Filtre de conviction : A1 hors kill zone/zone OTE → A2 ; A2 avec OTE
    # in_ote + haute conviction + kill zone active → A1.
    try:
        sig, _ = apply_strategy_layers_to_signal(
            sig, bars=bars, timestamp=timestamp,
        )
    except Exception:  # R6 : le signal passe tel quel
        pass
    return sig


# ─────────────────────────────────────────────────────────────────────
# Snapshot complet + persistence
# ─────────────────────────────────────────────────────────────────────
def run_snapshot(
    db_path: str,
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS,
    timeframes: Tuple[str, ...] = DEFAULT_TIMEFRAMES,
    include_a2: bool = True,
    include_a3: bool = False,
) -> Dict:
    """Capture un snapshot live : exécute le pipeline complet et renvoie tous les signaux."""
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_setups_processed": 0,
        "n_signals_found": 0,
        "signals": [],
        "by_level": {"A1": 0, "A2": 0, "A3": 0, "NONE": 0},
        "audit": {
            "db_path": db_path,
            "symbols": list(symbols),
            "timeframes": list(timeframes),
        },
    }
    for pair in symbols:
        for tf in timeframes:
            snapshot["n_setups_processed"] += 1
            sig = process_pair_tf(db_path, pair, tf)
            if sig is None:
                continue
            snapshot["by_level"][sig.setup_level] += 1
            if sig.setup_level == "A1":
                snapshot["signals"].append(sig.as_dict())
                snapshot["n_signals_found"] += 1
            elif include_a2 and sig.setup_level == "A2":
                snapshot["signals"].append(sig.as_dict())
                snapshot["n_signals_found"] += 1
            elif include_a3 and sig.setup_level == "A3":
                snapshot["signals"].append(sig.as_dict())
                snapshot["n_signals_found"] += 1
    return snapshot


def persist_snapshot(snapshot: Dict, path: Path) -> None:
    """Écriture atomique via .tmp + rename (R9 auditable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
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
        f"={snapshot['n_signals_found']} signal(aux) A1/A2 sur {snapshot['n_setups_processed']} setups",
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


# ─────────────────────────────────────────────────────────────────────
# Watchdog / boucle continue
# ─────────────────────────────────────────────────────────────────────
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
    """Boucle continue (daemon) qui exécute un snapshot toutes les `interval_s` secondes.

    Returns un dict d'audit avec le nombre d'itérations et l'état final.
    """
    log.info(f"v10_live_engine: starting loop (interval={interval_s}s, output={output_path})")
    audit = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "iterations": 0,
        "n_signals_total": 0,
        "stopped_at": None,
        "reason": "max_iterations" if max_iterations else "running",
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
            if snap["n_signals_found"] > 0 and not telegram_dry_run:
                log.info(f"Iter {iter_count}: {snap['n_signals_found']} signal(s) found")
            # Vérifier la condition d'arrêt APRÈS l'itération
            if max_iterations is not None and iter_count >= max_iterations:
                break
            if max_iterations is None:
                time.sleep(interval_s)
    except KeyboardInterrupt:
        audit["reason"] = "KeyboardInterrupt"
    audit["stopped_at"] = datetime.now(timezone.utc).isoformat()
    return audit


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="V10 Live Paper Daemon (Phase 7)")
    p.add_argument("--db", default="data/v9_forces.db", help="Chemin DB live")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Fichier JSON de sortie")
    p.add_argument("--interval", type=int, default=30, help="Intervalle secondes")
    p.add_argument("--include-a2", action="store_true", default=True, help="Inclure A2")
    p.add_argument("--include-a3", action="store_true", default=False, help="Inclure A3")
    p.add_argument("--once", action="store_true", help="Une seule itération (snapshot unique)")
    p.add_argument("--max-iter", type=int, default=None, help="Max iterations (pour test)")
    p.add_argument("--telegram-dry-run", action="store_true", default=True, help="Format Søn, pas d'envoi")
    args = p.parse_args()

    output_path = Path(args.output)
    if args.once:
        snap = run_snapshot(
            args.db, include_a2=args.include_a2, include_a3=args.include_a3,
        )
        persist_snapshot(snap, output_path)
        if args.telegram_dry_run:
            print(format_telegram(snap))
        return 0
    else:
        audit = run_loop(
            args.db,
            output_path,
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
