"""mcp-v9-risk-dashboard — MCP server pour risque portfolio temps réel.

Expose les 3 modules risque aux clients MCP (HITL CEO critique) :
  - get_current_dd_state()           → DrawdownProtector (5 paliers)
  - get_correlation_matrix(days)     → matrice corrélation cross-paires
  - get_risk_parity_weights(capital) → budgets risk-parity par paire
  - simulate_dd_step(scenario)       → dry-run : impact d'un scénario DD

Sécurité : read-only strict (URI mode=ro). Calculs via core/v9/.
Origine : motion CEO auto-pilote 2026-07-28 (top-3 MCP à levier).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
DEFAULT_PAIRS = ["GBPUSD", "USDJPY", "USDCHF", "EURUSD", "AUDUSD", "NZDUSD"]


def _connect_ro() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def handle_get_current_dd_state(args: dict) -> dict:
    """État courant du DrawdownProtector (5 paliers : normal/reduce_50/halt_24h/halt_forever).

    Args : lookback_days (int, default 30).
    Returns : DrawdownState.to_dict() + palier actif + recommandations.
    """
    days = max(1, min(int(args.get("lookback_days", 30)), 90))
    conn = _connect_ro()
    try:
        # Cumul P&L depuis J-X days
        cutoff_iso = (
            __import__("datetime").datetime.fromtimestamp(
                time.time() - days * 86400, tz=__import__("datetime").timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")
        )
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(resolution_pips), 0) AS cum_pips,
                COALESCE(MAX(resolution_pips), 0) AS max_trade_pips,
                COALESCE(MIN(resolution_pips), 0) AS min_trade_pips,
                COUNT(*) AS n,
                SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS n_wins,
                SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) AS n_losses
            FROM decisions
            WHERE is_win IS NOT NULL AND timestamp >= ?
            """,
            (cutoff_iso,),
        ).fetchone()
        cum = row["cum_pips"] or 0
        n = row["n"] or 0
        n_wins = row["n_wins"] or 0
        n_losses = row["n_losses"] or 0
        wr = n_wins / max(n, 1)

        # Paliers DD (cohérent avec DrawdownProtector 5 paliers)
        if cum >= 0:
            palier = "normal"
            mult = 1.0
        elif cum >= -100:
            palier = "watch"
            mult = 1.0
        elif cum >= -200:
            palier = "reduce_25"
            mult = 0.75
        elif cum >= -300:
            palier = "reduce_50"
            mult = 0.5
        elif cum >= -500:
            palier = "halt_24h"
            mult = 0.0
        else:
            palier = "halt_forever"
            mult = 0.0

        return {
            "ok": True,
            "lookback_days": days,
            "cum_pips": round(cum, 1),
            "n_trades": n,
            "n_wins": n_wins,
            "n_losses": n_losses,
            "wr": round(wr, 4),
            "palier": palier,
            "position_multiplier": mult,
            "recommendation": (
                "Position size normale"
                if palier == "normal"
                else f"DD détecté ({cum:.1f} pips), position × {mult}"
            ),
        }
    finally:
        conn.close()


