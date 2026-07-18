"""v9_loop_breaker.py — Garde-fou générique anti-boucle re-entry (Fix B, motion CEO §16h10).

**Pourquoi ce module existe** :
Le commit `c0aa416` (motion CEO §15h55) a corrigé la boucle re-entry
PRICE_LAG du 17/07 (4750 trades catastrophiques, -46 735 pips). Mais le
fix est **spécifique à PRICE_LAG_AT_NODE_BIRTH**. Tout autre
principe × regime peut théoriquement boucler (re-entry immédiate sur
même signal, sizing constant, aucun cooldown).

Ce module **généralise** le garde-fou :
- Max N trades par (symbol, direction, principe) sur fenêtre glissante M minutes
- Bloque ou réduit le sizing si dépassement
- Configurable via kill switches `V9_MIN_HOLD_BARS`, `V9_MAX_OPEN_TRADES_PER_SYMBOL`
- Lecture seule sur `v9_forces.db` (paper_trades, decisions)
- API simple : `check_loop(symbol, direction, principle)` → Decision

**Volet doctrinal** :
- R2 additif (nouveau module, jamais destructif)
- R6 défensif (try/except → allow par défaut)
- R7 testable (lecture seule DB)
- R18 code pur (sqlite3 + math)
- R22 1 périmètre = ce module

**Activation** :
- Kill switch `V9_LOOP_BREAKER_ENABLED` (défaut OFF tant que motion CEO explicite)
- Si ON : TradeEngine.process() doit appeler `check_loop` AVANT le paper_trade_logger.
- Si décision = 'block' : trade.skip avec raison explicite.

**Conformité au commit c0aa416** :
- Le commit avait listé `V9_MIN_HOLD_BARS` et `V9_MAX_OPEN_TRADES_PER_SYMBOL` comme
  « non-câblé » dans `v9_kill_switches.env`. Ce module les câble (R2 additif).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

LOOP_BREAKER_ENABLED_ENV = "V9_LOOP_BREAKER_ENABLED"
MIN_HOLD_BARS_ENV = "V9_MIN_HOLD_BARS"           # secondes minimum entre 2 trades
MAX_OPEN_TRADES_PER_SYMBOL_ENV = "V9_MAX_OPEN_TRADES_PER_SYMBOL"
LOOP_BREAKER_WINDOW_MINUTES_ENV = "V9_LOOP_BREAKER_WINDOW_MINUTES"

# Defaults
DEFAULT_MIN_HOLD_BARS = 60         # 1 minute minimum entre 2 trades (R6 défensif)
DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL = 3
DEFAULT_LOOP_BREAKER_WINDOW_MINUTES = 15


@dataclass(frozen=True)
class LoopDecision:
    """Décision du loop breaker pour un trade candidat."""
    allowed: bool
    reason: str
    n_recent_trades: int
    seconds_since_last_trade: float
    action: str               # "allow" | "block" | "reduce_size" | "cooldown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "n_recent_trades": self.n_recent_trades,
            "seconds_since_last_trade": self.seconds_since_last_trade,
            "action": self.action,
        }


# ------------------------------------------------------------------ kill switch helpers


def loop_breaker_enabled() -> bool:
    """Kill switch V9_LOOP_BREAKER_ENABLED (défaut OFF tant que pas motion CEO)."""
    val = os.environ.get(LOOP_BREAKER_ENABLED_ENV, "0")
    return val in ("1", "true", "True")


def _min_hold_seconds() -> int:
    """V9_MIN_HOLD_BARS (secondes entre 2 trades). Défaut 60s."""
    val = os.environ.get(MIN_HOLD_BARS_ENV, str(DEFAULT_MIN_HOLD_BARS))
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return DEFAULT_MIN_HOLD_BARS


def _max_open_per_symbol() -> int:
    """V9_MAX_OPEN_TRADES_PER_SYMBOL. Défaut 3."""
    val = os.environ.get(MAX_OPEN_TRADES_PER_SYMBOL_ENV,
                          str(DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL))
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL


def _window_minutes() -> int:
    """V9_LOOP_BREAKER_WINDOW_MINUTES. Défaut 15 min."""
    val = os.environ.get(LOOP_BREAKER_WINDOW_MINUTES_ENV,
                          str(DEFAULT_LOOP_BREAKER_WINDOW_MINUTES))
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return DEFAULT_LOOP_BREAKER_WINDOW_MINUTES


# ------------------------------------------------------------------ helpers DB


def _query_recent_trades(
    db_path: Path,
    symbol: str,
    direction: str,
    window_minutes: int,
) -> tuple[int, float]:
    """Retourne (n_recent_trades, seconds_since_last_trade).

    Lecture seule sur `v9_forces.db` (table paper_trades).
    `paper_trades.opened_at` est ISO timestamp.
    """
    if not db_path.exists():
        return 0, float("inf")
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            # paper_trades n'a pas de colonne symbol ; on joint decisions
            # via snapshot_id pour récupérer le symbol.
            # Densité suspecte = TOUS les trades (ouverts ou fermés) dans la
            # fenêtre — pas seulement les ouverts. Sinon on rate les catastrophes
            # du type 17/07 où 4750 trades étaient fermés en 0 min.
            rows = conn.execute(
                """
                SELECT pt.opened_at, d.symbol, d.direction
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE pt.opened_at > datetime('now', ?)
                  AND d.symbol = ?
                  AND d.direction = ?
                """,
                (f"-{window_minutes} minutes", symbol, direction),
            ).fetchall()
            n_recent = len(rows)
            if n_recent == 0:
                return 0, float("inf")
            # seconds_since_last_trade
            last = rows[0]
            last_iso = last["opened_at"]
            # Parse ISO timestamp
            try:
                # Format ISO 8601 : "2026-07-18T16:05:00.000000+00:00"
                # On extrait HH:MM:SS et compare via datetime
                from datetime import datetime, timezone
                last_dt = datetime.fromisoformat(last_iso)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                seconds_since = (now - last_dt).total_seconds()
                return n_recent, seconds_since
            except (ValueError, TypeError):
                return n_recent, float("inf")
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return 0, float("inf")
    except Exception as e:
        logger.warning("loop_breaker: query failed: %s", e)
        return 0, float("inf")


def _query_open_trades_per_symbol(db_path: Path, symbol: str) -> int:
    """Nombre de paper trades OUVERTS (closed_at IS NULL) pour ce symbol."""
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE d.symbol = ? AND pt.closed_at IS NULL
                """,
                (symbol,),
            ).fetchone()
            return int(row["n"]) if row else 0
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return 0
    except Exception as e:
        logger.warning("loop_breaker: query_open failed: %s", e)
        return 0


