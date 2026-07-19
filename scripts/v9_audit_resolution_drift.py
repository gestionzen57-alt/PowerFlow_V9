#!/usr/bin/env python3
"""v9_audit_resolution_drift.py — Audit rétrospectif de la divergence de résolution.

Réconciliation 2026-07-20 (audit live 01h03 UTC). Compare les deux moteurs de
comptage — `decisions` (DYNAMIC) et `paper_trades` (résolution héritée) — sur
les N derniers jours, groupé par contexte, et génère un rapport Markdown.

Lecture seule STRICTE (R6). Ne mute rien (R30 : recommande, n'applique pas).

Codes de sortie :
  0  drift_max < 20  (cohérent)
  1  20 ≤ drift_max < 40  (divergence forte)
  2  drift_max ≥ 40  (système incohérent)

Usage :
    python scripts/v9_audit_resolution_drift.py            # audit + rapport
    python scripts/v9_audit_resolution_drift.py --dry-run  # pas d'écriture fichier
    python scripts/v9_audit_resolution_drift.py --days 30 --db data/v9_forces.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_DB = ROOT_DIR / "data" / "v9_forces.db"
AUDIT_DIR = ROOT_DIR / "workspace" / "perplexity" / "audits"

WARN_THRESHOLD = 20.0
CRITICAL_THRESHOLD = 40.0


def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
    except sqlite3.OperationalError:
        return None


def collect_groups(conn: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    """Groupe la divergence par (symbol, timeframe, direction, regime_type).

    WR paper vient de paper_trades ⋈ decisions (via snapshot_id) ; WR decision
    vient des `decisions` résolues. On aligne les deux sur le même contexte.
    Retourne une liste de dicts triés par drift décroissant.
    """
    # WR/pips côté paper_trades, groupé par contexte de la décision jointe.
    paper_rows = conn.execute(
        """
        SELECT d.symbol AS symbol, d.timeframe AS timeframe,
               pt.direction AS direction, d.regime_type AS regime_type,
               COUNT(*) AS n,
               AVG(CAST(pt.is_win AS FLOAT)) AS wr,
               AVG(pt.pips_simulated) AS avg_pips
        FROM paper_trades pt
        JOIN decisions d ON d.snapshot_id = pt.snapshot_id
        WHERE pt.closed_at IS NOT NULL AND pt.is_win IS NOT NULL
          AND pt.closed_at > datetime('now', ?)
        GROUP BY d.symbol, d.timeframe, pt.direction, d.regime_type
        """,
        (f"-{days} days",),
    ).fetchall()

    dec_rows = conn.execute(
        """
        SELECT symbol, timeframe, direction, regime_type,
               COUNT(*) AS n,
               AVG(CAST(is_win AS FLOAT)) AS wr,
               AVG(resolution_pips) AS avg_pips
        FROM decisions
        WHERE resolved_at IS NOT NULL AND is_win IS NOT NULL
          AND resolved_at > datetime('now', ?)
        GROUP BY symbol, timeframe, direction, regime_type
        """,
        (f"-{days} days",),
    ).fetchall()

    def _key(r):
        return (r[0], r[1], r[2], r[3])

    paper = {_key(r): r for r in paper_rows}
    dec = {_key(r): r for r in dec_rows}

    groups: list[dict[str, Any]] = []
    for key in set(paper) | set(dec):
        p = paper.get(key)
        d = dec.get(key)
        wr_p = float(p[5]) if p and p[5] is not None else None
        wr_d = float(d[5]) if d and d[5] is not None else None
        drift = abs(wr_d - wr_p) * 100.0 if (wr_p is not None and wr_d is not None) else None
        groups.append({
            "symbol": key[0], "timeframe": key[1],
            "direction": key[2], "regime_type": key[3],
            "n_paper": int(p[4]) if p else 0,
            "n_decision": int(d[4]) if d else 0,
            "wr_paper": wr_p, "wr_decision": wr_d,
            "avg_pips_paper": float(p[6]) if p and p[6] is not None else None,
            "avg_pips_decision": float(d[6]) if d and d[6] is not None else None,
            "drift_pct": drift,
        })
    groups.sort(key=lambda g: (g["drift_pct"] is None, -(g["drift_pct"] or 0.0)))
    return groups


def _fmt_pct(v: float | None) -> str:
    return f"{v*100:.1f}%" if v is not None else "—"


def _fmt_num(v: float | None) -> str:
    return f"{v:+.1f}" if v is not None else "—"


def build_report(groups: list[dict[str, Any]], days: int) -> tuple[str, float]:
    """Rend le rapport Markdown. Retourne (markdown, drift_max)."""
    drifts = [g["drift_pct"] for g in groups if g["drift_pct"] is not None]
    drift_max = max(drifts) if drifts else 0.0
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(f"# RESOLUTION DRIFT AUDIT — {ts}")
    lines.append("")
    lines.append(f"Fenêtre : {days} jours · Groupes : {len(groups)} · "
                 f"Drift max : **{drift_max:.1f}%**")
    verdict = ("COHÉRENT" if drift_max < WARN_THRESHOLD else
               "DIVERGENCE FORTE" if drift_max < CRITICAL_THRESHOLD else "INCOHÉRENT (R30)")
    lines.append(f"Verdict : **{verdict}**")
    lines.append("")
    lines.append("## Top 5 divergences")
    lines.append("")
    lines.append("| symbol | tf | dir | regime | n(pt/dec) | WR pt | WR dec | drift | avg pips pt/dec |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for g in groups[:5]:
        lines.append(
            f"| {g['symbol']} | {g['timeframe']} | {g['direction']} | "
            f"{g['regime_type']} | {g['n_paper']}/{g['n_decision']} | "
            f"{_fmt_pct(g['wr_paper'])} | {_fmt_pct(g['wr_decision'])} | "
            f"{g['drift_pct']:.1f}% | {_fmt_num(g['avg_pips_paper'])}/"
            f"{_fmt_num(g['avg_pips_decision'])} |"
            if g["drift_pct"] is not None else
            f"| {g['symbol']} | {g['timeframe']} | {g['direction']} | "
            f"{g['regime_type']} | {g['n_paper']}/{g['n_decision']} | "
            f"{_fmt_pct(g['wr_paper'])} | {_fmt_pct(g['wr_decision'])} | — | "
            f"{_fmt_num(g['avg_pips_paper'])}/{_fmt_num(g['avg_pips_decision'])} |"
        )
    lines.append("")
    lines.append("## Tous les groupes")
    lines.append("")
    lines.append("| symbol | tf | dir | regime | n(pt/dec) | WR pt | WR dec | drift |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for g in groups:
        drift_s = f"{g['drift_pct']:.1f}%" if g["drift_pct"] is not None else "—"
        lines.append(
            f"| {g['symbol']} | {g['timeframe']} | {g['direction']} | "
            f"{g['regime_type']} | {g['n_paper']}/{g['n_decision']} | "
            f"{_fmt_pct(g['wr_paper'])} | {_fmt_pct(g['wr_decision'])} | {drift_s} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("_Généré par `scripts/v9_audit_resolution_drift.py` — lecture seule, "
                 "recommande sans muter (R30)._")
    return "\n".join(lines) + "\n", drift_max


def run_audit(db_path: Path, days: int, dry_run: bool) -> int:
    conn = _connect_ro(db_path)
    if conn is None:
        print(f"[WARN] DB introuvable ou inouvrable : {db_path}")
        return 0
    try:
        groups = collect_groups(conn, days)
    except sqlite3.OperationalError as e:
        print(f"[WARN] audit impossible (schema) : {e}")
        return 0
    finally:
        conn.close()

    report, drift_max = build_report(groups, days)

    print(f"Groupes analysés : {len(groups)} · drift max : {drift_max:.1f}%")
    print("Top 5 divergences :")
    for g in groups[:5]:
        drift_s = f"{g['drift_pct']:.1f}%" if g["drift_pct"] is not None else "—"
        print(f"  {g['symbol']}/{g['timeframe']}/{g['direction']}/{g['regime_type']} "
              f"— drift {drift_s} (n {g['n_paper']}/{g['n_decision']})")

    if not dry_run:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = AUDIT_DIR / f"RESOLUTION_DRIFT_AUDIT_{ts}.md"
        out.write_text(report, encoding="utf-8")
        print(f"Rapport écrit : {out}")
    else:
        print("(dry-run : aucun fichier écrit)")

    if drift_max >= CRITICAL_THRESHOLD:
        return 2
    if drift_max >= WARN_THRESHOLD:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit rétrospectif divergence de résolution.")
    parser.add_argument("--days", type=int, default=30, help="Fenêtre en jours (défaut 30).")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB), help="Chemin DB.")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit aucun fichier.")
    args = parser.parse_args()
    return run_audit(Path(args.db), args.days, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
