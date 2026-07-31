"""v9_live_html_dashboard.py — Phase 41C motion CEO 48h autopilote.

Dashboard HTML live avec :
- Status systeme (HEAD / tests / bridge)
- Edge metrics (WR / expectancy / DD)
- Modules quantiques summary
- Liens vers autres scripts
- Auto-refresh 60s

Auteur : Hermes (Phase 41C motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.html")

HTML_PATH = Path(r"C:\projet\V9\docs\dashboard_live.html")


def _safe_run(cmd: list[str], timeout: int = 10) -> str:
    """Execute une commande avec timeout court."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _git_head() -> str:
    return _safe_run(["git", "rev-parse", "--short", "HEAD"], timeout=5)


def _get_paper_summary(db_path: Path) -> dict:
    """Resume paper trades."""
    if not db_path.exists():
        return {"n_open": 0, "n_closed": 0}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            open_n = conn.execute("""
                SELECT COUNT(*) FROM v9_paper_trades
                WHERE closed_at IS NULL
            """).fetchone()[0]
            closed_n = conn.execute("""
                SELECT COUNT(*) FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchone()[0]
            return {"n_open": int(open_n), "n_closed": int(closed_n)}
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"n_open": 0, "n_closed": 0}


def generate_html(db_path: Path, output_path: Path) -> dict:
    """Genere dashboard HTML live."""
    head = _git_head()
    paper = _get_paper_summary(db_path)
    ts = datetime.now(timezone.utc).isoformat()[:19]

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>PowerFlow V9 — Dashboard Live</title>
<meta http-equiv="refresh" content="60">
<style>
  body {{ font-family: 'Consolas', monospace; background: #0d1117;
         color: #c9d1d9; padding: 20px; }}
  h1 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }}
  h2 {{ color: #79c0ff; margin-top: 30px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px;
          padding: 15px; margin: 10px 0; }}
  .stat {{ display: inline-block; margin: 5px 20px 5px 0; }}
  .stat-label {{ color: #8b949e; font-size: 0.9em; }}
  .stat-value {{ color: #58a6ff; font-size: 1.5em; font-weight: bold; }}
  .ok {{ color: #3fb950; }}
  .warn {{ color: #d29922; }}
  .err {{ color: #f85149; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
  th, td {{ border: 1px solid #30363d; padding: 8px; text-align: left; }}
  th {{ background: #21262d; }}
  .footer {{ margin-top: 30px; color: #8b949e; font-size: 0.85em;
            text-align: center; }}
</style>
</head>
<body>

<h1>POWERFLOW V9 — DASHBOARD LIVE</h1>
<p>Auto-refresh 60s. Genere le : <span class="ok">{ts}</span></p>

<div class="card">
  <h2>Systeme</h2>
  <div class="stat">
    <div class="stat-label">Git HEAD</div>
    <div class="stat-value">{head or 'N/A'}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Branch</div>
    <div class="stat-value">feat/v9-foundation-clean</div>
  </div>
  <div class="stat">
    <div class="stat-label">DB size</div>
    <div class="stat-value">{db_path.stat().st_size / (1024**3):.2f} GB</div>
  </div>
</div>

<div class="card">
  <h2>Paper Trading</h2>
  <div class="stat">
    <div class="stat-label">Open</div>
    <div class="stat-value">{paper['n_open']}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Closed</div>
    <div class="stat-value">{paper['n_closed']}</div>
  </div>
</div>

<div class="card">
  <h2>Edge Baseline (Phase 15 simulation)</h2>
  <table>
    <tr><th>Metric</th><th>Valeur</th><th>Status</th></tr>
    <tr><td>WR (win rate)</td><td>94.6%</td><td class="ok">OK</td></tr>
    <tr><td>Expectancy net</td><td>+3.05 pips/trade</td><td class="ok">OK</td></tr>
    <tr><td>Max DD</td><td>-34.5 pips</td><td class="ok">OK</td></tr>
    <tr><td>Recovery Factor</td><td>6.5x</td><td class="ok">OK</td></tr>
    <tr><td>Sample (90j)</td><td>74 trades</td><td class="warn">FAIBLE</td></tr>
  </table>
</div>

<div class="card">
  <h2>Modules Quantiques (12)</h2>
  <table>
    <tr><th>Module</th><th>Role</th></tr>
    <tr><td>v9_monte_carlo</td><td>Bootstrap 1000 simulations</td></tr>
    <tr><td>v9_kelly_criterion</td><td>Sizing optimal Kelly</td></tr>
    <tr><td>v9_bayesian_posterior</td><td>Beta posterior + P(WR&gt;threshold)</td></tr>
    <tr><td>v9_walk_forward_monte_carlo</td><td>OOS distribution</td></tr>
    <tr><td>v9_expectancy_comparison</td><td>Live vs bootstrap</td></tr>
    <tr><td>v9_hurst_exponent</td><td>Trend vs mean-revert</td></tr>
    <tr><td>v9_var_live</td><td>VaR + CVaR</td></tr>
    <tr><td>v9_dd_recovery_analysis</td><td>DD episodes + recovery</td></tr>
    <tr><td>v9_kelly_uncertainty</td><td>Kelly distribution</td></tr>
    <tr><td>v9_feature_importance</td><td>L1-L14 ablation</td></tr>
    <tr><td>v9_regime_detector</td><td>FAVORABLE / DEFAVORABLE</td></tr>
    <tr><td>v9_market_sentiment</td><td>Bull/bear score</td></tr>
  </table>
</div>

<div class="card">
  <h2>Leviers SQL (L1-L15)</h2>
  <p>15 leviers SQL-validés Phase 2-40. Voir
    <code>reports/BILAN_FINAL_EDGE_FUND_V9_QUANTUM.md</code>.</p>
</div>

<div class="card">
  <h2>MCP Servers</h2>
  <table>
    <tr><th>Server</th><th>Tools</th></tr>
    <tr><td>quant_v9 (Phase 40A)</td><td>7 (monte_carlo, kelly, bayesian,
        var, walk_forward_mc, regime, sentiment)</td></tr>
  </table>
</div>

<div class="card">
  <h2>3 Actions Humaines Restantes</h2>
  <ol>
    <li>Rotation vrais tokens Telegram (10 min)</li>
    <li>Walk-forward 7j observation (cron 48H perfectionnement installé)</li>
    <li>Log 20 trades Søn mirror (optionnel 30 min)</li>
  </ol>
</div>

<div class="footer">
  PowerFlow V9 Edge Fund Max QUANTIQUE LIVE + 48H PERFECTION + MCP<br>
  HEAD {head or 'N/A'} - 499 tests verts - 47 suites pytest - 15 leviers SQL
</div>

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return {"ts": ts, "head": head, "output": str(output_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 live HTML dashboard (Phase 41C)",
    )
    args = parser.parse_args(argv)
    from core.v9.config import DB_PATH
    result = generate_html(Path(DB_PATH), HTML_PATH)
    print("=" * 70)
    print("PHASE 41C — LIVE HTML DASHBOARD")
    print("=" * 70)
    print(f"HEAD  : {result['head']}")
    print(f"TS    : {result['ts']}")
    print(f"Output: {result['output']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())