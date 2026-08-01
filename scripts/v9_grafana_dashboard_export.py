"""v9_grafana_dashboard_export.py — Phase 85 motion CEO 48H (post-Plan C).

Exporte un dashboard Grafana JSON pour visualiser les KPIs V9 :
- P&L cumule
- Win rate
- Drawdown
- Sharpe
- Trades par jour
- Leviers declenches

Auteur : Hermes (Phase 85 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.grafana_export")


def _panel(title: str, raw_sql: str, panel_type: str = "timeseries",
            unit: str = "short", grid_pos: dict[str, int] | None = None) -> dict[str, Any]:
    """Helper pour creer un panel Grafana."""
    return {
        "title": title,
        "type": panel_type,
        "datasource": {"type": "sqlite", "uid": "v9_db"},
        "gridPos": grid_pos or {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [{
            "rawSql": raw_sql,
            "refId": "A",
        }],
        "fieldConfig": {
            "defaults": {"unit": unit},
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
    }


def generate_grafana_dashboard() -> dict[str, Any]:
    """Genere le dashboard Grafana JSON."""
    panels = [
        _panel(
            "P&L Cumul (pips)",
            "SELECT timestamp, SUM(pips_simulated) OVER (ORDER BY timestamp) "
            "as pnl_cumul FROM paper_trades ORDER BY timestamp",
            unit="short",
            grid_pos={"h": 8, "w": 24, "x": 0, "y": 0},
        ),
        _panel(
            "WR rolling (30 trades)",
            "SELECT timestamp, "
            "AVG(CASE WHEN is_win=1 THEN 1.0 ELSE 0.0 END) "
            "OVER (ORDER BY timestamp ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) "
            "as wr_rolling FROM paper_trades",
            unit="percentunit",
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 8},
        ),
        _panel(
            "Drawdown (max cumul)",
            "SELECT timestamp, "
            "MAX(cumul_pnl) OVER (ORDER BY timestamp) - cumul_pnl as dd "
            "FROM (SELECT timestamp, "
            "SUM(pips_simulated) OVER (ORDER BY timestamp) as cumul_pnl "
            "FROM paper_trades)",
            unit="short",
            grid_pos={"h": 8, "w": 12, "x": 12, "y": 8},
        ),
        _panel(
            "Sharpe Ratio (rolling 50)",
            "SELECT timestamp, "
            "AVG(pips_simulated) OVER (ORDER BY timestamp ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) / "
            "(0.001 + SQRT(VARIANCE(pips_simulated) OVER (ORDER BY timestamp ROWS BETWEEN 49 PRECEDING AND CURRENT ROW))) "
            "as sharpe_50 FROM paper_trades",
            unit="short",
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 16},
        ),
        _panel(
            "Trades / jour",
            "SELECT DATE(timestamp) as day, COUNT(*) as n_trades "
            "FROM paper_trades GROUP BY day ORDER BY day",
            unit="short",
            grid_pos={"h": 8, "w": 12, "x": 12, "y": 16},
        ),
    ]
    return {
        "title": "V9 Edge Fund Dashboard (Phase 85)",
        "uid": "v9_edge_fund",
        "schemaVersion": 38,
        "version": 1,
        "panels": panels,
        "time": {"from": "now-30d", "to": "now"},
        "refresh": "60s",
    }


def export_dashboard(output_path: Path) -> bool:
    """Exporte le dashboard dans un fichier JSON."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dash = generate_grafana_dashboard()
        output_path.write_text(json.dumps(dash, indent=2))
        return True
    except Exception as exc:
        log.warning("export_dashboard failed: %s", exc)
        return False


def main(argv=None) -> int:
    """Exporte vers ./docs/v9_grafana.json par defaut."""
    import argparse
    parser = argparse.ArgumentParser(description="V9 Grafana dashboard exporter")
    parser.add_argument("--output", default="./docs/v9_grafana.json")
    args = parser.parse_args(argv)
    print("=" * 70)
    print("V9 GRAFANA DASHBOARD EXPORT (Phase 85)")
    print("=" * 70)
    out = Path(args.output)
    ok = export_dashboard(out)
    print(f"Output : {out}")
    print(f"Generated : {ok}")
    if ok:
        print(f"Size : {out.stat().st_size} bytes")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())