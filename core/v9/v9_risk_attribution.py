"""v9_risk_attribution.py — Phase 132 : Risk Attribution par principe × regime × session.

Module additif (R2) qui calcule la décomposition du risque par croisement
principe × regime × session. Permet d'identifier les niches structurelles
contributrices au risque total du portefeuille paper-trade.

Mission CEO no-stop 03/08/2026 — sprint L11+.

Hypothèse : les risques sont concentrés sur quelques croisements
principe × regime × session. L'identification de ces concentrations
permet de calibrer les kill switches ciblés (au lieu de blacklister un
principe entier, blacklister un croisement).

Doctrine : R2 additif, R6 fail-open, R14 git verite, R25' motion CEO.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH

VERSION = "1.0"
OUTPUT_PATH_DEFAULT = Path("data/risk_attribution/v9_risk_attribution.json")


# ── Helpers de requete SQL ──────────────────────────────────────────
def _query_trades_by_cross(db_path: Path = DB_PATH) -> list[dict]:
    """Retourne la liste des trades avec (principe_set, regime, session, pnl, is_win).

    Principe_set = tuple(sorted des principes) pour permettre le groupement.
    Regime = depuis regime_snapshots.
    Session = inférée depuis le timestamp via infer_session_from_hour.
    """
    from core.v9.exit_simulator import infer_session_from_hour
    from datetime import datetime

    con = sqlite3.connect(str(db_path), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
                pt.snapshot_id,
                pt.direction,
                pt.is_win,
                pt.pips_simulated,
                pt.principes_source,
                fs.timestamp AS ts_forces,
                rs.regime_type
            FROM paper_trades pt
            LEFT JOIN forces_snapshots fs
                ON fs.snapshot_id = pt.snapshot_id
            LEFT JOIN regime_snapshots rs
                ON rs.forces_snapshot_ref = fs.snapshot_id
            WHERE pt.closed_at IS NOT NULL
            """
        ).fetchall()
    finally:
        con.close()

    trades = []
    for r in rows:
        ts_str = r["ts_forces"] or ""
        if not ts_str:
            continue
        try:
            d = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        session = infer_session_from_hour(d.hour)
        regime = (r["regime_type"] or "UNKNOWN").upper()

        principes_raw = r["principes_source"] or ""
        if not principes_raw:
            continue
        # Tuple sorted pour groupement stable
        principe_set = tuple(sorted(p.strip() for p in principes_raw.split(",") if p.strip()))

        trades.append({
            "principe_set": principe_set,
            "regime": regime,
            "session": session,
            "direction": (r["direction"] or "").lower(),
            "is_win": r["is_win"] or 0,
            "pips": r["pips_simulated"] or 0.0,
        })
    return trades


# ── Attribution du risque ───────────────────────────────────────────
def compute_risk_attribution(trades: list[dict] | None = None,
                              db_path: Path = DB_PATH) -> dict:
    """Calcule l'attribution du risque par croisement (principe_set, regime, session).

    Retourne un dict :
      - "by_cross" : dict[(principe_set, regime, session), stats]
      - "by_principe" : dict[principle, aggregated stats]
      - "by_regime" : dict[regime, aggregated stats]
      - "by_session" : dict[session, aggregated stats]
      - "total_n" : int
      - "total_pnl" : float
      - "concentration" : float (% du PNL négatif concentré sur les top-5 croisements)
    """
    if trades is None:
        trades = _query_trades_by_cross(db_path)
    if not trades:
        return {
            "by_cross": {},
            "by_principe": {},
            "by_regime": {},
            "by_session": {},
            "total_n": 0,
            "total_pnl": 0.0,
            "concentration": 0.0,
        }

    # Aggregation par croisement
    by_cross: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "pnl": 0.0}
    )
    # Aggregation par axe
    by_principe: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "pnl": 0.0}
    )
    by_regime: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "pnl": 0.0}
    )
    by_session: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "pnl": 0.0}
    )

    total_n = 0
    total_pnl = 0.0
    for t in trades:
        key = (t["principe_set"], t["regime"], t["session"])
        b = by_cross[key]
        b["n"] += 1
        b["wins"] += t["is_win"]
        b["pnl"] += t["pips"]

        for p in t["principe_set"]:
            bp = by_principe[p]
            bp["n"] += 1
            bp["wins"] += t["is_win"]
            bp["pnl"] += t["pips"]

        by_regime[t["regime"]]["n"] += 1
        by_regime[t["regime"]]["wins"] += t["is_win"]
        by_regime[t["regime"]]["pnl"] += t["pips"]

        by_session[t["session"]]["n"] += 1
        by_session[t["session"]]["wins"] += t["is_win"]
        by_session[t["session"]]["pnl"] += t["pips"]

        total_n += 1
        total_pnl += t["pips"]

    # Concentration : top 5 croisements par PNL negatif / PNL total negatif
    negative_crosses = sorted(
        ((k, v["pnl"]) for k, v in by_cross.items() if v["pnl"] < 0),
        key=lambda x: x[1],  # Plus negatif en premier
    )
    total_negative = sum(p for _, p in negative_crosses) or 1.0
    top5_negative = sum(p for _, p in negative_crosses[:5])
    concentration = round(abs(top5_negative) / abs(total_negative) * 100, 1)

    # Round pnl for all dicts
    def _round_stats(d: dict) -> dict:
        return {
            k: {"n": v["n"], "wins": v["wins"], "pnl": round(v["pnl"], 1)}
            for k, v in d.items()
        }

    return {
        "by_cross": _round_stats({
            ",".join(k[0]) + "|" + k[1] + "|" + k[2]: v
            for k, v in by_cross.items()
        }),
        "by_principe": _round_stats(by_principe),
        "by_regime": _round_stats(by_regime),
        "by_session": _round_stats(by_session),
        "total_n": total_n,
        "total_pnl": round(total_pnl, 1),
        "concentration": concentration,
    }


