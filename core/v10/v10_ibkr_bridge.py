"""V10 IBKR Broker Bridge — Phase H/I : micro-lot live via IBKR REST/IB API.

Doctrine V10 H/I :
  R1 : 7th
-----------the user wants me to continue. Let me check the test results and then proceed with the remaining tasks.

The test output shows 123. NEVER send real orders without V9_EXECUTION_ENABLED==1 (SHADOW/paper mandatory)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# R10 : zero real orders without explicit flag
V9_EXECUTION_ENABLED = False  # Must be explicitly set to True by CEO

# IBKR defaults
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 7497  # 7496 for live, 7497 for paper
IBKR_CLIENT_ID = 10


@dataclass
class IBKRConfig:
    """IBKR connection configuration."""
    host: str = IBKR_HOST
    port: int = IBKR_PORT
    client_id: int = IBKR_CLIENT_ID
    account: str = ""
    readonly: bool = True  # True for paper/simulation


@dataclass
class OrderRequest:
    """Order request from V10 signal pipeline."""
    symbol: str                    # e.g., "EURUSD"
    action: str                    # "BUY" or "SELL"
    quantity: float                # lots (micro-lot = 0.01)
    order_type: str = "MKT"        # MKT, LMT, STP
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"
    outside_rth: bool = False
    signal_id: str = ""            # V10 signal ID for traceability
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OrderResult:
    """Result of order placement."""
    success: bool
    order_id: Optional[str] = None
    filled: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class V10IBKRBridge:
    """IBKR bridge for V10 micro-lot execution (SHADOW by default)."""

    def __init__(self, config: IBKRConfig):
        self.config = config
        self.ib = None
        self.connected = False
        self._orders: dict = {}  # order_id -> OrderResult

    def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway."""
        if self.config.readonly:
            log.info("IBKR Bridge: READONLY mode (paper/simulation)")
        try:
            from ib_insync import IB
            self.ib = IB()
            self.ib.connect(
                self.config.host,
                self.config.port,
                clientId=self.config.client_id,
                readonly=self.config.readonly
            )
            self.connected = True
            log.info(f"IBKR connected: {self.config.host}:{self.config.port}")
            return True
        except Exception as e:
            log.error(f"IBKR connection failed: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from IBKR."""
        if self.ib and self.connected:
            self.ib.disconnect()
            self.connected = False
            log.info("IBKR disconnected")

    def place_order(self, req: OrderRequest) -> OrderResult:
        """Place a micro-lot order (SHADOW by default)."""
        # R10: Never send real orders without V9_EXECUTION_ENABLED
        if not V9_EXECUTION_ENABLED:
            # SHADOW mode: simulate fill
            log.info(f"SHADOW ORDER: {req.action} {req.quantity} {req.symbol}")
            return OrderResult(
                success=True,
                order_id=f"SHADOW_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                filled=req.quantity,
                avg_fill_price=0.0,  # Would need market data
                commission=0.0,
                error="SHADOW mode (V9_EXECUTION_ENABLED=0)"
            )

        if not self.connected:
            return OrderResult(success=False, error="Not connected to IBKR")

        try:
            from ib_insync import Stock, Forex, MarketOrder, LimitOrder, StopOrder

            # Map symbol to IBKR contract
            contract = self._make_contract(req.symbol)

            # Create order
            if req.order_type == "MKT":
                order = MarketOrder(req.action, req.quantity)
            elif req.order_type == "LMT":
                order = LimitOrder(req.action, req.quantity, req.limit_price)
            elif req.order_type == "STP":
                order = StopOrder(req.action, req.quantity, req.stop_price)
            else:
                return OrderResult(success=False, error=f"Unknown order type: {req.order_type}")

            order.outsideRth = req.outside_rth
            order.tif = req.time_in_force

            # Place order
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(0.5)  # Wait for fill

            # Check fill
            if trade.orderStatus.status == "Filled":
                result = OrderResult(
                    success=True,
                    order_id=str(trade.order.orderId),
                    filled=trade.orderStatus.filled,
                    avg_fill_price=trade.orderStatus.avgFillPrice,
                    commission=trade.commissionReport.commission if trade.commissionReport else 0.0
                )
            else:
                result = OrderResult(
                    success=False,
                    order_id=str(trade.order.orderId),
                    error=f"Order status: {trade.orderStatus.status}"
                )

            self._orders[result.order_id] = result
            return result

        except Exception as e:
            log.error(f"IBKR order failed: {e}")
            return OrderResult(success=False, error=str(e))

    def _make_contract(self, symbol: str):
        """Create IBKR contract for forex pair."""
        from ib_insync import Forex
        # IBKR Forex expects 6-char pair like "EURUSD"
        if len(symbol) == 6:
            return Forex(symbol)
        # Fallback for other formats
        return Forex(symbol + "USD")

    def get_account_summary(self) -> dict:
        """Get account summary (equity, margin, etc.)."""
        if not self.connected:
            return {}
        try:
            summary = self.ib.accountSummary()
            return {item.tag: item.value for item in summary}
        except Exception as e:
            log.error(f"Account summary failed: {e}")
            return {}

    def get_positions(self) -> list:
        """Get current positions."""
        if not self.connected:
            return []
        try:
            positions = self.ib.positions()
            return [{
                "symbol": p.contract.symbol,
                "position": p.position,
                "avg_cost": p.avgCost
            } for p in positions]
        except Exception as e:
            log.error(f"Positions failed: {e}")
            return []


def create_ibkr_bridge(
    host: str = IBKR_HOST,
    port: int = IBKR_PORT,
    client_id: int = IBKR_CLIENT_ID,
    account: str = "",
    readonly: bool = True
) -> V10IBKRBridge:
    """Factory for V10IBKRBridge."""
    config = IBKRConfig(host=host, port=port, client_id=client_id, account=account, readonly=readonly)
    bridge = V10IBKRBridge(config)
    return bridge


__all__ = [
    "V10IBKRBridge",
    "IBKRConfig",
    "OrderRequest",
    "OrderResult",
    "create_ibkr_bridge",
    "V9_EXECUTION_ENABLED",
]