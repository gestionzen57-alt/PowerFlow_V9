"""V10 CEO Dashboard — 1 page HTML de pilotage (Levier 5, Phase 33).

Agrège les indicateurs de décision V10 (0 dépendance externe) :
  - État du bridge MT5 (live/db_fallback/unavail, compte)
  - Fidélité du comportement des devises (Phase 32) : composite +
    extrême + verdict par paire
  - Régime de marché + leadership + coalition (Phase 32)
  - Fraîcheur du dataset v10_signals_clean (Levier 2)
  - Paper trades V9 (vérité héritée) + paper Phase 30 (120 trades)

Output : docs/dashboard_v10_ceo.html — auto-refresh 60s.

Usage : python scripts/v10_ceo_dashboard.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10 import v10_mt5_bridge  # noqa: E402
from core.v10.v10_currency_behavior import (  # noqa: E402
    classify_regime, compute_leadership, detect_coalitions,
    compute_fidelity_extreme, load_currency_series,
)

DB_PATH = Path(r"C:\projet\V9\data\v9_forces.db")
HTML_PATH = Path(r"C:\projet\V9\docs\dashboard_v10_ceo.html")
PAIRS = ("GBPUSD", "EURUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _get_bridge_status() -> dict:
    def _run():
        b = v10_mt5_bridge
        ok = b.initialize()
        state = b.get_bridge_state()
        cells_live = 0
        cells_unavail = 0
        if ok:
            for pair in ("GBPUSD", "EURUSD", "USDJPY"):
                try:
                    df = b.get_rates(pair, "M30", 1)
                    if df is not None:
                        cells_live += 1
                    else:
                        cells_unavail += 1
                except Exception:
                    cells_unavail += 1
            b.shutdown()
        return {
            "initialized": ok,
            "account_login": state.account_login,
            "account_server": state.account_server,
            "cells_live": cells_live,
            "cells_unavail": cells_unavail,
            "n_rate_calls": state.n_rate_calls,
        }
    return _safe(_run, {"initialized": False, "cells_live": 0,
                        "cells_unavail": 3, "account_login": None,
                        "account_server": None})


def _get_dataset_freshness() -> dict:
    def _run():
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        cur = con.cursor()
        cur.execute("SELECT MAX(timestamp), COUNT(*) FROM v10_signals_clean")
        max_ts, n = cur.fetchone()
        con.close()
        age_h = None
        if max_ts:
            ts = datetime.fromisoformat(str(max_ts).replace("Z", "+00:00"))
            age_h = round((datetime.now(timezone.utc) - ts).total_seconds() / 3600, 1)
        return {"max_ts": max_ts, "n_signals": n, "age_h": age_h}
    return _safe(_run, {"max_ts": None, "n_signals": 0, "age_h": None})


def _get_behavior_summary() -> dict:
    def _run():
        out = {}
        for pair in PAIRS:
            m30 = load_currency_series(str(DB_PATH), pair, "M30", days=7)
            if len(m30) < 30:
                out[pair] = {"verdict": "NO_DATA"}
                continue
            fid = compute_fidelity_extreme(m30)
            rg = classify_regime(m30)
            ld = compute_leadership(m30)
            co = detect_coalitions(m30)
            out[pair] = {
                "verdict": ("RELIABLE" if fid["extreme_reliable"] else "DEGRADED"),
                "best_currency": fid.get("best_currency"),
                "best_wr": fid.get("best_wr_pct"),
                "regime": rg.get("regime"),
                "leader": ld.get("leader"),
                "leader_strength": ld.get("leader_strength"),
                "rotation": ld.get("rotation_detected"),
                "n_coalitions": co.get("n_coalitions"),
            }
        return out
    return _safe(_run, {})


def _get_paper_summary() -> dict:
    def _run():
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        cur = con.cursor()
        cur.execute("""SELECT COUNT(*),
                       SUM(CASE WHEN pips_simulated > 0 THEN 1 ELSE 0 END),
                       AVG(pips_simulated), SUM(pips_simulated)
                       FROM paper_trades""")
        n, w, avg, tot = cur.fetchone()
        con.close()
        return {"n": n, "wr": round(100 * w / n, 1) if n else 0.0,
                "avg_pips": round(avg, 2) if avg else 0.0,
                "total_pips": round(tot, 1) if tot else 0.0}
    return _safe(_run, {"n": 0, "wr": 0.0, "avg_pips": 0.0, "total_pips": 0.0})


def _html_badge(ok: bool, ok_txt: str, ko_txt: str) -> str:
    color = "#27ae60" if ok else "#e74c3c"
    txt = ok_txt if ok else ko_txt
    return (f'<span style="background:{color};color:#fff;padding:2px 10px;'
            f'border-radius:12px;font-size:12px">{txt}</span>')


def generate_html() -> dict:
    bridge = _get_bridge_status()
    ds = _get_dataset_freshness()
    behavior = _get_behavior_summary()
    paper = _get_paper_summary()

    bridge_badge = _html_badge(
        bridge.get("initialized") and bridge.get("cells_live", 0) > 0,
        f"LIVE {bridge.get('cells_live', 0)}/3",
        f"DOWN ({bridge.get('cells_unavail', 0)}/3 unavail)")
    ds_badge = _html_badge(
        ds.get("age_h") is not None and ds.get("age_h", 99) < 24,
        f"FRAIS ({ds.get('age_h', '?')}h, {ds.get('n_signals', 0)} signaux)",
        "STALE")

    rows = ""
    for pair in PAIRS:
        b = behavior.get(pair, {})
        if b.get("verdict") == "NO_DATA":
            rows += (f"<tr><td><b>{pair}</b></td>"
                     f"<td colspan='6' style='color:#888'>données insuffisantes</td></tr>")
            continue
        verdict = _html_badge(
            b.get("verdict") == "RELIABLE", "RELIABLE", "DEGRADED")
        rotation = "🔄" if b.get("rotation") else "—"
        rows += (f"<tr><td><b>{pair}</b></td>"
                 f"<td>{verdict}</td>"
                 f"<td>{b.get('best_currency', '—')} WR {b.get('best_wr', '?')}%</td>"
                 f"<td>{b.get('regime', '?')}</td>"
                 f"<td>{b.get('leader', '?')} ({b.get('leader_strength', '?')}) {rotation}</td>"
                 f"<td>{b.get('n_coalitions', 0)}</td></tr>")

    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>V10 CEO Dashboard</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; background:#1a1d29; color:#e8eaf0; margin:0; padding:20px; }}
h1 {{ color:#5dade2; border-bottom:2px solid #5dade2; padding-bottom:8px; }}
h2 {{ color:#f5b041; margin-top:28px; }}
table {{ border-collapse:collapse; width:100%; margin-top:10px; }}
th,td {{ border:1px solid #3a3f55; padding:8px 12px; text-align:left; }}
th {{ background:#2c3044; color:#aab4d6; }}
tr:nth-child(even) td {{ background:#22263a; }}
.card {{ background:#22263a; border-left:4px solid #5dade2; padding:10px 16px;
        margin:8px 0; border-radius:4px; }}
.verdict-degraded {{ color:#e74c3c; font-weight:bold; }}
.verdict-reliable {{ color:#27ae60; font-weight:bold; }}
.meta {{ color:#8892b0; font-size:12px; }}
</style>
<meta http-equiv="refresh" content="60">
</head><body>
<h1>🚀 V10 CEO DASHBOARD</h1>
<p class="meta">Généré : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
· auto-refresh 60s</p>

<h2>⚡ Infrastructure</h2>
<div class="card">Bridge MT5 : {bridge_badge}
 · compte {bridge.get('account_login', '—')} ({bridge.get('account_server', '—')})
 · n_rate_calls {bridge.get('n_rate_calls', 0)}<br>
Dataset v10_signals_clean : {ds_badge}</div>

<h2>🪙 Comportement des devises (Phase 32)</h2>
<table>
<tr><th>Paire</th><th>Verdict fidélité</th><th>Extrême fiable</th>
<th>Régime</th><th>Leader</th><th>Coalitions</th></tr>
{rows}
</table>

<h2>📊 Paper trades (vérité héritée V9)</h2>
<div class="card">
n={paper.get('n', 0)} · WR {paper.get('wr', 0.0)}% ·
avg {paper.get('avg_pips', 0.0)} pips · total {paper.get('total_pips', 0.0)} pips
</div>

<p class="meta">Doctrine : R1-AGIR · R9 audit honnête · R10 capital protégé
(verdicts DEGRADED exclus du gate)</p>
</body></html>"""
    HTML_PATH.write_text(html, encoding="utf-8")
    return {"bridge": bridge, "dataset": ds, "behavior": behavior,
            "paper": paper, "html": str(HTML_PATH)}


def main() -> int:
    result = generate_html()
    n_reliable = sum(1 for b in result["behavior"].values()
                     if b.get("verdict") == "RELIABLE")
    n_degraded = sum(1 for b in result["behavior"].values()
                     if b.get("verdict") == "DEGRADED")
    print(f"[V10 CEO DASHBOARD] {result['html']}")
    print(f"  Bridge: {'LIVE' if result['bridge'].get('cells_live', 0) > 0 else 'DOWN'} "
          f"({result['bridge'].get('cells_live', 0)}/3 live)")
    print(f"  Dataset: {result['dataset'].get('n_signals', 0)} signaux, "
          f"âge {result['dataset'].get('age_h', '?')}h")
    print(f"  Comportement: {n_reliable} RELIABLE / {n_degraded} DEGRADED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