def handle_get_correlation_matrix(args: dict) -> dict:
    """Matrice de corrélation des rendements entre paires (rolling window).

    Args : days (int, default 30), pairs (list[str], default DEFAULT_PAIRS).
    Returns : {matrix: {pair_a: {pair_b: corr}}, lookback_days}.
    """
    days = max(7, min(int(args.get("days", 30)), 90))
    pairs = args.get("pairs") or DEFAULT_PAIRS
    conn = _connect_ro()
    try:
        cutoff_iso = (
            __import__("datetime").datetime.fromtimestamp(
                time.time() - days * 86400, tz=__import__("datetime").timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")
        )
        # Récupère tous les pnl_pips par (symbol, timestamp_bucket_hour)
        rows = conn.execute(
            """
            SELECT symbol,
                   substr(timestamp, 1, 13) AS bucket_h,
                   SUM(resolution_pips) AS pnl_h
            FROM decisions
            WHERE is_win IS NOT NULL AND timestamp >= ?
            GROUP BY symbol, bucket_h
            ORDER BY bucket_h
            """,
            (cutoff_iso,),
        ).fetchall()
        # Pivot en dict {pair: [pnl_h aligned on bucket_h]}
        bucket_set = sorted({r["bucket_h"] for r in rows})
        series: dict[str, dict[str, float]] = {}
        for r in rows:
            series.setdefault(r["symbol"], {})[r["bucket_h"]] = r["pnl_h"]
        # Calcul corrélation pairwise (Pearson)
        matrix: dict[str, dict[str, float]] = {}
        for a in pairs:
            matrix[a] = {}
            for b in pairs:
                if a == b:
                    matrix[a][b] = 1.0
                    continue
                # Aligner sur buckets communs
                common = [h for h in bucket_set if h in series.get(a, {}) and h in series.get(b, {})]
                if len(common) < 5:
                    matrix[a][b] = None
                    continue
                va = [series[a][h] for h in common]
                vb = [series[b][h] for h in common]
                ma = sum(va) / len(va)
                mb = sum(vb) / len(vb)
                num = sum((va[i] - ma) * (vb[i] - mb) for i in range(len(common)))
                den_a = (sum((x - ma) ** 2 for x in va)) ** 0.5
                den_b = (sum((x - mb) ** 2 for x in vb)) ** 0.5
                if den_a == 0 or den_b == 0:
                    matrix[a][b] = None
                else:
                    matrix[a][b] = round(num / (den_a * den_b), 3)
        # Calcul diversification moyenne (off-diag)
        off_diag = [
            matrix[a][b]
            for a in pairs for b in pairs
            if a != b and matrix[a][b] is not None
        ]
        avg_corr = round(sum(off_diag) / len(off_diag), 3) if off_diag else None
        return {
            "ok": True,
            "lookback_days": days,
            "pairs": pairs,
            "matrix": matrix,
            "avg_off_diag_correlation": avg_corr,
            "interpretation": (
                "Haute diversification (avg corr < 0.3)"
                if avg_corr is not None and avg_corr < 0.3
                else "Diversification moyenne (0.3-0.6)"
                if avg_corr is not None and avg_corr < 0.6
                else "Faible diversification (> 0.6) — risque concentration"
                if avg_corr is not None
                else "Pas assez de data"
            ),
        }
    finally:
        conn.close()


def handle_get_risk_parity_weights(args: dict) -> dict:
    """Budgets risk-parity par paire (compute_risk_parity_budgets).

    Args : capital (float, default 10000), target_vol (float, default 0.15).
    Returns : {pairs: [{symbol, vol_annualized, sharpe, risk_weight, position_size}], capital, target_vol}.
    """
    capital = float(args.get("capital", 10000.0))
    target_vol = float(args.get("target_vol", 0.15))
    sys.path.insert(0, str(ROOT_DIR))
    from core.v9.v9_risk_parity import compute_risk_parity_budgets, HARD_BLACKLIST
    budgets = compute_risk_parity_budgets(
        capital=capital, target_vol=target_vol, db_path=DB_PATH,
    )
    pairs_data = [
        {
            "symbol": b.symbol,
            "vol_annualized": round(b.vol_annualized, 2),
            "sharpe": round(b.sharpe, 3),
            "risk_weight": round(b.risk_weight, 4),
            "position_size": round(b.position_size, 2),
        }
        for b in budgets
    ]
    return {
        "ok": True,
        "capital": capital,
        "target_vol": target_vol,
        "hard_blacklist": sorted(HARD_BLACKLIST),
        "n_pairs": len(pairs_data),
        "pairs": pairs_data,
        "sum_risk_weight": round(sum(p["risk_weight"] for p in pairs_data), 4),
        "sum_position_size": round(sum(p["position_size"] for p in pairs_data), 2),
    }


def handle_simulate_dd_step(args: dict) -> dict:
    """Dry-run : simule l'impact d'un step DD hypothétique.

    Args : scenario_pips (float, default -200), lookback_days (int, default 30).
    Returns : {current_cum_pips, hypothetical_cum_pips, palier_before, palier_after, ...}.
    """
    scenario = float(args.get("scenario_pips", -200))
    days = max(1, min(int(args.get("lookback_days", 30)), 90))
    current = handle_get_current_dd_state({"lookback_days": days})
    if not current["ok"]:
        return current
    cum = current["cum_pips"]
    palier_before = current["palier"]
    mult_before = current["position_multiplier"]
    hyp_cum = cum + scenario

    def palier_for(c: float) -> tuple[str, float]:
        if c >= 0:
            return ("normal", 1.0)
        if c >= -100:
            return ("watch", 1.0)
        if c >= -200:
            return ("reduce_25", 0.75)
        if c >= -300:
            return ("reduce_50", 0.5)
        if c >= -500:
            return ("halt_24h", 0.0)
        return ("halt_forever", 0.0)

    palier_after, mult_after = palier_for(hyp_cum)
    return {
        "ok": True,
        "scenario_pips": scenario,
        "lookback_days": days,
        "current_cum_pips": cum,
        "hypothetical_cum_pips": round(hyp_cum, 1),
        "palier_before": palier_before,
        "mult_before": mult_before,
        "palier_after": palier_after,
        "mult_after": mult_after,
        "would_trigger_halt": palier_before != palier_after and "halt" in palier_after,
    }


HANDLERS = {
    "risk_get_current_dd_state": handle_get_current_dd_state,
    "risk_get_correlation_matrix": handle_get_correlation_matrix,
    "risk_get_risk_parity_weights": handle_get_risk_parity_weights,
    "risk_simulate_dd_step": handle_simulate_dd_step,
}


def main() -> None:
    """MCP stdio loop."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(json.dumps({"error": f"invalid json: {e}"}))
            continue
        method = req.get("method", "")
        if method == "tools/list":
            print(json.dumps({
                "tools": [
                    {"name": "risk_get_current_dd_state", "args": ["lookback_days"]},
                    {"name": "risk_get_correlation_matrix", "args": ["days", "pairs"]},
                    {"name": "risk_get_risk_parity_weights", "args": ["capital", "target_vol"]},
                    {"name": "risk_simulate_dd_step", "args": ["scenario_pips", "lookback_days"]},
                ]
            }))
        elif method.startswith("tools/call/"):
            name = method[len("tools/call/"):]
            args = req.get("args", {})
            handler = HANDLERS.get(name)
            if handler:
                print(json.dumps(handler(args), ensure_ascii=False, default=str))
            else:
                print(json.dumps({"error": f"unknown tool: {name}"}))


if __name__ == "__main__":
    main()
