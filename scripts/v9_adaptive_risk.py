"""v9_adaptive_risk.py — Phase 45 motion CEO 48h autopilote.

Adaptive risk manager :
- Volatility targeting (ajuste position size selon vol reelle)
- Dynamic Kelly (ajuste selon regime)
- Correlation-aware sizing

Auteur : Hermes (Phase 45 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.adaptive_risk")


def realized_volatility(pips: list[float], window: int = 20) -> float:
    """Realized vol (std des returns) sur window dernieres valeurs."""
    if len(pips) < window:
        window = len(pips)
    if window < 2:
        return 0.0
    recent = pips[-window:]
    mean = sum(recent) / window
    var = sum((p - mean) ** 2 for p in recent) / window
    return var ** 0.5


def vol_targeting_sizing(base_size: float, current_vol: float,
                            target_vol: float = 8.0,
                            max_size_factor: float = 2.0,
                            min_size_factor: float = 0.25) -> dict:
    """Ajuste sizing selon vol reelle.

    Size_factor = base_size * (target_vol / current_vol)
    Clamp entre [min_factor, max_factor].
    """
    if current_vol <= 0:
        return {"size_factor": 1.0, "raw_factor": 1.0, "reason": "vol_zero"}
    raw = target_vol / current_vol
    clamped = max(min_size_factor, min(max_size_factor, raw))
    final_size = base_size * clamped
    if clamped == max_size_factor and raw > max_size_factor:
        reason = "capped_at_max"
    elif clamped == min_size_factor and raw < min_size_factor:
        reason = "capped_at_min"
    else:
        reason = "in_range"
    return {
        "size_factor": round(clamped, 3),
        "raw_factor": round(raw, 3),
        "final_size": round(final_size, 4),
        "target_vol": target_vol,
        "current_vol": round(current_vol, 3),
        "reason": reason,
    }


def dynamic_kelly(base_kelly: float, regime_factor: float = 1.0,
                    sentiment_factor: float = 1.0,
                    vol_factor: float = 1.0,
                    min_kelly: float = 0.0) -> dict:
    """Kelly dynamique selon regime/sentiment/vol."""
    adjusted = base_kelly * regime_factor * sentiment_factor * vol_factor
    adjusted = max(min_kelly, min(adjusted, 0.5))
    return {
        "base_kelly": round(base_kelly, 4),
        "regime_factor": round(regime_factor, 3),
        "sentiment_factor": round(sentiment_factor, 3),
        "vol_factor": round(vol_factor, 3),
        "adjusted_kelly": round(adjusted, 4),
    }


def correlation_aware_sizing(base_size: float, correlations: list[float],
                                threshold: float = 0.5) -> dict:
    """Reduit sizing si correlations elevees avec autres strategies."""
    if not correlations:
        return {"size_factor": 1.0, "n_high_corr": 0,
                "avg_corr": 0.0, "reason": "no_correlations"}
    avg_corr = sum(correlations) / len(correlations)
    high_corr = [c for c in correlations if abs(c) > threshold]
    n_high = len(high_corr)
    if n_high == 0:
        size_factor = 1.0
        reason = "low_correlation"
    else:
        # Penalty : chaque high corr * 0.2 (max -50%)
        penalty = min(0.5, n_high * 0.2)
        size_factor = max(0.5, 1.0 - penalty)
        reason = f"high_correlation_{n_high}"
    return {
        "size_factor": round(size_factor, 3),
        "n_high_corr": n_high,
        "avg_corr": round(avg_corr, 3),
        "final_size": round(base_size * size_factor, 4),
        "reason": reason,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 adaptive risk (Phase 45)",
    )
    parser.add_argument("--target-vol", type=float, default=8.0)
    parser.add_argument("--current-vol", type=float, default=12.0)
    parser.add_argument("--base-kelly", type=float, default=0.20)
    args = parser.parse_args(argv)

    vt = vol_targeting_sizing(0.5, args.current_vol, args.target_vol)
    dk = dynamic_kelly(args.base_kelly, regime_factor=1.0,
                         sentiment_factor=0.8, vol_factor=0.7)
    cs = correlation_aware_sizing(0.5, [0.6, 0.3, -0.1])

    print("=" * 70)
    print("PHASE 45 — ADAPTIVE RISK")
    print("=" * 70)
    print(f"Vol targeting        :")
    print(f"  current_vol={vt['current_vol']:.2f}  "
          f"target_vol={vt['target_vol']:.2f}")
    print(f"  raw_factor={vt['raw_factor']:.3f}  "
          f"size_factor={vt['size_factor']:.3f}  "
          f"final_size={vt['final_size']:.4f}  "
          f"[{vt['reason']}]")
    print()
    print(f"Dynamic Kelly        :")
    print(f"  base={dk['base_kelly']:.4f}  "
          f"adjusted={dk['adjusted_kelly']:.4f}")
    print()
    print(f"Correlation-aware    :")
    print(f"  avg_corr={cs['avg_corr']:.3f}  n_high={cs['n_high_corr']}  "
          f"size_factor={cs['size_factor']:.3f}  [{cs['reason']}]")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())