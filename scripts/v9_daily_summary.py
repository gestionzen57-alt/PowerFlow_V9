"""v9_daily_summary.py — Phase 22 motion CEO « EDGE FUND MAX ».

Genere un rapport lisible (Telegram-style) du jour trading.
Combine : trade journal + win streak + paper performance + edge metrics.

Output : data/daily_summary/YYYY-MM-DD.md (markdown lisible)
         data/daily_summary/YYYY-MM-DD.txt (version plain text)

Auteur : Hermes (Phase 22 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.daily_summary")

SUMMARY_DIR = Path(r"C:\projet\V9\data\daily_summary")


def _load_latest_journal(day: str) -> dict | None:
    """Charge le trade journal du jour s'il existe."""
    from scripts.v9_trade_journal import JOURNAL_DIR as _JOURNAL_DIR
    journal_path = _JOURNAL_DIR / f"{day}.json"
    if journal_path.exists():
        try:
            return json.loads(journal_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _get_streaks() -> dict:
    """Recupere les streaks actuels."""
    try:
        from scripts.v9_win_streak import (
            get_recent_trades, compute_streaks, get_recommendation,
        )
        from core.v9.config import DB_PATH
        trades = get_recent_trades(DB_PATH, n=50)
        streaks = compute_streaks(trades)
        rec, _ = get_recommendation(streaks)
        return {"streaks": streaks, "recommendation": rec}
    except Exception as e:
        return {"error": str(e)}


def _get_performance(days: int = 7) -> dict:
    """Recupere la performance N derniers jours."""
    try:
        from scripts.v9_paper_performance import (
            get_paper_trades, compute_performance,
        )
        from core.v9.config import DB_PATH
        trades = get_paper_trades(DB_PATH, days=days)
        return compute_performance(trades)
    except Exception as e:
        return {"error": str(e)}


def build_summary(day: str) -> str:
    """Construit le rapport markdown pour le jour."""
    lines = []
    lines.append(f"# V9 Daily Summary — {day}")
    lines.append("")
    lines.append(f"**Genere le** : {datetime.now(timezone.utc).isoformat()[:19]}")
    lines.append("")

    # Trade journal
    journal = _load_latest_journal(day)
    lines.append("## ▶ Trades du jour")
    if journal and journal.get("n_total", 0) > 0:
        lines.append(f"- **Trades fermes** : {journal['n_total']}")
        lines.append(f"- **Win rate** : {journal['wr_pct']:.1f}%")
        lines.append(f"- **Pips net** : {journal['pips_net']:+.1f}")
        lines.append(f"- **Expectancy** : {journal['expectancy_net']:+.2f}p/trade")
        lines.append(f"- **Meilleur trade** : {journal['max_pips']:+.1f}p")
        lines.append(f"- **Pire trade** : {journal['min_pips']:+.1f}p")
    else:
        lines.append("- Aucun trade ferme ce jour.")
    lines.append("")

    # Win streak
    streaks_data = _get_streaks()
    lines.append("## ▶ Win Streak")
    if "error" not in streaks_data:
        s = streaks_data["streaks"]
        lines.append(f"- **Current** : {s['current_streak']} {s['current_type']}")
        lines.append(f"- **Max win streak** : {s['max_win_streak']}")
        lines.append(f"- **Max loss streak** : {s['max_loss_streak']}")
        lines.append(f"- **Recommendation** : `{streaks_data['recommendation']}`")
    else:
        lines.append(f"- Erreur : {streaks_data['error']}")
    lines.append("")

    # Performance 7j
    perf = _get_performance(days=7)
    lines.append("## ▶ Performance (7 derniers jours)")
    if "error" not in perf and perf.get("n_total", 0) > 0:
        lines.append(f"- **Trades** : {perf['n_total']} "
                     f"(W:{perf['n_wins']}, L:{perf['n_losses']})")
        lines.append(f"- **Win rate** : {perf['win_rate_pct']:.1f}%")
        lines.append(f"- **Pips total** : {perf['total_pips_net']:+.1f}")
        lines.append(f"- **Expectancy net** : {perf['expectancy_net']:+.2f}p")
        lines.append(f"- **Sharpe-like** : {perf['sharpe_like']:.3f}")
        lines.append(f"- **Sortino-like** : {perf['sortino_like']}")
        lines.append(f"- **Profit factor** : {perf['profit_factor']}")
        lines.append(f"- **Max DD** : {perf['max_dd_pips']:.1f}p")
        lines.append(f"- **Recovery factor** : {perf['recovery_factor']}")
    else:
        lines.append("- Pas assez de trades pour analyse 7j.")
    lines.append("")

    # Edge metrics (Phase 15 baseline)
    lines.append("## ▶ Edge Baseline (Phase 15 simulation)")
    lines.append("- **WR** : 94.6% (cible >= 60%)")
    lines.append("- **Expectancy net** : +3.05p (cible >= +3p)")
    lines.append("- **Max DD** : 34.5p (cible <= 100p)")
    lines.append("- **Recovery factor** : 6.5x (cible > 5x)")
    lines.append("- **Sample** : 74 trades GBPUSD haussiere 11-13h UTC 90j")
    lines.append("")

    return "\n".join(lines)


def save_summary(day: str, summary: str) -> tuple[Path, Path]:
    """Sauvegarde le summary en .md et .txt."""
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    md_path = SUMMARY_DIR / f"{day}.md"
    txt_path = SUMMARY_DIR / f"{day}.txt"
    md_path.write_text(summary, encoding="utf-8")
    txt_path.write_text(summary, encoding="utf-8")  # .md est lisible en plain text
    return md_path, txt_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 daily summary generator (Phase 22)",
    )
    parser.add_argument("--day", default=None,
                        help="Jour YYYY-MM-DD (defaut aujourd'hui UTC)")
    args = parser.parse_args(argv)

    day = args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = build_summary(day)
    md_path, txt_path = save_summary(day, summary)
    print(summary)
    print(f"\n>>> Sauvegarde : {md_path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())