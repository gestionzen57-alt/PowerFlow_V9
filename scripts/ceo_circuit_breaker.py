"""CEO-OPT2 : Circuit-breaker streak agressif.

3 SL consécutifs → pause forcée 2h.
5 SL consécutifs → pause 4h + alerte CEO.
R6 fail-open : si DB inaccessible, laisser passer (jamais bloquer).
R10 : lecture seule sur la DB.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Seuils CEO
STREAK_SOFT = 3    # 3 SL → pause 2h
STREAK_HARD = 5    # 5 SL → pause 4h + alerte
PAUSE_SOFT_H = 2
PAUSE_HARD_H = 4

DB_PATH = Path("data/v10_decisions.db")


@dataclass
class CircuitState:
    is_open: bool               # True = trading bloqué
    streak_count: int           # SL consécutifs actuels
    pause_until: Optional[str]  # ISO UTC
    level: str                  # 'CLEAR' | 'SOFT' | 'HARD'
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "is_open": self.is_open,
            "streak_count": self.streak_count,
            "pause_until": self.pause_until,
            "level": self.level,
            "reason": self.reason,
        }


def check_circuit_breaker(
    db_path: Path = DB_PATH,
    now: Optional[datetime] = None,
) -> CircuitState:
    """Vérifie l'état du circuit-breaker sur les derniers trades.

    R6 fail-open : retourne CLEAR si DB inaccessible.
    R10 : SELECT only.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        if not db_path.exists():
            return CircuitState(
                is_open=False, streak_count=0,
                pause_until=None, level="CLEAR",
                reason="db_not_found — fail-open",
            )

        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            # Derniers 10 trades résolus, ordre chronologique inverse
            rows = conn.execute(
                """
                SELECT result, resolved_at
                FROM shadow_trades
                WHERE result IN ('WIN','LOSS','SL')
                ORDER BY resolved_at DESC
                LIMIT 10
                """
            ).fetchall()
    except Exception:  # noqa: BLE001
        return CircuitState(
            is_open=False, streak_count=0,
            pause_until=None, level="CLEAR",
            reason="db_error — fail-open",
        )

    if not rows:
        return CircuitState(
            is_open=False, streak_count=0,
            pause_until=None, level="CLEAR",
            reason="no_resolved_trades",
        )

    # Compte le streak de SL depuis le dernier trade
    streak = 0
    for row in rows:
        if row["result"] in ("LOSS", "SL"):
            streak += 1
        else:
            break  # WIN interrompt le streak

    if streak >= STREAK_HARD:
        pause_until = (now + timedelta(hours=PAUSE_HARD_H)).isoformat()
        return CircuitState(
            is_open=True, streak_count=streak,
            pause_until=pause_until, level="HARD",
            reason=f"{streak} SL consécutifs — pause {PAUSE_HARD_H}h + alerte CEO",
        )

    if streak >= STREAK_SOFT:
        pause_until = (now + timedelta(hours=PAUSE_SOFT_H)).isoformat()
        return CircuitState(
            is_open=True, streak_count=streak,
            pause_until=pause_until, level="SOFT",
            reason=f"{streak} SL consécutifs — pause {PAUSE_SOFT_H}h",
        )

    return CircuitState(
        is_open=False, streak_count=streak,
        pause_until=None, level="CLEAR",
        reason=f"streak={streak} < seuil SOFT ({STREAK_SOFT})",
    )


__all__ = ["CircuitState", "check_circuit_breaker", "STREAK_SOFT", "STREAK_HARD"]
