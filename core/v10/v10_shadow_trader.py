"""
v10_shadow_trader.py — C11-OPT1 : Shadow Trading (compute-only, R10)

Exécute en parallèle du replay un trade papier live pour valider
les signaux en conditions réelles sans aucun ordre broker.
Fail-open R6 sur toutes les opérations.
"""
from __future__ import annotations

import warnings
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShadowTrade:
    pair: str
    tf: str
    direction: str      # BUY | SELL
    entry: float
    sl: float
    tp: float
    ts: float = field(default_factory=lambda: time.time())
    exit_price: float = 0.0
    pnl: float = 0.0
    status: str = "OPEN"  # OPEN | WIN | LOSS | CANCELLED

    def close(self, price: float) -> None:
        self.exit_price = price
        if self.direction == "BUY":
            self.pnl = price - self.entry
        else:
            self.pnl = self.entry - price
        self.status = "WIN" if self.pnl > 0 else "LOSS"


class ShadowTrader:
    """C11-OPT1 — Registre des trades shadow (compute-only)."""

    def __init__(self) -> None:
        self._trades: list[ShadowTrade] = []

    def open_trade(self, pair: str, tf: str, direction: str,
                   entry: float, sl: float, tp: float) -> ShadowTrade | None:
        try:
            t = ShadowTrade(pair=pair, tf=tf, direction=direction,
                            entry=entry, sl=sl, tp=tp)
            self._trades.append(t)
            return t
        except Exception as e:
            warnings.warn(f"[C11-OPT1] ShadowTrader.open_trade error (fail-open): {e}")
            return None

    def close_trade(self, trade: ShadowTrade, price: float) -> None:
        try:
            trade.close(price)
        except Exception as e:
            warnings.warn(f"[C11-OPT1] ShadowTrader.close_trade error (fail-open): {e}")

    def summary(self) -> dict[str, Any]:
        try:
            closed = [t for t in self._trades if t.status in ("WIN", "LOSS")]
            wins = [t for t in closed if t.status == "WIN"]
            total_pnl = sum(t.pnl for t in closed)
            wr = len(wins) / len(closed) if closed else 0.0
            return {
                "shadow_trades": len(closed),
                "shadow_wins": len(wins),
                "shadow_wr": round(wr, 4),
                "shadow_pnl": round(total_pnl, 4),
                "shadow_open": len([t for t in self._trades if t.status == "OPEN"]),
            }
        except Exception as e:
            warnings.warn(f"[C11-OPT1] ShadowTrader.summary error (fail-open): {e}")
            return {"shadow_trades": 0, "shadow_wr": 0.0, "shadow_pnl": 0.0}
