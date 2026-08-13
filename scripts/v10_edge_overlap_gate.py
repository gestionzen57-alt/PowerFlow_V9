"""V10 Edge OVERLAP Gate — validation SHADOW→exécutable pour l'edge OVERLAP.

L'edge OVERLAP (fenêtre 12-16 UTC + |delta_forces|≥15) est prouvé en replay
(WR 58-67%, +298-339 pips). Ce script formalise la gate R10 pour passer de
SHADOW (replay) → exécutable (paper/live).

Gate R10 (stricte — edge OVERLAP) :
  - n_trades      ≥ 30 (replay sur données réelles, TP/SL réels)
  - WR            ≥ 54% (baseline edge OVERLAP prouvé)
  - Sharpe        ≥ 0.5 (risk-adjusted)
  - Max DD        ≤ 50 pips
  - Consistency   ≥ 75% (WR stable sur sous-fenêtres glissantes)
  - CEO gate      (validation humaine — toujours requise, hors script)

R6 fail-open : données insuffisantes → INSUFFICIENT, pas de promotion.
R10 : ce script ne passe JAMAIS d'ordre — il produit un verdict.

Doctrine : R1-AGIR, R7-MESURER, R9-AUDITABLE, R10-PROTÉGER.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# Gate R10 — edge OVERLAP (baseline prouvé 58%, on exige 54% pour marges)
GATE_N_TRADES = 30
GATE_WR = 0.54
GATE_SHARPE = 0.5
GATE_MAX_DD_PIPS = 50.0
GATE_CONSISTENCY = 0.75


def _sharpe_like(pnls: list) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd


def _max_dd_pips(pnls: list) -> float:
    """Drawdown max en pips (somme des pertes consécutives max)."""
    max_dd = 0.0
    cum = 0.0
    for p in pnls:
        if p < 0:
            cum += p
            max_dd = min(max_dd, cum)
        else:
            cum = 0.0
    return abs(max_dd)


def _consistency(pnls: list, window: int = 10) -> float:
    """Fraction de sous-fenêtres glissantes où le WR local ≥ WR global - 10pts."""
    if len(pnls) < window:
        return 0.0
    global_wr = sum(1 for p in pnls if p > 0) / len(pnls)
    threshold = global_wr - 0.10
    n_windows = 0
    n_ok = 0
    for i in range(0, len(pnls) - window + 1, window):
        sub = pnls[i:i + window]
        local_wr = sum(1 for p in sub if p > 0) / len(sub)
        n_windows += 1
        if local_wr >= threshold:
            n_ok += 1
    return n_ok / n_windows if n_windows > 0 else 0.0


def evaluate_edge(trades: list) -> dict:
    """Évalue un bucket de trades OVERLAP contre la gate R10 stricte."""
    n = len(trades)
    result = {
        "n_trades": n, "gates_passed": 0, "promote_eligible": False,
        "ceof_gate_pending": True,  # toujours requise hors script
    }

    if n < GATE_N_TRADES:
        result["verdict"] = "INSUFFICIENT"
        result["reasons"] = [f"n<{GATE_N_TRADES} (need {GATE_N_TRADES - n} more)"]
        return result

    wins = sum(1 for t in trades if t.get("pnl_pips", 0) > 0)
    wr = wins / n
    pnls = [t.get("pnl_pips", 0.0) for t in trades]
    sharpe = _sharpe_like(pnls)
    max_dd = _max_dd_pips(pnls)
    consistency = _consistency(pnls)
    total_pnl = sum(pnls)

    gates = {
        "n_trades": n >= GATE_N_TRADES,
        "wr": wr >= GATE_WR,
        "sharpe": sharpe >= GATE_SHARPE,
        "max_dd": max_dd <= GATE_MAX_DD_PIPS,
        "consistency": consistency >= GATE_CONSISTENCY,
    }
    # n_trades est un prérequis, pas un gate compté (toujours true ici)
    scored_gates = {k: v for k, v in gates.items() if k != "n_trades"}
    passed = sum(1 for v in scored_gates.values() if v)

    result.update({
        "wr": round(wr, 4), "sharpe": round(sharpe, 3),
        "max_dd_pips": round(max_dd, 2),
        "consistency": round(consistency, 4),
        "total_pnl_pips": round(total_pnl, 2),
        "gates": gates,
        "gates_passed": passed,
        "promote_eligible": passed == 4,  # 4 gates scorés (wr, sharpe, dd, consistency)
        "verdict": "PROMOTE" if passed == 4 else "HOLD",
    })
    if passed < 4:
        failed = [k for k, v in scored_gates.items() if not v]
        result["reasons"] = [f"gate failed: {','.join(failed)}"]
    else:
        result["reasons"] = ["all gates passed — CEO gate pending"]
    return result


def load_replay_trades(replay_path: Path) -> list:
    """Charge les trades d'un rapport replay edge OVERLAP."""
    if not replay_path.exists():
        return []
    d = json.loads(replay_path.read_text(encoding="utf-8"))
    return d.get("trades", [])


