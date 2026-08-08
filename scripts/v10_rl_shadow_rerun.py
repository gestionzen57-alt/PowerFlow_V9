#!/usr/bin/env python3
"""
v10_rl_shadow_rerun.py — Re-run ciblé RL SHADOW EURUSD + USDJPY
Sprint 24 — généré par Perplexity GitHub MCP

Objectif:
- Rejouer 100 trades shadow sur EURUSD et USDJPY après le fix JPY (Phase 19)
- Mesurer baseline/shadow WR et gate 30-consécutifs
- Produire un rapport JSON audit trail

Doctrine: R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL (shadow only)
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PAIRS = ["EURUSD", "USDJPY"]
N_TRADES = 100
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _gate_30_consecutive(trades: list[dict]) -> dict:
    best_streak = 0
    current = 0
    for t in trades:
        if bool(t.get("shadow_win", False)):
            current += 1
            best_streak = max(best_streak, current)
        else:
            current = 0
    return {
        "best_streak": best_streak,
        "pass": best_streak >= 30,
    }


def _compute_wr(trades: list[dict], key: str) -> dict:
    vals = [t for t in trades if t.get(key) is not None]
    n = len(vals)
    wins = sum(1 for t in vals if bool(t.get(key)))
    return {
        "n": n,
        "wins": wins,
        "wr": round(wins / n, 4) if n else None,
    }


def run() -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp_utc": ts,
        "sprint": "S24",
        "script": "v10_rl_shadow_rerun.py",
        "pairs": {},
        "summary": {},
        "status": "OK",
    }

    try:
        from core.v10.v10_rl_adapter import run_shadow_session  # type: ignore
    except Exception as e:
        report["status"] = "IMPORT_ERROR"
        report["error"] = str(e)
        out = REPORTS_DIR / f"v10_rl_shadow_rerun_{ts}.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    pair_results = []
    for pair in PAIRS:
        try:
            result = run_shadow_session(pair=pair, n_trades=N_TRADES, mode="SHADOW")
            data = _jsonable(result)
            trades = data.get("trades", []) if isinstance(data, dict) else []

            baseline = _compute_wr(trades, "baseline_win")
            shadow = _compute_wr(trades, "shadow_win")
            gate = _gate_30_consecutive(trades)
            delta = None
            if baseline.get("wr") is not None and shadow.get("wr") is not None:
                delta = round(shadow["wr"] - baseline["wr"], 4)

            pair_report = {
                "pair": pair,
                "baseline": baseline,
                "shadow": shadow,
                "delta_wr": delta,
                "gate_30_consecutive": gate,
                "raw": data,
            }
            report["pairs"][pair] = pair_report
            pair_results.append(pair_report)
        except Exception as e:
            report["pairs"][pair] = {
                "pair": pair,
                "status": "ERROR",
                "error": str(e),
            }

    passed = sum(1 for p in pair_results if p.get("gate_30_consecutive", {}).get("pass") is True)
    report["summary"] = {
        "pairs_tested": len(PAIRS),
        "pairs_ok": len(pair_results),
        "gate_passed": passed,
        "gate_total": len(PAIRS),
        "verdict": "PASS" if passed == len(PAIRS) else f"PARTIAL ({passed}/{len(PAIRS)})",
    }

    out = REPORTS_DIR / f"v10_rl_shadow_rerun_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"report={out}")
    return report


if __name__ == "__main__":
    run()
