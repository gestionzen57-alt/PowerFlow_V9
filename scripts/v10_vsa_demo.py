#!/usr/bin/env python
"""V10 VSA Engine — CLI de demonstration (Phase 2 Edge Fund).

Usage :
  python scripts/v10_vsa_demo.py                       # demo synthetique complet
  python scripts/v10_vsa_demo.py --pair EURUSD --tf M15
  python scripts/v10_vsa_demo.py --json                # sortie machine-readable
  python scripts/v10_vsa_demo.py --case markup        # cas cible (markup/climax/...)
  python scripts/v10_vsa_demo.py --n 60               # n bougies dans le backtest

Doctrine : R1-AGIR (demo sans permission), R6 fail-open (vol=0 -> NEUTRAL),
           R9 audit (chaque affichage imprime le classification_path),
           R10 zero capital (compute only).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_vsa import (  # noqa: E402
    VSAState,
    compute_vsa,
    compute_vsa_series,
)


# ─────────────────────────────────────────────────────────────────────
# Generateurs de bougies synthetiques (R9 audit-friendly, deterministes)
# ─────────────────────────────────────────────────────────────────────
def _baseline_bars(n: int = 40, *, base: float = 1.1000) -> list:
    """Serie 'neutre' : spread=0.0020, vol=1000, close=open+0.0005 (hausse legere)."""
    bars = []
    for i in range(n):
        bars.append({
            "timestamp": f"2026-08-04T{i:02d}:00:00Z",
            "open": base,
            "high": base + 0.0010,
            "low": base - 0.0010,
            "close": base + 0.0005,
            "tick_volume": 1000.0,
        })
    return bars


def _apply_case_markup(bars: list) -> list:
    """MARKUP : wide + high_vol + direction=+1 (non climax)."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1000, "high": 1.1050, "low": 1.0990,
        "close": 1.1040, "tick_volume": 1800.0,
    }
    return bars


def _apply_case_markdown(bars: list) -> list:
    """MARKDOWN : wide + high_vol + direction=-1 (non climax)."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1050, "high": 1.1100, "low": 1.0990,
        "close": 1.1000, "tick_volume": 1800.0,
    }
    return bars


def _apply_case_climax_buying(bars: list) -> list:
    """MARKUP via buying climax (climax volume + direction=+1)."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1095, "high": 1.1100, "low": 1.0990,
        "close": 1.1098, "tick_volume": 3500.0,
    }
    return bars


def _apply_case_climax_selling(bars: list) -> list:
    """MARKDOWN via selling climax (climax volume + direction=-1)."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1095, "high": 1.1100, "low": 1.0990,
        "close": 1.0995, "tick_volume": 3500.0,
    }
    return bars


def _apply_case_accumulation(bars: list) -> list:
    """ACCUMULATION : narrow + high_vol + doji + direction=+1."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1005, "high": 1.1008, "low": 1.1003,
        "close": 1.10055, "tick_volume": 1800.0,
    }
    return bars


def _apply_case_distribution(bars: list) -> list:
    """DISTRIBUTION : narrow + high_vol + doji + direction=-1."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.10045, "high": 1.1008, "low": 1.1003,
        "close": 1.1004, "tick_volume": 1800.0,
    }
    return bars


def _apply_case_no_demand(bars: list) -> list:
    """NO_DEMAND : narrow + dry + direction=+1."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1000, "high": 1.1002, "low": 1.0998,
        "close": 1.1001, "tick_volume": 400.0,
    }
    return bars


def _apply_case_no_supply(bars: list) -> list:
    """NO_SUPPLY : narrow + dry + direction=-1."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1001, "high": 1.1002, "low": 1.0998,
        "close": 1.0999, "tick_volume": 400.0,
    }
    return bars


def _apply_case_neutral(bars: list) -> list:
    """NEUTRAL : volume normal, range etroit, pas de combinaison decisive."""
    bars[-1] = {
        "timestamp": "2026-08-04T39:00:00Z",
        "open": 1.1000, "high": 1.1001, "low": 1.0999,
        "close": 1.10005, "tick_volume": 1000.0,
    }
    return bars


CASE_BUILDERS = {
    "markup": _apply_case_markup,
    "markdown": _apply_case_markdown,
    "climax_buying": _apply_case_climax_buying,
    "climax_selling": _apply_case_climax_selling,
    "accumulation": _apply_case_accumulation,
    "distribution": _apply_case_distribution,
    "no_demand": _apply_case_no_demand,
    "no_supply": _apply_case_no_supply,
    "neutral": _apply_case_neutral,
}


# ─────────────────────────────────────────────────────────────────────
# Affichage ASCII (verdict-first style CEO)
# ─────────────────────────────────────────────────────────────────────
STATE_GLYPH = {
    VSAState.MARKUP: "🟢 MARKUP",
    VSAState.MARKDOWN: "🔴 MARKDOWN",
    VSAState.ACCUMULATION: "🟡 ACCUMULATION",
    VSAState.DISTRIBUTION: "🟠 DISTRIBUTION",
    VSAState.NEUTRAL: "⚪ NEUTRAL",
}

STATE_BAR = {
    VSAState.MARKUP: "█████████████████████████",
    VSAState.MARKDOWN: "█████████████████████████",
    VSAState.ACCUMULATION: "█████████████████████·····",
    VSAState.DISTRIBUTION: "█████████████████████·····",
    VSAState.NEUTRAL: "███████····················",
}

BIAS_GLYPH = {+1: "LONG", -1: "SHORT", 0: "NONE"}


def _bar_for_state(state: str, length: int = 30) -> str:
    """Mini 'bar chart' ASCII en fonction de l'etat."""
    n_full = {
        "MARKUP": 28,
        "MARKDOWN": 28,
        "ACCUMULATION": 18,
        "DISTRIBUTION": 18,
        "NEUTRAL": 9,
    }.get(state, 9)
    return "█" * n_full + "·" * max(0, length - n_full)


