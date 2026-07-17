"""v9_dashboard_api.py — API dashboard temps réel PowerFlow V9.

2026-07-17 motion CEO « orchestre et crée tout ce qu'il faut ».

Dashboard live pour supervision hedge fund. Expose les métriques
métier (paper trades, WR, pips, DD, risk parity) en JSON pour
consommation par un front-end web.

Routes :
  GET /                       → index (informations)
  GET /health                 → health check
  GET /api/metrics            → métriques globales (WR, PF, Sharpe)
  GET /api/strategies         → catalogue des stratégies
  GET /api/drawdown           → état drawdown protector
  GET /api/risk-parity        → allocation risk-parity multi-paires
  GET /api/top                → top N stratégies par métrique
  GET /api/recent-trades      → N derniers paper_trades clôturés
  GET /api/kill-switches      → état des kill switches
  GET /api/crons              → état des crons (Windows scheduled tasks)

Doctrine : R6 défensif, R18 pas de LLM. Code pur Python.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

DASHBOARD_VERSION = "1.0"
ROOT = Path(r"C:\projet\V9")
DB_PATH = ROOT / "data" / "v9_forces.db"


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class MetricsResponse(BaseModel):
    version: str
    timestamp: str
    totals: dict
    by_direction: dict
    best_session: str | None
    worst_session: str | None
    best_principle: str | None
    worst_principle: str | None


app = FastAPI(
    title="PowerFlow V9 Dashboard API",
    description="API temps réel pour supervision hedge fund V9",
    version=DASHBOARD_VERSION,
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Page d'accueil HTML du dashboard."""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>PowerFlow V9 — Hedge Fund Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                margin: 0; padding: 20px; background: #0a0e27; color: #e0e0e0; }}
        h1 {{ color: #00d9ff; margin: 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 16px; margin-top: 24px; }}
        .card {{ background: #131836; padding: 20px; border-radius: 8px;
                 border-left: 4px solid #00d9ff; }}
        .card h3 {{ margin: 0 0 12px 0; color: #00d9ff; font-size: 14px;
                     text-transform: uppercase; letter-spacing: 1px; }}
        .metric {{ font-size: 32px; font-weight: bold; color: #ffffff; }}
        .metric.positive {{ color: #00ff88; }}
        .metric.negative {{ color: #ff4444; }}
        .label {{ color: #888; font-size: 12px; margin-top: 4px; }}
        a {{ color: #00d9ff; text-decoration: none; }}
        code {{ background: #1e2347; padding: 2px 6px; border-radius: 3px;
                font-family: "Consolas", monospace; }}
    </style>
</head>
<body>
    <h1>🎯 PowerFlow V9 — Hedge Fund Dashboard</h1>
    <p style="color: #888;">
        Version <code>{DASHBOARD_VERSION}</code> ·
        Généré <code id="ts">{datetime.now(timezone.utc).isoformat()}</code>
    </p>
    <div class="grid">
        <div class="card">
            <h3>Métriques</h3>
            <p><a href="/api/metrics">📊 /api/metrics</a></p>
            <p><a href="/api/strategies">🎯 /api/strategies</a></p>
            <p><a href="/api/top">🏆 /api/top</a></p>
        </div>
        <div class="card">
            <h3>Risk Management</h3>
            <p><a href="/api/drawdown">🛡️ /api/drawdown</a></p>
            <p><a href="/api/risk-parity">⚖️ /api/risk-parity</a></p>
        </div>
        <div class="card">
            <h3>Infrastructure</h3>
            <p><a href="/api/kill-switches">🔌 /api/kill-switches</a></p>
            <p><a href="/api/crons">⏰ /api/crons</a></p>
            <p><a href="/api/recent-trades">📈 /api/recent-trades</a></p>
            <p><a href="/health">❤️ /health</a></p>
        </div>
    </div>
    <script>
        // Auto-refresh timestamp
        setInterval(() => {{
            document.getElementById('ts').textContent = new Date().toISOString();
        }}, 1000);
    </script>
</body>
</html>
"""


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=DASHBOARD_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _read_meta_from_db() -> dict[str, Any]:
    """Lit les métriques globales depuis la DB."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) AS losses,
                   COALESCE(SUM(pips_simulated), 0) AS total_pips,
                   COALESCE(AVG(pips_simulated), 0) AS avg_pips,
                   SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_count
            FROM paper_trades
            """
        ).fetchone()
    finally:
        conn.close()

    n, wins, losses, total_pips, avg_pips, open_count = (
        row[0] or 0, row[1] or 0, row[2] or 0,
        float(row[3] or 0), float(row[4] or 0), row[5] or 0,
    )
    wr = round(100 * wins / max(wins + losses, 1), 2)

    # Profit factor
    conn = sqlite3.connect(str(DB_PATH))
    try:
        win_sum = float(conn.execute(
            "SELECT COALESCE(SUM(pips_simulated), 0) FROM paper_trades WHERE is_win=1"
        ).fetchone()[0] or 0)
        loss_sum = abs(float(conn.execute(
            "SELECT COALESCE(SUM(pips_simulated), 0) FROM paper_trades WHERE is_win=0"
        ).fetchone()[0] or 0))
    finally:
        conn.close()
    pf = round(win_sum / loss_sum, 2) if loss_sum else 0.0

    # Sharpe-like
    if n > 1:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            stddev = float(conn.execute(
                "SELECT COALESCE(SQRT(AVG(pips_simulated*pips_simulated) - AVG(pips_simulated)*AVG(pips_simulated)), 0) "
                "FROM paper_trades WHERE closed_at IS NOT NULL"
            ).fetchone()[0] or 0)
        finally:
            conn.close()
        sharpe_like = round(float(avg_pips) / stddev, 3) if stddev else 0
    else:
        sharpe_like = 0

    # Max drawdown (walking forward)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT pips_simulated FROM paper_trades WHERE closed_at IS NOT NULL "
            "ORDER BY closed_at"
        ).fetchall()
    finally:
        conn.close()
    cum_pips = peak = max_dd = 0.0
    for r in rows:
        cum_pips += r[0] or 0
        if cum_pips > peak:
            peak = cum_pips
        dd = peak - cum_pips
        if dd > max_dd:
            max_dd = dd

    return {
        "n_trades_total": n,
        "n_trades_closed": wins + losses,
        "n_trades_open": open_count,
        "wins": wins,
        "losses": losses,
        "wr_pct": wr,
        "total_pips": round(total_pips, 1),
        "avg_pips": round(avg_pips, 2),
        "max_drawdown_pips": round(max_dd, 1),
        "profit_factor": pf,
        "sharpe_like": sharpe_like,
        "recovery_factor": round(total_pips / max(max_dd, 1), 2),
    }


@app.get("/api/metrics")
def api_metrics() -> dict[str, Any]:
    """Métriques globales du paper-trade."""
    from core.v9.v9_strategy_pole import compute_meta_metrics
    try:
        return compute_meta_metrics()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/strategies")
def api_strategies(min_n: int = 20) -> dict[str, Any]:
    """Catalogue des stratégies (segments principle × session × regime)."""
    from core.v9.v9_strategy_pole import StrategyCatalogue
    cat = StrategyCatalogue()
    n = cat.recompute(min_n=min_n)
    items = sorted(cat._cache.values(), key=lambda m: m.avg_pips, reverse=True)
    return {
        "count": n,
        "min_n": min_n,
        "strategies": [m.to_dict() for m in items],
    }


@app.get("/api/top")
def api_top(n: int = 5, by: str = "avg_pips") -> dict[str, Any]:
    """Top N stratégies par métrique."""
    from core.v9.v9_strategy_pole import StrategyCatalogue
    cat = StrategyCatalogue()
    cat.recompute(min_n=20)
    top = cat.top(n=n, by=by)
    return {"by": by, "count": len(top), "strategies": [m.to_dict() for m in top]}


@app.get("/api/drawdown")
def api_drawdown(capital: float = 10000.0) -> dict[str, Any]:
    """État du drawdown protector."""
    from core.v9.v9_drawdown_protector import DrawdownProtector
    prot = DrawdownProtector(initial_capital=capital)
    return prot.get_decision_summary()


@app.get("/api/risk-parity")
def api_risk_parity(
    capital: float = 10000.0,
    target_vol: float = 0.15,
) -> dict[str, Any]:
    """Allocation risk-parity multi-paires."""
    from core.v9.v9_risk_parity import compute_risk_parity_budgets, HARD_BLACKLIST
    budgets = compute_risk_parity_budgets(
        capital=capital, target_vol=target_vol,
    )
    return {
        "version": "1.0",
        "capital": capital,
        "target_vol_annualized": target_vol,
        "blacklist": list(HARD_BLACKLIST),
        "budgets": [b.to_dict() for b in budgets],
    }


@app.get("/api/recent-trades")
def api_recent_trades(limit: int = 20) -> dict[str, Any]:
    """N derniers paper_trades clôturés."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            """
            SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.confiance,
                   pt.opened_at, pt.closed_at, pt.pips_simulated, pt.is_win,
                   d.symbol, d.timeframe, d.regime_type
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL
            ORDER BY pt.closed_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "limit": limit,
        "count": len(rows),
        "trades": [
            {
                "trade_id": r[0],
                "symbol": r[8],
                "timeframe": r[9],
                "direction": r[2],
                "confiance": r[3],
                "opened_at": r[4],
                "closed_at": r[5],
                "pips": round(r[6] or 0, 2),
                "is_win": bool(r[7]),
                "regime": r[10],
            }
            for r in rows
        ],
    }


@app.get("/api/kill-switches")
def api_kill_switches() -> dict[str, Any]:
    """État des kill switches V9."""
    env_path = ROOT / "config" / "v9_kill_switches.env"
    if not env_path.exists():
        return {"error": "config/v9_kill_switches.env not found"}
    switches: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        switches[key.strip()] = val.strip()
    return {
        "version": DASHBOARD_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "switches": switches,
    }


@app.get("/api/crons")
def api_crons() -> dict[str, Any]:
    """État des crons Windows (V9_* scheduled tasks)."""
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/fo", "LIST"],
            capture_output=True, timeout=10,
        )
    except Exception as exc:
        return {"error": str(exc)}

    # schtasks output est en cp1252 sur Windows FR
    try:
        text = r.stdout.decode("cp1252", errors="replace")
    except Exception:
        text = r.stdout.decode("utf-8", errors="replace")

    crons = []
    current_task: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            # Filtre large : on cherche V9_ dans n'importe quelle clé
            for v in current_task.values():
                if "V9_" in v:
                    crons.append(current_task)
                    break
            current_task = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            current_task[key.strip()] = val.strip()

    # Filtre large final
    v9_crons = []
    for c in crons:
        name = next((v for v in c.values() if "V9_" in v), "?")
        v9_crons.append({
            "name": name,
            "raw": c,
        })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(v9_crons),
        "crons": v9_crons,
    }


@app.get("/api/hedge-fund-summary")
def api_hedge_fund_summary(
    capital: float = 10000.0,
    target_vol: float = 0.15,
) -> dict[str, Any]:
    """Aggregate DD + risk parity + meta metrics."""
    from core.v9.v9_drawdown_protector import DrawdownProtector
    from core.v9.v9_risk_parity import compute_risk_parity_budgets
    from core.v9.v9_strategy_pole import compute_meta_metrics

    return {
        "drawdown_protection": DrawdownProtector(
            initial_capital=capital,
        ).get_decision_summary(),
        "risk_parity": {
            "budgets": [
                b.to_dict() for b in compute_risk_parity_budgets(
                    capital=capital, target_vol=target_vol,
                )
            ],
        },
        "meta_metrics": compute_meta_metrics(),
    }


def main() -> int:
    """Lance le serveur dashboard."""
    import argparse
    parser = argparse.ArgumentParser(description="V9 Dashboard API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "core.v9.v9_dashboard_api:app",
        host=args.host, port=args.port, reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())