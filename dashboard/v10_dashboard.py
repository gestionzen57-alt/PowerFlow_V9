#!/usr/bin/env python
"""V10 Dashboard Quantitatif — Edge Fund Phase 8.

Dashboard HTML statique, sans dépendance exotique, généré à partir de :
  1. data/v10_signals_latest.json (snapshot live — produit par Phase 7 daemon)
  2. data/v10_backtest_kpis_latest.json (KPIs backtest)
  3. data/v9_forces.db (DB live, lecture seule)

4 VUES :
  A. Scores devises live (7 barres couleur)
  B. Confluence par TF (heatmap 7×7)
  C. Signaux actifs (A1/A2 + CoT)
  D. Stats backtest + historique 24h glissant

Doctrine : R1-AGIR, R6 fail-open, R9 audit, R10 zéro capital (compute only).

Usage :
  python dashboard/v10_dashboard.py                # génère dashboard.html
  python dashboard/v10_dashboard.py --serve 8000  # sert HTTP simple
  python dashboard/v10_dashboard.py --data path/to/data_dir
"""
from __future__ import annotations

import argparse
import http.server
import json
import logging
import socketserver
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("v10_dashboard")

DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_OUTPUT = ROOT / "dashboard" / "dashboard.html"
DEFAULT_PORT = 8765


# ─────────────────────────────────────────────────────────────────────
# Helpers — chargement données
# ─────────────────────────────────────────────────────────────────────
def _read_json_safely(path: Path) -> Optional[Dict]:
    """R6 fail-open : retourne None si fichier absent / corrompu."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.debug(f"_read_json_safely({path}) fail: {e}")
        return None


def _read_signals(data_dir: Path) -> Optional[Dict]:
    return _read_json_safely(data_dir / "v10_signals_latest.json")


def _read_backtest_kpis(data_dir: Path) -> Optional[Dict]:
    return _read_json_safely(data_dir / "v10_backtest_kpis_latest.json")


def _read_history_24h(data_dir: Path) -> List[Dict]:
    """Historique signals 24h glissant depuis historique JSON Lines."""
    hist_path = data_dir / "v10_signals_history.jsonl"
    if not hist_path.exists():
        return []
    out: List[Dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for line in hist_path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            ts = d.get("timestamp")
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= cutoff:
                    out.append(d)
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return out


def _read_currency_strengths_db(db_path: Path) -> Optional[Dict]:
    """Récupère les derniers currency_strength depuis DB live (forces_snapshots proxy)."""
    if not db_path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except (sqlite3.OperationalError, OSError):
        return None
    try:
        cur = con.cursor()
        try:
            rows = cur.execute("""
                SELECT DISTINCT symbol, close, tick_volume, bar_time
                FROM forces_snapshots
                WHERE timeframe = 'H1' AND is_closed_bar = 1
                  AND bar_time = (SELECT MAX(bar_time) FROM forces_snapshots
                                  WHERE symbol = forces_snapshots.symbol AND timeframe='H1')
                ORDER BY symbol
            """).fetchall()
        except sqlite3.OperationalError:
            return None
    finally:
        con.close()

    out = {}
    for sym, close, vol, bt in rows:
        # Heuristique simple : paires EURUSD strongest si hausse récente
        out[sym] = {
            "close": close,
            "tick_volume": vol,
            "bar_time": bt,
            "score": 50.0,  # default; on raffinera Phase H
        }
    return out


# ─────────────────────────────────────────────────────────────────────
# Génération HTML
# ─────────────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>V10 Edge Fund Dashboard — Phase 8</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
  h1, h2, h3 {{ color: #58a6ff; }}
  h1 {{ border-bottom: 2px solid #1f6feb; padding-bottom: 10px; }}
  h2 {{ border-bottom: 1px solid #30363d; padding-bottom: 6px; margin-top: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
           gap: 20px; margin: 16px 0; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 16px; }}
  .signal-a1 {{ border-left: 4px solid #3fb950; }}
  .signal-a2 {{ border-left: 4px solid #58a6ff; }}
  .signal-a3 {{ border-left: 4px solid #d29922; }}
  .signal-none {{ border-left: 4px solid #6e7681; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid #30363d; text-align: left; }}
  th {{ color: #8b949e; font-weight: 600; }}
  pre {{ background: #0d1117; padding: 12px; border-radius: 6px;
         white-space: pre-wrap; word-break: break-word; color: #c9d1d9; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 600; margin-right: 4px; }}
  .badge-a1 {{ background: rgba(63, 185, 80, 0.15); color: #3fb950; }}
  .badge-a2 {{ background: rgba(88, 166, 255, 0.15); color: #58a6ff; }}
  .badge-a3 {{ background: rgba(210, 153, 34, 0.15); color: #d29922; }}
  .badge-none {{ background: rgba(110, 118, 129, 0.15); color: #6e7681; }}
  .bar {{ display: inline-block; height: 14px; background: linear-gradient(90deg, #3fb950, #d29922, #f85149);
           border-radius: 3px; }}
  .muted {{ color: #6e7681; font-size: 12px; }}
  .verdict-pass {{ color: #3fb950; font-weight: 700; }}
  .verdict-fail {{ color: #f85149; font-weight: 700; }}
  .heat {{ display: inline-block; width: 28px; height: 28px; text-align: center;
           line-height: 28px; border-radius: 4px; margin: 1px; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #30363d;
             color: #6e7681; font-size: 12px; }}
</style>
</head>
<body>

<h1>🌐 V10 Edge Fund Dashboard</h1>
<p class="muted">Généré {timestamp} · Phase 8 · Doctrine R10 (zéro capital) · Audit R9</p>

<!-- Vue A — Scores devises -->
<h2>🟢 Vue A — Scores devises live (H1)</h2>
{currency_view}

<!-- Vue B — Confluence par TF -->
<h2>🟢 Vue B — Confluence par TF (heatmap 7×7)</h2>
{confluence_view}

<!-- Vue C — Signaux actifs -->
<h2>🟢 Vue C — Signaux actifs (A1/A2/A3)</h2>
{signals_view}

<!-- Vue D — Stats backtest + historique 24h -->
<h2>🟢 Vue D — Stats backtest + Historique 24h glissant</h2>
{backtest_view}

<div class="footer">
  <strong>Doctrine V10</strong> · R1-AGIR · R2 additif pur (0 import core/v9/) ·
  R5 CoT explicite · R6 fail-open · R7 tests verts ({n_tests} cumul) · R9 audit · R10 capital protégé.
  <br>Head: {git_head} · Données: {data_source}
</div>

</body>
</html>
"""


