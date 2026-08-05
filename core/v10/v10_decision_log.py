"""V10 Decision Log — journal persistant des décisions + synthèse (Sprint 16).

Persiste chaque décision BUY/SELL/WAIT produite par `decide_entry` dans une
table SQLite `v10_decisions`, puis permet la synthèse de performance réelle :
WR, PnL, Sharpe-like par paire × action, pour valider l'edge des signaux
produits par le pipeline (lecture cohérente, apprentissage des erreurs).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open (DB indisponible → in-memory),
R7, R9 audit honnête (proxy pnl), R10 zéro ordre réel (log des décisions only).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS v10_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    timeframe TEXT,
    timestamp TEXT,
    action TEXT,
    signal_level TEXT,
    filtered_level TEXT,
    lot_size REAL,
    pnl_pips REAL,
    is_win INTEGER,
    audit_json TEXT
);
"""


@dataclass
class DecisionRecord:
    pair: str = ""
    timeframe: str = ""
    timestamp: str = ""
    action: str = "WAIT"
    signal_level: str = "NONE"
    filtered_level: str = "NONE"
    lot_size: float = 0.0
    pnl_pips: float = 0.0
    is_win: Optional[bool] = None

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "timestamp": self.timestamp, "action": self.action,
            "signal_level": self.signal_level,
            "filtered_level": self.filtered_level,
            "lot_size": round(self.lot_size, 4),
            "pnl_pips": round(self.pnl_pips, 2),
            "is_win": self.is_win,
        }


class DecisionLogger:
    """Journal SQLite des décisions (R6 : fallback in-memory)."""

    def __init__(self, db_path: str = "data/v10_decisions.db"):
        self.db_path = db_path
        self._mem: Optional[List[DecisionRecord]] = []
        self._conn = None
        try:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(SCHEMA)
            self._conn.commit()
            self._mem = None  # SQLite actif
        except Exception as exc:
            log.warning("SQLite indisponible, fallback in-memory (R6): %s", exc)
            self._conn = None
            self._mem = []

    def append(self, rec: DecisionRecord) -> None:
        if self._conn is not None:
            try:
                self._conn.execute(
                    "INSERT INTO v10_decisions "
                    "(pair, timeframe, timestamp, action, signal_level, "
                    "filtered_level, lot_size, pnl_pips, is_win, audit_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rec.pair, rec.timeframe, rec.timestamp, rec.action,
                     rec.signal_level, rec.filtered_level, rec.lot_size,
                     rec.pnl_pips, 1 if rec.is_win else 0 if rec.is_win is False else None,
                     json.dumps(rec.as_dict(), ensure_ascii=False)),
                )
                self._conn.commit()
            except Exception as exc:
                log.warning("append échoué (R6): %s", exc)
        elif self._mem is not None:
            self._mem.append(rec)

    def all_records(self) -> List[DecisionRecord]:
        if self._conn is not None:
            try:
                rows = self._conn.execute(
                    "SELECT pair, timeframe, timestamp, action, signal_level, "
                    "filtered_level, lot_size, pnl_pips, is_win "
                    "FROM v10_decisions ORDER BY id").fetchall()
                return [
                    DecisionRecord(pair=r[0], timeframe=r[1], timestamp=r[2],
                                   action=r[3], signal_level=r[4],
                                   filtered_level=r[5], lot_size=r[6] or 0.0,
                                   pnl_pips=r[7] or 0.0,
                                   is_win=bool(r[8]) if r[8] is not None else None)
                    for r in rows
                ]
            except Exception as exc:
                log.warning("read échoué (R6): %s", exc)
                return []
        return list(self._mem or [])

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass


def summarize_decisions(records: List[DecisionRecord]) -> Dict:
    """Synthèse de performance réelle des décisions (WR, PnL, Sharpe-like).

    R9 honnête : pnl/is_win sont des proxies (is_win_proxy). Edge RELATIF.
    """
    total = len(records)
    if total == 0:
        return {"n": 0, "by_action": {}}

    trades = [r for r in records if r.action in ("BUY", "SELL")]
    wins = [r for r in trades if r.is_win]
    pnls = [r.pnl_pips for r in trades]

    # Sharpe-like
    sharpe = 0.0
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = var ** 0.5
        if sd > 0:
            sharpe = mean / sd

    # Par (pair, action)
    by_pair_action: Dict[str, Dict] = {}
    for r in trades:
        key = f"{r.pair}|{r.action}"
        b = by_pair_action.setdefault(key, {"n": 0, "wins": 0, "pnl": 0.0})
        b["n"] += 1
        b["wins"] += 1 if r.is_win else 0
        b["pnl"] += r.pnl_pips
    for k, b in by_pair_action.items():
        if b["n"]:
            b["wr"] = round(b["wins"] / b["n"], 4)
            b["pnl"] = round(b["pnl"], 2)

    return {
        "n_total": total,
        "n_trades": len(trades),
        "n_buysell_active": len([r for r in trades if r.is_win is not None]),
        "wr": round(sum(1 for r in wins) / len(trades), 4) if trades else 0.0,
        "total_pnl": round(sum(pnls), 2),
        "sharpe_like": round(sharpe, 3),
        "by_pair_action": dict(sorted(
            by_pair_action.items(), key=lambda kv: -kv[1]["wr"])),
    }


__all__ = [
    "DecisionRecord",
    "DecisionLogger",
    "summarize_decisions",
]
