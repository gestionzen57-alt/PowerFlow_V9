#!/usr/bin/env python3
"""
v10_walkforward_30d.py — Validation walk-forward 30 jours EURUSD M30
Sprint 24 — généré par Perplexity GitHub MCP

Objectif:
- Évaluer out-of-sample la paire EURUSD en M30 sur les 30 derniers jours
- Produire WR, nombre de trades, proxy Sharpe, verdict GO/NO-GO
- Sauvegarder un rapport JSON pour audit

Doctrine: R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL (paper only)
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
DB_PATH = Path("data/v10_decisions.db")
PAIR = "EURUSD"
TF = "M30"
WINDOW_DAYS = 30


def _proxy_sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((x - mean) ** 2 for x in returns) / max(1, len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return round(mean / std, 4)


def run() -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    report = {
        "timestamp_utc": ts,
        "script": "v10_walkforward_30d.py",
        "pair": PAIR,
        "timeframe": TF,
        "window_days": WINDOW_DAYS,
        "status": "OK",
    }

    if not DB_PATH.exists():
        report["status"] = "DB_ABSENT"
        out = REPORTS_DIR / f"v10_walkforward_30d_{PAIR}_{TF}_{ts}.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'")
        if not cur.fetchone():
            report["status"] = "TABLE_ABSENT"
        else:
            cur.execute(
                """
                SELECT created_at, action, pair, timeframe, pnl, is_win
                FROM decisions
                WHERE pair = ?
                  AND timeframe = ?
                  AND action IN ('BUY','SELL')
                  AND created_at >= ?
                  AND is_win IS NOT NULL
                ORDER BY created_at ASC
                """,
                (PAIR, TF, since.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
            rows = cur.fetchall()
            n = len(rows)
            wins = sum(1 for r in rows if r[5] == 1)
            wr = round(wins / n, 4) if n else None
            pnls = [float(r[4]) for r in rows if r[4] is not None]
            sharpe = _proxy_sharpe(pnls)
            avg_pnl = round(sum(pnls) / len(pnls), 4) if pnls else None

            go = bool(
                n >= 60 and
                wr is not None and wr >= 0.55 and
                sharpe is not None and sharpe >= 0.3
            )

            report.update({
                "n_trades": n,
                "wins": wins,
                "wr": wr,
                "avg_pnl": avg_pnl,
                "proxy_sharpe": sharpe,
                "criteria": {
                    "min_trades": 60,
                    "min_wr": 0.55,
                    "min_proxy_sharpe": 0.3,
                },
                "verdict": "GO" if go else "NO_GO",
            })
    except Exception as e:
        report["status"] = "ERROR"
        report["error"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out = REPORTS_DIR / f"v10_walkforward_30d_{PAIR}_{TF}_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"report={out}")
    return report


if __name__ == "__main__":
    run()
