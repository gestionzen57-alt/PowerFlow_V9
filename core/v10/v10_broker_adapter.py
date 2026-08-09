"""
v10_broker_adapter.py — Cycle 19
Adaptateur broker abstrait : interface unifiée pour OANDA, MT5, Interactive Brokers.
Mode simulation inclus.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class AccountInfo:
    broker: str
    account_id: str
    balance: float
    equity: float
    margin_used: float
    margin_free: float
    currency: str = "USD"

    def as_dict(self) -> dict:
        return {
            "broker": self.broker,
            "account": self.account_id,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "margin_used": round(self.margin_used, 2),
            "margin_free": round(self.margin_free, 2),
            "currency": self.currency,
        }


class BrokerAdapter:
    """
    Interface unifiée broker. Implémentation simulation par défaut.
    Pour un vrai broker, surcharger les méthodes.
    """

    def __init__(self, broker: str = "SIMULATION", initial_balance: float = 10_000.0) -> None:
        self.broker = broker
        self._balance = initial_balance
        self._equity = initial_balance
        self._open_positions: Dict[str, dict] = {}

    def get_account(self) -> AccountInfo:
        margin_used = sum(p.get("margin", 0) for p in self._open_positions.values())
        return AccountInfo(
            broker=self.broker,
            account_id="SIM-001",
            balance=self._balance,
            equity=self._equity,
            margin_used=margin_used,
            margin_free=self._equity - margin_used,
        )

    def place_order(self, pair: str, direction: str, lot: float,
                    sl: Optional[float] = None, tp: Optional[float] = None,
                    price: Optional[float] = None) -> dict:
        pos_id = f"{pair}_{direction}_{lot}"
        self._open_positions[pos_id] = {
            "pair": pair, "direction": direction, "lot": lot,
            "sl": sl, "tp": tp, "entry": price, "margin": lot * 1000,
        }
        return {"status": "FILLED", "pos_id": pos_id, "broker": self.broker}

    def close_position(self, pos_id: str, pnl: float = 0.0) -> dict:
        if pos_id not in self._open_positions:
            return {"status": "NOT_FOUND", "pos_id": pos_id}
        del self._open_positions[pos_id]
        self._balance += pnl
        self._equity += pnl
        return {"status": "CLOSED", "pos_id": pos_id, "pnl": pnl}

    def get_open_positions(self) -> List[dict]:
        return list(self._open_positions.values())

    def get_price(self, pair: str) -> dict:
        # Simulation : retourne prix fixe
        return {"pair": pair, "bid": 1.10000, "ask": 1.10020, "spread": 0.00020}

    def reset(self) -> None:
        self._open_positions.clear()