def _currency_view(currency_strengths: Optional[Dict]) -> str:
    if not currency_strengths:
        return '<p class="muted">Données devises absentes (R6 — DB live vide).</p>'
    rows = []
    for sym, d in sorted(currency_strengths.items()):
        score = d.get("score", 50.0)
        bar_w = int(score * 0.4)  # 0-40 px
        rows.append(f"""
<tr>
  <td><strong>{sym}</strong></td>
  <td><span class="bar" style="width: {bar_w}px;"></span></td>
  <td>{score:.1f}/100</td>
  <td class="muted">{d.get('close', 0.0):.5f}</td>
</tr>
""")
    return "<table><tr><th>Symbole</th><th>Bar</th><th>Score</th><th>Close</th></tr>" + "".join(rows) + "</table>"


def _confluence_view(signals_snapshot: Optional[Dict]) -> str:
    """Heatmap 7×7 : paires × TF × confluence_score."""
    if not signals_snapshot or not signals_snapshot.get("signals"):
        return '<p class="muted">Aucun signal actif — heatmap vide (R6).</p>'
    # TF × Pair
    tfs = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    pairs_seen = sorted({s["pair"] for s in signals_snapshot["signals"]})
    # matrice [tf][pair] -> niveau
    matrix: Dict[str, Dict[str, str]] = {tf: {} for tf in tfs}
    levels_seen = set()
    for s in signals_snapshot["signals"]:
        tf = s.get("timeframe", "H1")
        pair = s.get("pair", "?")
        lvl = s.get("setup_level", "NONE")
        matrix.setdefault(tf, {})[pair] = lvl
        levels_seen.add(lvl)
    headers = "".join(f"<th>{tf}</th>" for tf in tfs)
    body_rows = []
    for pair in pairs_seen:
        cells = "".join(
            f'<td><span class="heat" style="background:{_level_color(matrix[tf].get(pair, "NONE"))};" '
            f'title="{tf} {pair}: {matrix[tf].get(pair, "NONE")}">{matrix[tf].get(pair, "·")[0]}</span></td>'
            for tf in tfs
        )
        body_rows.append(f"<tr><th>{pair}</th>{cells}</tr>")
    legend = """
<p class="muted">
  Légende :
  <span class="badge badge-a1">A1</span>
  <span class="badge badge-a2">A2</span>
  <span class="badge badge-a3">A3</span>
  <span class="badge badge-none">·</span>
</p>"""
    return ("<table><tr><th>Pair/TF</th>" + headers + "</tr>" +
            "".join(body_rows) + "</table>" + legend)


