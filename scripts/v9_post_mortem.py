"""v9_post_mortem.py — Phase 31 motion CEO autopilote.

Post-mortem automatique d'une journee de trading.
Genere un rapport structure : ce qui a bien marche / mal marche / apprentissages.

Auteur : Hermes (Phase 31 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.post_mortem")

POST_MORTEM_DIR = Path(r"C:\projet\V9\data\post_mortem")


def get_trades_for_day(db_path: Path | str, day: str) -> list[dict]:
    """Retourne les paper trades fermes du jour."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, symbol, direction, opened_at, closed_at,
                       pips_brut, pips_net, close_reason
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND substr(closed_at, 1, 10) = ?
                ORDER BY closed_at ASC
            """, (day,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def build_post_mortem(trades: list[dict], day: str) -> str:
    """Construit le post-mortem markdown."""
    lines = []
    lines.append(f"# Post-Mortem — {day}")
    lines.append("")
    lines.append(f"**Genere le** : {datetime.now(timezone.utc).isoformat()[:19]}")
    lines.append("")

    n_total = len(trades)
    lines.append("## RESUME EXECUTIF")
    if n_total == 0:
        lines.append("Aucun trade ferme ce jour.")
        return "\n".join(lines)
    lines.append(f"- N trades : {n_total}")

    wins = [t for t in trades if t["pips_net"] > 0]
    losses = [t for t in trades if t["pips_net"] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    wr = 100.0 * n_wins / n_total
    total_pips = sum(t["pips_net"] for t in trades)
    expectancy = total_pips / n_total
    lines.append(f"- Win rate : {wr:.1f}% ({n_wins}W / {n_losses}L)")
    lines.append(f"- Total pips net : {total_pips:+.1f}")
    lines.append(f"- Expectancy : {expectancy:+.3f} p/trade")
    lines.append("")

    # Stats par symbol
    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)
    lines.append("## PERFORMANCE PAR SYMBOL")
    for symbol, sym_trades in sorted(by_symbol.items()):
        sym_wins = sum(1 for t in sym_trades if t["pips_net"] > 0)
        sym_wr = 100.0 * sym_wins / len(sym_trades)
        sym_pips = sum(t["pips_net"] for t in sym_trades)
        lines.append(f"- **{symbol}** : {len(sym_trades)} trades, "
                     f"WR {sym_wr:.1f}%, pips {sym_pips:+.1f}")
    lines.append("")

    # Close reasons
    by_close = defaultdict(int)
    for t in trades:
        by_close[t.get("close_reason", "unknown")] += 1
    lines.append("## CLOSE REASONS")
    for reason, count in sorted(by_close.items()):
        pct = 100.0 * count / n_total
        lines.append(f"- {reason} : {count} ({pct:.1f}%)")
    lines.append("")

    # Apprentissages
    lines.append("## CE QUI A BIEN MARCHE")
    if wins:
        best = max(wins, key=lambda t: t["pips_net"])
        lines.append(f"- Meilleur trade : {best['symbol']} {best['direction']} "
                     f"{best['pips_net']:+.1f}p ({best.get('close_reason')})")
    if wr >= 70:
        lines.append(f"- WR eleve : {wr:.1f}% > 70%")
    lines.append("")

    lines.append("## CE QUI A MAL MARCHE")
    if losses:
        worst = min(losses, key=lambda t: t["pips_net"])
        lines.append(f"- Pire trade : {worst['symbol']} {worst['direction']} "
                     f"{worst['pips_net']:+.1f}p ({worst.get('close_reason')})")
    if wr < 50:
        lines.append(f"- WR faible : {wr:.1f}% < 50%")
    if total_pips < 0:
        lines.append(f"- Journee perdante : {total_pips:+.1f}p")
    lines.append("")

    lines.append("## APPRENTISSAGES")
    lines.append("- Analyser pourquoi les losses ont ferme (SL_hit / time_exit / autres)")
    lines.append("- Verifier si les heures des trades correspondent a 11-13h UTC")
    lines.append("- Confirmer que les symbols sont dans GBPUSD 11-13h UTC")
    return "\n".join(lines)


def save_post_mortem(day: str, content: str) -> Path:
    """Sauvegarde le post-mortem."""
    POST_MORTEM_DIR.mkdir(parents=True, exist_ok=True)
    path = POST_MORTEM_DIR / f"{day}.md"
    path.write_text(content, encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 post-mortem (Phase 31)",
    )
    parser.add_argument("--day", default=None,
                        help="Jour YYYY-MM-DD (defaut aujourd'hui UTC)")
    args = parser.parse_args(argv)

    day = args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from core.v9.config import DB_PATH
    trades = get_trades_for_day(DB_PATH, day)
    pm = build_post_mortem(trades, day)
    path = save_post_mortem(day, pm)
    print(pm)
    print()
    print(f">>> Sauvegarde : {path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())