def load_daily_learning_trades(learning_path: Path) -> list:
    """Charge les trades agrégés de l'historique daily_learning."""
    if not learning_path.exists():
        return []
    d = json.loads(learning_path.read_text(encoding="utf-8"))
    trades = []
    for entry in d.get("history", []):
        for t in entry.get("trades", []):
            trades.append({
                "pair": t.get("pair"),
                "direction": t.get("direction"),
                "pnl_pips": t.get("pnl_pips", 0.0),
                "delta": t.get("delta", 0.0),
                "bar_time": t.get("bar_time"),
                "date": entry.get("date"),
            })
    return trades


def main() -> int:
    # Source 1 : replay cumulé (méthode la plus honnête, TP/SL réels)
    replay_path = ROOT / "reports" / "v10_shadow_edge_replay_2026-08-11.json"
    replay_trades = load_replay_trades(replay_path)
    # Source 2 : daily learning (données du jour, proxy close[t+3]-close[t])
    learning_path = ROOT / "reports" / "v10_daily_learning.json"
    daily_trades = load_daily_learning_trades(learning_path)

    # On évalue les 2 sources séparément (transparence R9)
    replay_eval = evaluate_edge(replay_trades)
    daily_eval = evaluate_edge(daily_trades)

    # Verdict consolidé : PROMOTE seulement si les 2 sources valident
    # (replay = TP/SL réels, daily = proxy — les 2 doivent converger)
    consolidated = "PROMOTE" if (
        replay_eval.get("verdict") == "PROMOTE"
        and daily_eval.get("verdict") == "PROMOTE"
    ) else "HOLD"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge": "OVERLAP_12_16_UTC_delta_forces_gte_15",
        "sources": {
            "replay_cumul_7j": {
                "path": str(replay_path),
                "n_trades": len(replay_trades),
                "eval": replay_eval,
            },
            "daily_learning_live": {
                "path": str(learning_path),
                "n_trades": len(daily_trades),
                "eval": daily_eval,
            },
        },
        "consolidated_verdict": consolidated,
        "gate_r10": {
            "n_trades_min": GATE_N_TRADES,
            "wr_min": GATE_WR,
            "sharpe_min": GATE_SHARPE,
            "max_dd_pips_max": GATE_MAX_DD_PIPS,
            "consistency_min": GATE_CONSISTENCY,
        },
        "audit": {
            "r9_honest": "replay=TP/SL reels | daily=proxy close[t+3]-close[t]",
            "r10": "recommandation only, zero order real — CEO gate toujours requise",
            "note": "PROMOTE exige replay ET daily convergents + CEO gate",
        },
    }

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = ROOT / "reports" / f"v10_edge_overlap_gate_{date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport gate: %s", out)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())