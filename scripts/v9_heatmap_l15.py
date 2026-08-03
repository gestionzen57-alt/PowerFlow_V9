#!/usr/bin/env python3
"""v9_heatmap_l15.py — Heatmap regime × session × pattern (Phase 126 L15).

Mission : identifier les niches structurelles WR>70% ET n>=10 sur les
3 axes (regime, session, pattern) pour calibrer le levier L15 (filtre
croisé multi-dimensionnel). Sprint CEO no-stop 03/08/2026.

Livrables :
- data/heatmaps/l15_regime_session_pattern.json
- data/heatmaps/l15_heatmap_report.md (markdown)
- Proposition 3-5 nouveaux kill switches (R6 fail-open, R25' motion CEO)

Doctrine : R2 additif, R6 fail-open, R14 git verite, R22 sous-unite unique,
R25' motion CEO explicite, R26 DECISIONS_LOG entry dediee.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.v9.exit_simulator import infer_session_from_hour  # noqa: E402
from core.v9.config import DB_PATH  # noqa: E402


# ── Config ────────────────────────────────────────────────────────────
OUTPUT_DIR = _ROOT / "data" / "heatmaps"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 4 regimes × 5 sessions × 4 patterns (1, 2, 3, 5+ principes) = 80 cases cibles
REGIMES = ("CASSURE", "EXTENSION", "DISTRIBUTION", "RETOUR_EQUILIBRE", "REJET")
SESSIONS = ("asie", "london", "overlap", "new_york", "after")
PATTERNS = ("1", "2", "3", "4", "5+")

# Seuils de niche
NICHE_MIN_TRADES = 10
NICHE_MIN_WR = 70.0  # %


def _symbol_from_snapshot(snapshot_id: str) -> str:
    """Parse `v9-{SYMBOL}-{TF}-{bar_time}-{seq}` -> SYMBOL."""
    if not snapshot_id:
        return "UNKNOWN"
    parts = snapshot_id.split("-")
    if len(parts) >= 3 and parts[0] == "v9":
        return parts[1]
    return "UNKNOWN"


# ── Charge les trades depuis la DB ────────────────────────────────────
def load_trades(db_path: Path = DB_PATH) -> list[dict]:
    """Jointure paper_trades + forces_snapshots + regime_snapshots.

    Retourne liste de dicts avec : symbol, timestamp, utc_hour, session,
    regime, n_principes, pattern, is_win, pips_simulated.
    """
    con = sqlite3.connect(str(db_path), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        # Dédoublonnage regime_snapshots (1 regime par snapshot)
        rows = con.execute(
            """
            SELECT
                pt.snapshot_id,
                pt.direction,
                pt.is_win,
                pt.pips_simulated,
                pt.principes_source,
                fs.timestamp AS ts_forces,
                fs.symbol AS symbol_fs,
                (SELECT rs1.regime_type FROM regime_snapshots rs1
                 WHERE rs1.forces_snapshot_ref = fs.snapshot_id
                 ORDER BY rs1.timestamp DESC LIMIT 1) AS regime_type
            FROM paper_trades pt
            LEFT JOIN forces_snapshots fs
                ON fs.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL
            """
        ).fetchall()
    finally:
        con.close()

    trades = []
    for r in rows:
        ts_str = r["ts_forces"] or ""
        try:
            # Format ISO ou epoch
            if "T" in ts_str or " " in ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                ts = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        utc_hour = ts.hour
        session = infer_session_from_hour(utc_hour)
        regime = (r["regime_type"] or "UNKNOWN").upper()
        principes = r["principes_source"] or ""
        if not principes:
            continue
        n_principes = principes.count(",") + 1
        pattern = str(n_principes) if n_principes < 5 else "5+"
        symbol = r["symbol_fs"] or _symbol_from_snapshot(r["snapshot_id"])
        direction = (r["direction"] or "").lower()

        trades.append({
            "symbol": symbol,
            "direction": direction,
            "timestamp": ts.isoformat(),
            "utc_hour": utc_hour,
            "session": session,
            "regime": regime,
            "n_principes": n_principes,
            "pattern": pattern,
            "is_win": r["is_win"] or 0,
            "pips": r["pips_simulated"] or 0.0,
        })
    return trades


# ── Heatmap builder ───────────────────────────────────────────────────
def _stringify_keys(d):
    """Sérialise récursivement les tuples en strings pour JSON."""
    if isinstance(d, dict):
        return {(_stringify_keys(k) if not isinstance(k, str) else k): _stringify_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_stringify_keys(x) for x in d]
    if isinstance(d, tuple):
        return ",".join(str(x) for x in d)
    return d


def build_heatmap(trades: list[dict]) -> dict:
    """Construit le heatmap 3D regime × session × pattern + 2D symbol × session."""
    # 3D : regime × session × pattern
    heatmap_3d: dict = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0}))
    )
    # 2D : symbol × session
    heatmap_2d: dict = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})

    for t in trades:
        key3 = (t["regime"], t["session"], t["pattern"])
        bucket3 = heatmap_3d[key3[0]][key3[1]][key3[2]]
        bucket3["n"] += 1
        bucket3["wins"] += t["is_win"]
        bucket3["pnl"] += t["pips"]

        key2 = (t["symbol"], t["session"])
        bucket2 = heatmap_2d[key2]
        bucket2["n"] += 1
        bucket2["wins"] += t["is_win"]
        bucket2["pnl"] += t["pips"]

    return {"3d_regime_session_pattern": dict(heatmap_3d),
            "2d_symbol_session": dict(heatmap_2d)}


# ── Niche detection ──────────────────────────────────────────────────
def find_niches(heatmap: dict, min_n: int = NICHE_MIN_TRADES,
                min_wr: float = NICHE_MIN_WR) -> list[dict]:
    """Détecte les niches structurelles WR > min_wr ET n >= min_n."""
    niches = []
    for regime, sessions in heatmap["3d_regime_session_pattern"].items():
        for session, patterns in sessions.items():
            for pattern, stats in patterns.items():
                if stats["n"] < min_n:
                    continue
                wr = stats["wins"] / stats["n"] * 100
                if wr >= min_wr:
                    niches.append({
                        "regime": regime,
                        "session": session,
                        "pattern": pattern,
                        "n": stats["n"],
                        "wins": stats["wins"],
                        "wr_pct": round(wr, 1),
                        "pnl": round(stats["pnl"], 1),
                        "avg_pips": round(stats["pnl"] / stats["n"], 2),
                    })
    # Top niches par gain total
    niches.sort(key=lambda x: -x["pnl"])
    return niches


# ── Kill switch proposal ────────────────────────────────────────────
def propose_kill_switches(niches: list[dict], heatmap: dict) -> list[dict]:
    """Propose 3-5 kill switches basés sur les niches identifiées.

    Logique : si 1 niche WR>80% ET n>=20 → proposer un BOOST sizing
    (multiplicateur 1.3 sur ce contexte). Si 1 anti-niche WR<30% → BLACKLIST.
    """
    proposals = []

    # Filtre 1 : top niches avec n>=20 → boost sizing
    top_boost = [n for n in niches if n["n"] >= 20 and n["wr_pct"] >= 80]
    for n in top_boost[:2]:
        proposals.append({
            "type": "BOOST",
            "kill_switch": f"V9_HEATMAP_L15_BOOST_{n['regime']}_{n['session']}_{n['pattern']}_ENABLED",
            "regime": n["regime"],
            "session": n["session"],
            "pattern": n["pattern"],
            "rationale": f"WR={n['wr_pct']}% sur n={n['n']} (top niche), gain {n['pnl']}p",
            "default": "0",
            "sizing_multiplier": 1.3,
        })

    # Filtre 2 : anti-niches WR<30% ET n>=15 → blacklist
    for regime, sessions in heatmap["3d_regime_session_pattern"].items():
        for session, patterns in sessions.items():
            for pattern, stats in patterns.items():
                if stats["n"] < 15:
                    continue
                wr = stats["wins"] / stats["n"] * 100
                if wr < 30:
                    proposals.append({
                        "type": "BLACKLIST",
                        "kill_switch": f"V9_HEATMAP_L15_BLACKLIST_{regime}_{session}_{pattern}_ENABLED",
                        "regime": regime,
                        "session": session,
                        "pattern": pattern,
                        "rationale": f"WR={wr:.1f}% < 30% sur n={stats['n']} (anti-niche), perte {stats['pnl']}p",
                        "default": "0",
                        "sizing_multiplier": 0.0,
                    })

    return proposals


# ── Markdown report ──────────────────────────────────────────────────
def render_markdown(heatmap: dict, niches: list[dict], proposals: list[dict],
                    total_trades: int) -> str:
    """Génère un rapport markdown lisible."""
    lines = [
        "# L15 Heatmap — regime × session × pattern (Phase 126)",
        "",
        f"**Généré le** : {datetime.now(timezone.utc).isoformat()}",
        f"**Total trades analysés** : {total_trades}",
        f"**Niches détectées (WR>70% ET n>=10)** : {len(niches)}",
        f"**Kill switches proposés** : {len(proposals)}",
        "",
        "## Top 10 niches structurelles",
        "",
        "| Regime | Session | Pattern | n | WR | PNL | avg/trade |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in niches[:10]:
        lines.append(
            f"| {n['regime']} | {n['session']} | {n['pattern']} | {n['n']} | "
            f"{n['wr_pct']}% | {n['pnl']:+}p | {n['avg_pips']:+}p |"
        )

    lines.extend([
        "",
        "## Heatmap 3D (regime × session × pattern)",
        "",
        "Format : `[regime,session,pattern] : n=X WR=Y% PNL=Z p`",
        "",
    ])

    for regime in sorted(heatmap["3d_regime_session_pattern"].keys()):
        lines.append(f"### Regime: {regime}")
        lines.append("")
        for session in sorted(heatmap["3d_regime_session_pattern"][regime].keys()):
            lines.append(f"- **{session}**")
            for pattern in sorted(heatmap["3d_regime_session_pattern"][regime][session].keys()):
                s = heatmap["3d_regime_session_pattern"][regime][session][pattern]
                if s["n"] == 0:
                    continue
                wr = s["wins"] / s["n"] * 100
                marker = " 🔥" if wr >= 70 and s["n"] >= 10 else ""
                marker = " 💀" if wr < 30 and s["n"] >= 10 else marker
                lines.append(
                    f"  - pattern={pattern}: n={s['n']} WR={wr:.1f}% PNL={s['pnl']:+.1f}p{marker}"
                )
        lines.append("")

    lines.extend([
        "## Heatmap 2D (symbol × session)",
        "",
        "| Symbol | Session | n | WR | PNL |",
        "|---|---|---|---|---|",
    ])
    for (sym, sess), s in sorted(heatmap["2d_symbol_session"].items()):
        wr = s["wins"] / s["n"] * 100
        lines.append(f"| {sym} | {sess} | {s['n']} | {wr:.1f}% | {s['pnl']:+.1f}p |")

    lines.extend([
        "",
        "## Kill switches proposés",
        "",
    ])
    for p in proposals:
        lines.append(f"### {p['type']} — `{p['kill_switch']}`")
        lines.append(f"- **Regime** : {p['regime']}")
        lines.append(f"- **Session** : {p['session']}")
        lines.append(f"- **Pattern** : {p['pattern']}")
        lines.append(f"- **Rationale** : {p['rationale']}")
        lines.append(f"- **Default** : {p['default']} (R25' strict, motion CEO explicite)")
        lines.append(f"- **Sizing multiplier** : {p['sizing_multiplier']}")
        lines.append("")

    lines.extend([
        "## Doctrine",
        "",
        "- R2 additif : heatmap + propositions, 0 modif code core/ (lecture seule)",
        "- R6 fail-open : kill switches défauts OFF",
        "- R14 git verite : chiffres extraits du SQL réel, pas inventes",
        "- R22 sous-unite unique : 1 livrable = 1 heatmap",
        "- R25' motion CEO explicite requise pour activation",
        "- R26 DECISIONS_LOG entry dediee",
        "- R28 Hermes operateur git unique",
    ])

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L15 heatmap regime × session × pattern")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--min-n", type=int, default=NICHE_MIN_TRADES)
    parser.add_argument("--min-wr", type=float, default=NICHE_MIN_WR)
    parser.add_argument("--output", type=Path,
                        default=OUTPUT_DIR / "l15_regime_session_pattern.json")
    parser.add_argument("--report", type=Path,
                        default=OUTPUT_DIR / "l15_heatmap_report.md")
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"DB introuvable: {args.db}", file=sys.stderr)
        return 4

    print(f"Chargement des trades depuis {args.db}...")
    trades = load_trades(args.db)
    print(f"  → {len(trades)} trades charges")

    print("Construction heatmap...")
    heatmap = build_heatmap(trades)
    print(f"  → {len(heatmap['3d_regime_session_pattern'])} regimes x sessions x patterns")

    print(f"Detection niches (WR>={args.min_wr}% ET n>={args.min_n})...")
    niches = find_niches(heatmap, min_n=args.min_n, min_wr=args.min_wr)
    print(f"  → {len(niches)} niches detectees")

    print("Proposition kill switches...")
    proposals = propose_kill_switches(niches, heatmap)
    print(f"  → {len(proposals)} switches proposes")

    # Output JSON (sérialise les tuples en strings)
    output_payload = {
        "schema_version": "1.0",
        "phase": "126",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_source": str(args.db),
        "total_trades": len(trades),
        "niches_count": len(niches),
        "proposals_count": len(proposals),
        "thresholds": {"min_n": args.min_n, "min_wr": args.min_wr},
        "heatmap": _stringify_keys(heatmap),
        "niches": niches,
        "proposals": proposals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output_payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    print(f"JSON ecrit: {args.output}")

    # Output Markdown
    md = render_markdown(heatmap, niches, proposals, len(trades))
    args.report.write_text(md, encoding="utf-8")
    print(f"Markdown ecrit: {args.report}")

    # Top 3 niches
    print()
    print("=== Top 3 niches ===")
    for n in niches[:3]:
        print(f"  {n['regime']:>15} × {n['session']:>10} × pattern={n['pattern']:>2} : "
              f"n={n['n']:>3} WR={n['wr_pct']:>5.1f}% PNL={n['pnl']:>+7.1f}p")

    return 0


if __name__ == "__main__":
    sys.exit(main())