def _ascii_print(state_json: dict, *, compact: bool = False) -> None:
    """Affiche le verdict VSA en ASCII (verdict-first)."""
    print("=" * 70)
    print(" V10 VSA ENGINE — Volume Spread Analysis (Wyckoff)")
    print("=" * 70)
    print(f" Pair        : {state_json['symbol']}")
    print(f" Timestamp   : {state_json['timestamp']}")
    print(f" Timeframe   : {state_json['timeframe']}")
    print()

    state = state_json["state"]
    glyph = STATE_GLYPH.get(state, state)
    bar = _bar_for_state(state)
    bias_str = (
        "LONG" if state in ("MARKUP", "ACCUMULATION")
        else "SHORT" if state in ("MARKDOWN", "DISTRIBUTION")
        else "NONE"
    )
    print(f" VERDICT     : {glyph}  [{bar}]  bias={bias_str}")
    print()

    if not compact:
        print(" ── Raw measures ──────────────────────────────────────────────")
        print(f" Spread          : {state_json['spread']:.6f}")
        print(f" Spread relative : {state_json['spread_relative']:.3f}  (vs avg[{5}])")
        print(f" Volume          : {state_json['volume']:.0f}")
        print(f" Volume relative : {state_json['volume_relative']:.3f}  (vs avg[{20}])")
        print(f" Effort/result   : {state_json['effort_vs_result']:.3f}  (body/spread)")
        print(f" Body ratio      : {state_json['body_ratio']:.3f}")
        print(f" Direction       : {state_json['direction']:+d}")
        print()

        flags = state_json["flags"]
        active_flags = [k for k, v in flags.items() if v]
        if active_flags:
            print(" ── Flags ─────────────────────────────────────────────────────")
            for fl in active_flags:
                print(f"   ⚑ {fl}")
            print()

        print(" ── Classification path (R9 audit) ────────────────────────────")
        for step in state_json["classification_path"]:
            print(f"   • {step}")
        print()

        audit = state_json["audit"]
        print(" ── Audit metadata ────────────────────────────────────────────")
        print(f"   n_bars_used  : {audit['n_bars_used']}")
        print(f"   period       : {audit['period']}")
        print(f"   seed         : {audit['seed']}")
        print()

    print("=" * 70)


# Fallback bar pour etat inconnu
STATE_BARS_FALLBACK = {}


def _run_case(args) -> None:
    """Execute le cas (markup/markdown/...) et affiche."""
    n = args.n or 40
    bars = _baseline_bars(n)
    builder = CASE_BUILDERS.get(args.case)
    if builder is None:
        sys.stderr.write(f"Unknown case: {args.case}. Available: {list(CASE_BUILDERS)}\n")
        sys.exit(2)
    bars = builder(bars)

    state = compute_vsa(
        args.pair,
        bars[-1].get("timestamp", "2026-08-04T12:00:00Z"),
        args.tf,
        bars,
        seed=42,
    )
    payload = state.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _ascii_print(payload, compact=args.compact)


def _run_series(args) -> None:
    """Affiche la distribution des etats sur toute la serie (backtest)."""
    n = args.n or 50
    bars = _baseline_bars(n)
    # override per-case sur la derniere bougie
    builder = CASE_BUILDERS.get(args.case)
    if builder is not None:
        bars = builder(bars)

    series = compute_vsa_series(args.pair, args.tf, bars, seed=42)
    counts = {s: 0 for s in VSAState}
    sufficient = [s for s in series if not s.data_insufficient]
    for s in sufficient:
        counts[s.state] += 1

    print("=" * 70)
    print(f" V10 VSA — Distribution sur {len(bars)} bougies — {args.pair} / {args.tf}")
    print("=" * 70)
    print(f" Total classifiees : {len(sufficient)} / {len(bars)}")
    for st in VSAState:
        n_ = counts[st]
        bar = "█" * n_ + "·" * max(0, 20 - n_)
        print(f"  {STATE_GLYPH[st]:<22}  {bar}  ({n_})")
    print()
    print(" DERNIERE BOUGIE :")
    _ascii_print(series[-1].as_dict(), compact=False)


def main() -> int:
    p = argparse.ArgumentParser(description="V10 VSA Engine — CLI demo")
    p.add_argument("--pair", default="EURUSD", help="Symbole (defaut EURUSD)")
    p.add_argument("--tf", default="M15", help="Timeframe M1..D1 (defaut M15)")
    p.add_argument("--case", default="markup",
                   choices=list(CASE_BUILDERS),
                   help="Scenario OHLCV synthetique a appliquer")
    p.add_argument("--n", type=int, default=40, help="Nombre de bougies (defaut 40)")
    p.add_argument("--json", action="store_true", help="Sortie JSON machine-readable")
    p.add_argument("--compact", action="store_true", help="Affichage compact (sans path)")
    p.add_argument("--series", action="store_true",
                   help="Affiche distribution sur toute la serie")
    args = p.parse_args()

    if args.series:
        _run_series(args)
    else:
        _run_case(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
