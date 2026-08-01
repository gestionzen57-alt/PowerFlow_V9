"""v9_alert_dispatcher.py — Phase 49C motion CEO autopilote.

Dispatcher central : detecte evenements importants via audit + DB
et dispatch via Telegram alert v2.

Auteur : Hermes (Phase 49C motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.dispatcher")


def _get_paper_summary(db_path: Path) -> dict:
    """Stats paper trades recents."""
    if not db_path.exists():
        return {"n_open": 0, "n_closed": 0}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS n_open,
                    SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) AS n_closed,
                    SUM(CASE WHEN closed_at IS NOT NULL AND pips_net > 0 THEN 1 ELSE 0 END) AS n_wins,
                    SUM(CASE WHEN closed_at IS NOT NULL AND pips_net <= 0 THEN 1 ELSE 0 END) AS n_losses,
                    AVG(CASE WHEN closed_at IS NOT NULL THEN pips_net END) AS avg_pips
                FROM v9_paper_trades
                WHERE opened_at > REPLACE(datetime('now', '-7 days'), ' ', 'T')
            """).fetchone()
            return {
                "n_open": int(row[0] or 0),
                "n_closed": int(row[1] or 0),
                "n_wins": int(row[2] or 0),
                "n_losses": int(row[3] or 0),
                "avg_pips": float(row[4] or 0.0),
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"n_open": 0, "n_closed": 0, "n_wins": 0, "n_losses": 0,
                "avg_pips": 0.0}


def _compute_wr(summary: dict) -> float:
    """WR depuis summary."""
    total = summary["n_wins"] + summary["n_losses"]
    return summary["n_wins"] / total if total > 0 else 0.0


def detect_and_dispatch(db_path: Path,
                          telegram_dry_run: bool = True) -> dict:
    """Detecte evenements et dispatch alertes."""
    from scripts.v9_telegram_alerts import (
        emit_alert, classify_event,
    )
    summary = _get_paper_summary(db_path)
    wr = _compute_wr(summary)
    events_dispatched = []
    # Event 1 : WR < 60%
    if summary["n_closed"] >= 5 and wr < 0.60:
        result = emit_alert(
            "WR_DROP_BELOW_60",
            {"wr": round(wr, 3), "n_trades": summary["n_closed"],
             "avg_pips": round(summary["avg_pips"], 2)},
            dry_run=telegram_dry_run,
        )
        events_dispatched.append(result)
    # Event 2 : avg pips < 0
    if summary["n_closed"] >= 5 and summary["avg_pips"] < 0:
        result = emit_alert(
            "EXPECTANCY_NEGATIVE",
            {"avg_pips": round(summary["avg_pips"], 2),
             "n_trades": summary["n_closed"]},
            dry_run=telegram_dry_run,
        )
        events_dispatched.append(result)
    # Event 3 : daily audit OK
    if summary["n_closed"] >= 20 and wr >= 0.85:
        result = emit_alert(
            "DAILY_AUDIT_OK",
            {"wr": round(wr, 3), "n_trades": summary["n_closed"],
             "avg_pips": round(summary["avg_pips"], 2)},
            dry_run=telegram_dry_run,
        )
        events_dispatched.append(result)
    # Event 4 : sentiment flip (via market sentiment)
    try:
        from scripts.v9_market_sentiment import (
            get_paper_trades_directional, compute_sentiment,
        )
        directional = get_paper_trades_directional(db_path, days=7)
        sentiment = compute_sentiment(directional)
        if abs(sentiment.get("score", 0)) > 0.5:
            result = emit_alert(
                "SENTIMENT_FLIP",
                {"sentiment": sentiment.get("sentiment", "NEUTRAL"),
                 "score": sentiment.get("score", 0)},
                dry_run=telegram_dry_run,
            )
            events_dispatched.append(result)
    except Exception:
        pass
    # Event 5 : regime change (via regime detector)
    try:
        from scripts.v9_regime_detector import (
            get_paper_trades_recent, detect_regime,
        )
        trades = get_paper_trades_recent(db_path, days=7)
        regime = detect_regime(trades)
        if regime.get("regime") == "DEFAVORABLE":
            result = emit_alert(
                "REGIME_CHANGE",
                {"regime": regime.get("regime", "UNKNOWN"),
                 "size_factor": regime.get("position_size_factor", 1.0)},
                dry_run=telegram_dry_run,
            )
            events_dispatched.append(result)
    except Exception:
        pass
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "wr": round(wr, 3),
        "n_events_dispatched": len(events_dispatched),
        "events": [
            {
                "type": e["alert"]["event_type"],
                "severity": e["alert"]["severity"],
                "sent": e["send"]["sent"],
            }
            for e in events_dispatched
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 alert dispatcher (Phase 49C)",
    )
    parser.add_argument("--live", action="store_true",
                        help="Live send (sinon dry_run)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = detect_and_dispatch(Path(DB_PATH),
                                    telegram_dry_run=not args.live)
    print("=" * 70)
    print("PHASE 49C — ALERT DISPATCHER")
    print("=" * 70)
    print(f"Summary    : {result['summary']}")
    print(f"WR         : {result['wr']}")
    print(f"Events     : {result['n_events_dispatched']}")
    for evt in result["events"]:
        print(f"  - {evt['type']:25s} [{evt['severity']:8s}] sent={evt['sent']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())