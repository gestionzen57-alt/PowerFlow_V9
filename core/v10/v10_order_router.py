"""
v10_order_router.py — Cycle 19
Routage des ordres : validation pré-envoi, queue, retry et log.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone
import uuid


@dataclass
class Order:
    pair: str
    direction: str       # BUY | SELL
    lot: float
    order_type: str      # MARKET | LIMIT | STOP
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = "PENDING"   # PENDING | SENT | FILLED | REJECTED | CANCELLED
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "id": self.order_id,
            "pair": self.pair,
            "direction": self.direction,
            "lot": self.lot,
            "type": self.order_type,
            "price": self.price,
            "sl": self.sl,
            "tp": self.tp,
            "status": self.status,
            "timestamp": self.timestamp,
            "error": self.error,
        }


class OrderRouter:
    """
    Route les ordres avec validation, queue et log d'audit.
    En mode simulation, les ordres sont marqués FILLED immédiatement.
    """
    MAX_LOT = 10.0
    MIN_LOT = 0.01

    def __init__(self, simulation: bool = True) -> None:
        self.simulation = simulation
        self._queue: List[Order] = []
        self._history: List[Order] = []

    def validate(self, order: Order) -> tuple:
        errors = []
        if order.direction not in ("BUY", "SELL"):
            errors.append("invalid_direction")
        if not (self.MIN_LOT <= order.lot <= self.MAX_LOT):
            errors.append(f"lot_out_of_range: {order.lot}")
        if order.order_type not in ("MARKET", "LIMIT", "STOP"):
            errors.append("invalid_order_type")
        if order.order_type != "MARKET" and order.price is None:
            errors.append("price_required_for_non_market")
        return len(errors) == 0, errors

    def submit(self, order: Order) -> Order:
        valid, errors = self.validate(order)
        if not valid:
            order.status = "REJECTED"
            order.error = " | ".join(errors)
            self._history.append(order)
            return order
        self._queue.append(order)
        order.status = "SENT"
        if self.simulation:
            order.status = "FILLED"
        self._history.append(order)
        return order

    def cancel(self, order_id: str) -> bool:
        for o in self._queue:
            if o.order_id == order_id and o.status == "SENT":
                o.status = "CANCELLED"
                return True
        return False

    def pending_orders(self) -> List[Order]:
        return [o for o in self._queue if o.status == "SENT"]

    def history(self) -> List[dict]:
        return [o.as_dict() for o in self._history]

    def reset(self) -> None:
        self._queue.clear()
        self._history.clear()
