"""
v10_live_monitor.py — Cycle 19
Moniteur live : supervision des positions ouvertes, PnL flottant, alertes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class PositionStatus:
    pos_id: str
    pair: str
    direction: str
    lot: float
    entry_price: float
    current_price: float
    floating_pnl: float
    pips: float
    r_multiple: float
    sl: Optional[float]
    tp: Optional[float]

    def as_dict(self) -> dict:
        return {
            "id": self.pos_id,
            "pair": self.pair,
            "direction": self.direction,
            "lot": self.lot,
            "entry": round(self.entry_price, 5),
            "current": round(self.current_price, 5),
            "pnl": round(self.floating_pnl, 2),
            "pips": round(self.pips, 1),
            "r": round(self.r_multiple, 2),
            "sl": self.sl,
            "tp": self.tp,
        }


class LiveMonitor:
    """
    Suit les positions ouvertes et calcule le PnL flottant en temps réel.
    """
    PIP = 0.0001
    PIP_VALUE = 10.0   # USD par pip par lot standard

    def __init__(self) -> None:
        self._positions: Dict[str, dict] = {}
        self._alerts: List[str] = []

    def register_position(self, pos_id: str, pair: str, direction: str,
                          lot: float, entry: float,
                          sl: Optional[float] = None,
                          tp: Optional[float] = None) -> None:
        self._positions[pos_id] = {
            "pair": pair, "direction": direction, "lot": lot,
            "entry": entry, "sl": sl, "tp": tp,
        }

    def update(self, pos_id: str, current_price: float) -> Optional[PositionStatus]:
        pos = self._positions.get(pos_id)
        if not pos:
            return None
        sign = 1 if pos["direction"] == "BUY" else -1
        pips = sign * (current_price - pos["entry"]) / self.PIP
        pnl = pips * self.PIP_VALUE * pos["lot"]
        sl_dist = abs(pos["entry"] - pos["sl"]) / self.PIP if pos["sl"] else 1.0
        r = pips / sl_dist if sl_dist > 0 else 0.0

        # Alertes SL/TP proches
        if pos["sl"] and abs(current_price - pos["sl"]) / self.PIP < 5:
            self._alerts.append(f"SL_NEAR {pos_id} ({pos['pair']}) — 5 pips")
        if pos["tp"] and abs(current_price - pos["tp"]) / self.PIP < 5:
            self._alerts.append(f"TP_NEAR {pos_id} ({pos['pair']}) — 5 pips")

        return PositionStatus(
            pos_id=pos_id, pair=pos["pair"], direction=pos["direction"],
            lot=pos["lot"], entry_price=pos["entry"], current_price=current_price,
            floating_pnl=pnl, pips=pips, r_multiple=r,
            sl=pos["sl"], tp=pos["tp"],
        )

    def close_position(self, pos_id: str) -> None:
        self._positions.pop(pos_id, None)

    def total_floating_pnl(self, prices: Dict[str, float]) -> float:
        total = 0.0
        for pid, pos in self._positions.items():
            price = prices.get(pos["pair"], pos["entry"])
            sign = 1 if pos["direction"] == "BUY" else -1
            pips = sign * (price - pos["entry"]) / self.PIP
            total += pips * self.PIP_VALUE * pos["lot"]
        return total

    def alerts(self) -> List[str]:
        return list(self._alerts)

    def reset(self) -> None:
        self._positions.clear()
        self._alerts.clear()
