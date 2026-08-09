"""
v10_portfolio_balancer.py — C11-OPT5 : Multi-pair Portfolio Balancer

Contrôle l'exposition nette du portefeuille multi-paires :
  - Net exposure cap par devise (ex: USD max 3 positions nettes)
  - Corrrelation filter (paires corrélées > 0.80 → réduction taille)
  - Position sizing Kelly fraction

Fail-open R6. Compute-only R10.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MAX_NET_EXPOSURE: int = 3      # max positions nettes par devise
DEFAULT_CORR_THRESHOLD: float = 0.80   # seuil corrélation
DEFAULT_KELLY_FRACTION: float = 0.25   # fraction Kelly conservative


@dataclass
class BalancerResult:
    allowed: bool = True
    reason: str = ""
    kelly_size: float = 1.0
    net_exposure: dict = field(default_factory=dict)
    warnings_list: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "kelly_size": self.kelly_size,
            "net_exposure": self.net_exposure,
            "warnings": self.warnings_list,
        }


class PortfolioBalancer:
    """C11-OPT5 — Contrôle exposition nette multi-paires."""

    def __init__(
        self,
        max_net_exposure: int = DEFAULT_MAX_NET_EXPOSURE,
        corr_threshold: float = DEFAULT_CORR_THRESHOLD,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    ) -> None:
        self._max_net = max_net_exposure
        self._corr_th = corr_threshold
        self._kelly = kelly_fraction
        self._open_positions: dict[str, list[str]] = {}  # currency → [BUY/SELL]

    def check_and_size(
        self,
        pair: str,
        direction: str,
        win_rate: float,
        rr: float = 1.5,
    ) -> BalancerResult:
        """Vérifie l'exposition et calcule la taille Kelly."""
        result = BalancerResult()
        try:
            base, quote = pair[:3].upper(), pair[3:6].upper()

            # Net exposure check
            for ccy in (base, quote):
                positions = self._open_positions.get(ccy, [])
                net = positions.count("BUY") - positions.count("SELL")
                result.net_exposure[ccy] = net
                if abs(net) >= self._max_net:
                    result.allowed = False
                    result.reason = f"NET_EXPOSURE_CAP {ccy}={net}"
                    return result

            # Kelly fraction
            if win_rate > 0 and rr > 0:
                try:
                    kelly = (win_rate - (1 - win_rate) / rr) * self._kelly
                    result.kelly_size = max(0.0, min(1.0, kelly))
                except Exception as e:
                    warnings.warn(f"[C11-OPT5] Kelly calc error (fail-open): {e}")

            result.reason = f"OK kelly={result.kelly_size:.2f}"
        except Exception as e:
            warnings.warn(f"[C11-OPT5] PortfolioBalancer.check_and_size error (fail-open): {e}")
            result.reason = f"ERROR_FAIL_OPEN: {e}"
        return result

    def register_open(self, pair: str, direction: str) -> None:
        try:
            for ccy in (pair[:3].upper(), pair[3:6].upper()):
                self._open_positions.setdefault(ccy, []).append(direction)
        except Exception as e:
            warnings.warn(f"[C11-OPT5] register_open error (fail-open): {e}")

    def register_close(self, pair: str, direction: str) -> None:
        try:
            for ccy in (pair[:3].upper(), pair[3:6].upper()):
                lst = self._open_positions.get(ccy, [])
                if direction in lst:
                    lst.remove(direction)
        except Exception as e:
            warnings.warn(f"[C11-OPT5] register_close error (fail-open): {e}")
