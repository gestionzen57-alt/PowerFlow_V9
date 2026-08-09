"""
v10_cycle19_optimizer.py — Cycle 19 Orchestrator
Pipeline live : LiveConnector + OrderRouter + BrokerAdapter + FeedHandler + LiveMonitor
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

from core.v10.v10_live_connector import LiveConnector
from core.v10.v10_order_router import OrderRouter, Order
from core.v10.v10_broker_adapter import BrokerAdapter
from core.v10.v10_feed_handler import FeedHandler, Tick
from core.v10.v10_live_monitor import LiveMonitor


@dataclass
class C19TradeRequest:
    pair: str
    direction: str
    lot: float
    order_type: str = "MARKET"
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None


@dataclass
class C19Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    connection: Optional[dict] = None
    account: Optional[dict] = None
    order: Optional[dict] = None
    position_status: Optional[dict] = None
    feed_snapshot: Optional[dict] = None
    gap_alerts: List[str] = field(default_factory=list)
    monitor_alerts: List[str] = field(default_factory=list)
    success: bool = False

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "success": self.success,
            "connection": self.connection,
            "account": self.account,
            "order": self.order,
            "position": self.position_status,
            "feed": self.feed_snapshot,
            "gap_alerts": self.gap_alerts,
            "monitor_alerts": self.monitor_alerts,
        }


class C19Optimizer:
    """
    Cycle 19 — Pipeline d'exécution live (simulation).
    1. Connexion broker
    2. Récupération compte
    3. Routage ordre
    4. Enregistrement position dans LiveMonitor
    5. Snapshot feed + alertes
    """

    def __init__(self, broker: str = "SIMULATION", capital: float = 10_000.0) -> None:
        self.connector = LiveConnector(broker=broker)
        self.router = OrderRouter(simulation=True)
        self.adapter = BrokerAdapter(broker=broker, initial_balance=capital)
        self.feed = FeedHandler()
        self.monitor = LiveMonitor()

    def run(self, req: C19TradeRequest, ticks: Optional[List[Tick]] = None) -> C19Result:
        result = C19Result()

        # 1 — Connexion
        self.connector.connect()
        result.connection = self.connector.state.as_dict()
        if not self.connector.state.connected:
            return result

        # 2 — Compte
        result.account = self.adapter.get_account().as_dict()

        # 3 — Ordre
        order = Order(
            pair=req.pair, direction=req.direction, lot=req.lot,
            order_type=req.order_type, price=req.price, sl=req.sl, tp=req.tp,
        )
        sent_order = self.router.submit(order)
        result.order = sent_order.as_dict()

        if sent_order.status == "FILLED":
            # 4 — Enregistrement monitor
            entry = req.price or self.adapter.get_price(req.pair)["ask"]
            self.monitor.register_position(
                pos_id=sent_order.order_id, pair=req.pair,
                direction=req.direction, lot=req.lot,
                entry=entry, sl=req.sl, tp=req.tp,
            )
            pos_status = self.monitor.update(sent_order.order_id, entry)
            result.position_status = pos_status.as_dict() if pos_status else None

        # 5 — Feed + alertes
        if ticks:
            for tick in ticks:
                self.feed.on_tick(tick)
        latest = self.feed.latest_tick(req.pair)
        result.feed_snapshot = latest.as_dict() if latest else None
        result.gap_alerts = self.feed.gap_alerts()
        result.monitor_alerts = self.monitor.alerts()
        result.success = sent_order.status == "FILLED"

        return result

    def reset(self) -> None:
        self.connector.reset()
        self.router.reset()
        self.adapter.reset()
        self.feed.reset()
        self.monitor.reset()