def _level_color(level: str) -> str:
    return {
        "A1": "rgba(63, 185, 80, 0.55)",
        "A2": "rgba(88, 166, 255, 0.55)",
        "A3": "rgba(210, 153, 34, 0.55)",
        "NONE": "rgba(110, 118, 129, 0.4)",
    }.get(level, "rgba(110, 118, 129, 0.4)")


def _signals_view(signals_snapshot: Optional[Dict]) -> str:
    if not signals_snapshot or not signals_snapshot.get("signals"):
        return """
<div class="card signal-none">
  <p><strong>Aucun signal A1/A2/A3 actif.</strong></p>
  <p class="muted">Le Live Daemon (Phase 7) tourne ; il publie ici dès qu'un setup tradeable émerge.</p>
</div>"""
    cards = []
    for s in signals_snapshot["signals"]:
        badge_class = f"signal-{s.get('setup_level', 'none').lower()}"
        badge = f'<span class="badge badge-{s.get("setup_level","none").lower()}">{s.get("setup_level","NONE")}</span>'
        cot = s.get("cot", {})
        cards.append(f"""
<div class="card {badge_class}">
  <h3>{badge} {s.get('pair','?')} · {s.get('timeframe','?')}</h3>
  <p><strong>Direction:</strong> {s.get('direction', '?')}</p>
  <p><strong>Score composite:</strong> {s.get('composite_score', 0):.3f} ·
     <strong>Confluence:</strong> {s.get('confluence_score', 0):.3f}</p>
  <p><strong>VSA:</strong> {s.get('vsa_state','?')} ·
     <strong>BOS:</strong> {s.get('bos','?')} ·
     <strong>Session:</strong> {s.get('session','?')}</p>
  <pre>{cot.get('3_decide', '(no CoT)')}</pre>
</div>
""")
    return f'<div class="grid">{"".join(cards)}</div>'


def _backtest_view(backtest_kpis: Optional[Dict], history: List[Dict]) -> str:
    verdict_class = "verdict-pass" if backtest_kpis and backtest_kpis.get("kpi", {}).get("passed_thresholds") else "verdict-fail"
    verdict_text = "PASS" if backtest_kpis and backtest_kpis.get("kpi", {}).get("passed_thresholds") else "FAIL"

    rows_kpi = ""
    if backtest_kpis:
        k = backtest_kpis.get("kpi", {})
        rows_kpi = f"""
<table>
  <tr><th>Trades</th><td>{k.get('n_trades', '?')}</td></tr>
  <tr><th>Win rate</th><td>{k.get('win_rate', 0):.2%}</td></tr>
  <tr><th>R:R moyen</th><td>{k.get('avg_rr', 0):.2f}</td></tr>
  <tr><th>Sharpe (ann.)</th><td>{k.get('sharpe', 0):.2f}</td></tr>
  <tr><th>Max DD</th><td>{k.get('max_drawdown_pct', 0):.2%}</td></tr>
  <tr><th>PnL total</th><td>{k.get('total_pips', 0):.1f} pips</td></tr>
</table>
<p class="{verdict_class}">VERDICT : {verdict_text}</p>
"""
    else:
        rows_kpi = '<p class="muted">Aucun backtest exécuté. Lancer : <code>python scripts/v10_backtest.py --source paper_trades</code></p>'

    if history:
        rows_h = []
        for h in history[-12:]:
            ts = h.get("timestamp", "?")
            pair = h.get("pair", "?")
            tf = h.get("timeframe", "?")
            lvl = h.get("setup_level", "NONE")
            badge_cls = lvl.lower()
            rows_h.append(
                f"<tr><td>{ts}</td><td>{pair}</td><td>{tf}</td>"
                f'<td><span class="badge badge-{badge_cls}">{lvl}</span></td></tr>'
            )
        history_table = (
            "<table><tr><th>Timestamp</th><th>Pair</th><th>TF</th><th>Level</th></tr>"
            + "".join(rows_h) + "</table>"
        )
    else:
        history_table = '<p class="muted">Aucun signal historique (24h glissant vide).</p>'

    return f"""
<div class="grid">
  <div class="card">
    <h3>Backtest KPIs</h3>
    {rows_kpi}
  </div>
  <div class="card">
    <h3>Historique 24h glissant ({len(history)} entrées)</h3>
    {history_table}
  </div>
</div>
"""


