"""v9_dashboard_enhanced.py — P0-2 motion CEO 48h Champ libre.

Dashboard ameliore avec lecture multi-TF + price action + forward projection.
Integré en single command.

Auteur : Hermes (P0-2 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.dash_enhanced")


def render_section(title: str, lines: list[str]) -> str:
    return f"\n[{title}]\n" + "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 enhanced dashboard (P0-2)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--mode", choices=["full", "compact"], default="full")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    db_path = Path(DB_PATH)
    print("=" * 70)
    print(f"V9 DASHBOARD ENHANCED — {args.symbol} ({datetime.now(timezone.utc).isoformat()[:19]} UTC)")
    print("=" * 70)

    # Section 1 : Multi-TF
    from scripts.v9_multi_timeframe_reader import multi_tf_analysis
    mtf = multi_tf_analysis(args.symbol, db_path)
    lines = []
    for r in mtf["tf_readings"]:
        lines.append(
            f"  [{r['tf']:3s}] trend={r['trend']:9s} "
            f"phase={r['regime_phase']:14s} mom={r['momentum']:+.4f}"
        )
    lines.append(f"  CONFLUENCE : {mtf['confluence']['score']}/100 "
                 f"({mtf['confluence']['alignment']})")
    print(render_section("MULTI-TIMEFRAME", lines))

    # Section 2 : Anticipation
    from scripts.v9_market_anticipation import (
        detect_regime_phase, forward_projection, momentum_divergence,
    )
    import sqlite3
    closes = []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT close FROM candles_d WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 30
            """, (args.symbol,)).fetchall()
            closes = [float(r[0]) for r in rows]
            closes.reverse()
        finally:
            conn.close()
    except Exception:
        pass
    phase = detect_regime_phase(args.symbol, db_path)
    proj = forward_projection(closes, horizon="H+4")
    div = momentum_divergence(closes)
    lines = []
    lines.append(f"  Regime phase  : {phase.get('phase', 'UNKNOWN')}")
    if "position_in_range" in phase:
        lines.append(f"  Position      : {phase['position_in_range']:.1%} of range")
    if "error" not in proj:
        lines.append(f"  H+4 projeté   : {proj.get('projected', 0)} "
                     f"(delta {proj.get('delta_pct', 0):+.2f}%)")
        lines.append(f"  Direction     : {proj.get('direction', '?')}")
        lines.append(f"  Confidence    : {proj.get('confidence', 0)}")
    lines.append(f"  Divergence    : {div.get('divergence', 'NONE')}")
    print(render_section("ANTICIPATION", lines))

    # Section 3 : Price Action
    from scripts.v9_price_action_context import price_action_context
    pa = price_action_context(args.symbol, db_path, tf="D")
    lines = []
    if "error" not in pa:
        lines.append(f"  Pattern       : {pa['pattern'].get('pattern', 'NONE')}")
        lines.append(f"  Note          : {pa['pattern'].get('note', '')}")
        lines.append(f"  Swings        : {pa['swings']['n_highs']} highs, "
                     f"{pa['swings']['n_lows']} lows")
        sr = pa["support_resistance"]
        lines.append(f"  Supports      : {sr['n_supports']}  "
                     f"(nearest {sr['nearest_support']})")
        lines.append(f"  Resistances   : {sr['n_resistances']}  "
                     f"(nearest {sr['nearest_resistance']})")
    else:
        lines.append(f"  Error : {pa['error']}")
    print(render_section("PRICE ACTION", lines))

    # Section 4 : Edge baseline
    lines = [
        "  Mega-edge     : GBPUSD haussiere 11-13h UTC = WR 94.6% +336p (Phase 2)",
        "  L8 BLACKLIST  : regime NEUTRE = 80% pertes (-1623.5p)",
        "  L9 BLACKLIST  : hors london_ny = -129p",
        "  L11 BLACKLIST : behavior KO = -121p",
        "  L13 COALITION : no_coalition WR 98.8% boost x1.5",
        "  L14 INVERSION : mardi BLACKLIST, vendredi MEGA",
        "  L15 SENTIMENT : bearish → blacklist LONG",
    ]
    print(render_section("EDGE BASELINE", lines))

    # Section 5 : Telegram alerts
    lines = [
        "  21 events classifiés (5 sévérités)",
        "  Dispatcher dry_run par défaut",
        "  Telegram integration via env vars",
        "  Cron 48H perfectionnement actif",
    ]
    print(render_section("TELEGRAM ALERTS", lines))

    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())