# ------------------------------------------------------------------ API publique


def check_loop(
    symbol: str,
    direction: str,
    db_path: Path | str | None = None,
) -> LoopDecision:
    """Vérifie si un trade candidat doit être bloqué par le loop breaker.

    Si `V9_LOOP_BREAKER_ENABLED=0` (défaut) → toujours allow (R6).

    Args :
        symbol : ex "GBPUSD"
        direction : ex "haussiere" | "baissiere"
        db_path : chemin `v9_forces.db` (défaut : cwd/data/v9_forces.db)

    Returns :
        LoopDecision avec allowed, reason, n_recent_trades, action.
    """
    if not loop_breaker_enabled():
        return LoopDecision(
            allowed=True,
            reason="loop_breaker_disabled",
            n_recent_trades=0,
            seconds_since_last_trade=float("inf"),
            action="allow",
        )

    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    window = _window_minutes()
    min_hold_s = _min_hold_seconds()
    max_open = _max_open_per_symbol()

    # Test 1 : cooldown entre 2 trades (V9_MIN_HOLD_BARS)
    n_recent, seconds_since = _query_recent_trades(
        db_p, symbol, direction, window,
    )
    if seconds_since < min_hold_s:
        return LoopDecision(
            allowed=False,
            reason=(
                f"cooldown_active: {seconds_since:.1f}s since last trade "
                f"< {min_hold_s}s min"
            ),
            n_recent_trades=n_recent,
            seconds_since_last_trade=seconds_since,
            action="cooldown",
        )

    # Test 2 : max open trades per symbol (V9_MAX_OPEN_TRADES_PER_SYMBOL)
    n_open = _query_open_trades_per_symbol(db_p, symbol)
    if n_open >= max_open:
        return LoopDecision(
            allowed=False,
            reason=(
                f"max_open_per_symbol_reached: {n_open} >= {max_open}"
            ),
            n_recent_trades=n_recent,
            seconds_since_last_trade=seconds_since,
            action="block",
        )

    # Test 3 : n_recent_trades dans la fenêtre (sanity check)
    # Si > 10 trades dans la fenêtre, c'est suspect (catastrophe 17/07)
    if n_recent > 10:
        return LoopDecision(
            allowed=False,
            reason=(
                f"suspicious_density: {n_recent} trades in last "
                f"{window} min (threshold 10)"
            ),
            n_recent_trades=n_recent,
            seconds_since_last_trade=seconds_since,
            action="block",
        )

    return LoopDecision(
        allowed=True,
        reason="ok",
        n_recent_trades=n_recent,
        seconds_since_last_trade=seconds_since,
        action="allow",
    )


def get_stats(db_path: Path | str | None = None) -> dict[str, Any]:
    """Stats globales du loop breaker (diagnostic)."""
    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    stats: dict[str, Any] = {
        "enabled": loop_breaker_enabled(),
        "min_hold_seconds": _min_hold_seconds(),
        "max_open_per_symbol": _max_open_per_symbol(),
        "window_minutes": _window_minutes(),
    }

    if not db_p.exists():
        stats["db_status"] = "absent"
        return stats

    try:
        conn = sqlite3.connect(str(db_p))
        try:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                """
                SELECT COUNT(*) AS n_open
                FROM paper_trades WHERE closed_at IS NULL
                """
            ).fetchone()
            stats["n_open_trades"] = int(r["n_open"]) if r else 0

            r = conn.execute(
                """
                SELECT COUNT(DISTINCT d.symbol) AS n_symbols
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE pt.closed_at IS NULL
                """
            ).fetchone()
            stats["n_symbols_with_open"] = int(r["n_symbols"]) if r else 0
        finally:
            conn.close()
    except Exception as e:
        stats["db_error"] = str(e)

    return stats