# ── Top risque ──────────────────────────────────────────────────────
def top_risk_concentrations(attribution: dict, top_n: int = 5) -> list[dict]:
    """Retourne les top N croisements qui concentrent le risque negatif."""
    items = []
    for k, v in attribution.get("by_cross", {}).items():
        if v["pnl"] < 0:
            items.append({
                "cross": k,
                "n": v["n"],
                "wins": v["wins"],
                "pnl": v["pnl"],
                "wr_pct": round(v["wins"] / v["n"] * 100, 1) if v["n"] > 0 else 0,
            })
    items.sort(key=lambda x: x["pnl"])
    return items[:top_n]


# ── CLI minimal ─────────────────────────────────────────────────────
def render_report(attribution: dict, top_risks: list[dict]) -> str:
    """Genere un rapport markdown lisible."""
    lines = [
        "# Phase 132 — Risk Attribution par principe × regime × session",
        "",
        f"**Total trades** : {attribution['total_n']}",
        f"**PNL cumulé** : {attribution['total_pnl']:+.1f}p",
        f"**Concentration du risque** : {attribution['concentration']}% du PNL négatif sur top-5 croisements",
        "",
        "## Top 5 croisements par risque (PNL négatif)",
        "",
        "| Cross (principes|regime|session) | n | WR | PNL |",
        "|---|---|---|---|",
    ]
    for r in top_risks:
        lines.append(f"| {r['cross']} | {r['n']} | {r['wr_pct']}% | {r['pnl']:+.1f}p |")

    lines.extend([
        "",
        "## PNL par regime",
        "",
        "| Regime | n | WR | PNL |",
        "|---|---|---|---|",
    ])
    for regime, v in sorted(attribution.get("by_regime", {}).items()):
        wr = v["wins"] / v["n"] * 100 if v["n"] > 0 else 0
        lines.append(f"| {regime} | {v['n']} | {wr:.1f}% | {v['pnl']:+.1f}p |")

    lines.extend([
        "",
        "## PNL par session",
        "",
        "| Session | n | WR | PNL |",
        "|---|---|---|---|",
    ])
    for sess, v in sorted(attribution.get("by_session", {}).items()):
        wr = v["wins"] / v["n"] * 100 if v["n"] > 0 else 0
        lines.append(f"| {sess} | {v['n']} | {wr:.1f}% | {v['pnl']:+.1f}p |")

    lines.extend([
        "",
        "## PNL par principe (top 10 negatif)",
        "",
        "| Principe | n | WR | PNL |",
        "|---|---|---|---|",
    ])
    by_princ_sorted = sorted(
        attribution.get("by_principe", {}).items(), key=lambda x: x[1]["pnl"]
    )
    for p, v in by_princ_sorted[:10]:
        wr = v["wins"] / v["n"] * 100 if v["n"] > 0 else 0
        lines.append(f"| {p} | {v['n']} | {wr:.1f}% | {v['pnl']:+.1f}p |")

    return "\n".join(lines)


def main(db_path: Path = DB_PATH,
         output: Path | None = None,
         report: Path | None = None) -> int:
    """Point d'entree CLI."""
    output = output or OUTPUT_PATH_DEFAULT
    report = report or output.with_suffix(".md")
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Chargement des trades depuis {db_path}...")
    trades = _query_trades_by_cross(db_path)
    print(f"  -> {len(trades)} trades charges")

    attribution = compute_risk_attribution(trades, db_path)
    top_risks = top_risk_concentrations(attribution, top_n=5)
    print(f"  -> {len(attribution['by_cross'])} croisements")
    print(f"  -> concentration du risque : {attribution['concentration']}%")

    # Output JSON
    output.write_text(
        json.dumps(attribution, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"JSON ecrit: {output}")

    # Output Markdown
    md = render_report(attribution, top_risks)
    report.write_text(md, encoding="utf-8")
    print(f"Markdown ecrit: {report}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())