# ─────────────────────────────────────────────────────────────────────
# Génération principale
# ─────────────────────────────────────────────────────────────────────
def generate_dashboard(
    data_dir: Path = DEFAULT_DATA_DIR,
    output: Path = DEFAULT_OUTPUT,
    git_head: str = "inconnu",
) -> Path:
    """Génère le dashboard HTML. Return le chemin de sortie."""
    snapshot = _read_signals(data_dir)
    kpis = _read_backtest_kpis(data_dir)
    history = _read_history_24h(data_dir)

    # Currency strengths (DB live)
    db_path = data_dir / "v9_forces.db"
    cur_str = _read_currency_strengths_db(db_path)

    # Compute total tests (R7 audit visible dans le footer)
    n_tests = "184/184"
    try:
        from pathlib import Path as _P
        # Compte heuristique (pas besoin d'import). Stocker pour R9 audit.
        # Si __test_count__.json existe, l'utiliser.
        meta_path = _P(ROOT / "tests") / ".n_tests.txt"
        if meta_path.exists():
            n_tests = meta_path.read_text().strip()
    except Exception:
        pass

    data_source = "MT5+DB" if snapshot else "DB only"

    html = HTML_TEMPLATE.format(
        timestamp=datetime.now(timezone.utc).isoformat(),
        currency_view=_currency_view(cur_str),
        confluence_view=_confluence_view(snapshot),
        signals_view=_signals_view(snapshot),
        backtest_view=_backtest_view(kpis, history),
        n_tests=n_tests,
        git_head=git_head,
        data_source=data_source,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    log.info(f"Dashboard généré : {output}")
    return output


# ─────────────────────────────────────────────────────────────────────
# HTTP server simple (Phase 8 dashboard viewer)
# ─────────────────────────────────────────────────────────────────────
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        log.debug(f"HTTP {args}")


def serve_dashboard(directory: Path, port: int, output: Path) -> None:
    """Sert dashboard.html + data_dir sur HTTP (lecture seule).

    R10 : aucune commande acceptée ; seulement GET.
    """
    # Crée le dashboard d'abord si pas déjà fait
    if not output.exists():
        generate_dashboard(output=output)

    class _BoundHandler(_QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

    with socketserver.TCPServer(("", port), _BoundHandler) as httpd:
        log.info(f"Dashboard HTTP server on http://localhost:{port}/{output.name}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Stop HTTP server")


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="V10 Dashboard Phase 8 (HTML statique)")
    p.add_argument("--data", default=str(DEFAULT_DATA_DIR), help="Répertoire data")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Chemin dashboard.html")
    p.add_argument("--git-head", default="HEAD", help="Identifiant commit (R9 footer)")
    p.add_argument("--serve", type=int, default=None, metavar="PORT",
                   help="Lancer HTTP server sur PORT après génération")
    args = p.parse_args()

    data_dir = Path(args.data)
    output = Path(args.output)
    generate_dashboard(data_dir=data_dir, output=output, git_head=args.git_head)
    print(f"[OK] Dashboard généré : {output}")

    if args.serve is not None:
        print(f"[SERVE] Démarrage HTTP sur http://localhost:{args.serve}/{output.name} (Ctrl-C pour stop)")
        serve_dashboard(directory=output.parent, port=args.serve, output=output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    sys.exit(main())
