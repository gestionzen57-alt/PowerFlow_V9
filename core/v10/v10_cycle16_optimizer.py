"""
v10_cycle16_optimizer.py — Cycle 16 Orchestrator
Pipeline : PositionSizer + KellyCriterion + VolatilityScaler +
CorrelationMatrix + ExposureManager → C16Result
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from core.v10.v10_position_sizer import PositionSizer, SizingResult
from core.v10.v10_kelly_criterion import KellyCriterion
from core.v10.v10_volatility_scaler import VolatilityScaler
from core.v10.v10_correlation_matrix import CorrelationMatrix
from core.v10.v10_exposure_manager import ExposureManager


@dataclass
class C16TradeRequest:
    pair: str
    sl_pips: float
    tp_pips: float
    atr_pips: float
    current_atr: float
    historical_pnls: List[float] = field(default_factory=list)
    pair_return: float = 0.0


@dataclass
class C16Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sizing: Optional[dict] = None
    kelly: Optional[dict] = None
    vol_scale: Optional[dict] = None
    exposure_check: Optional[dict] = None
    final_lot: float = 0.0
    approved: bool = False
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "approved": self.approved,
            "final_lot": round(self.final_lot, 4),
            "summary": self.summary,
            "sizing": self.sizing,
            "kelly": self.kelly,
            "vol_scale": self.vol_scale,
            "exposure_check": self.exposure_check,
        }


class C16Optimizer:
    """
    Cycle 16 — Pipeline de sizing & gestion d'exposition.
    1. Kelly criterion depuis historique
    2. Sizing ATR-based
    3. Scaling volatilité
    4. Check exposition + corrélations
    5. Calcul lot final
    """

    def __init__(self, capital: float = 10_000.0) -> None:
        self.sizer = PositionSizer(capital=capital)
        self.kelly = KellyCriterion()
        self.vol_scaler = VolatilityScaler(window=20)
        self.corr_matrix = CorrelationMatrix(window=30)
        self.exposure = ExposureManager()

    def run(self, req: C16TradeRequest) -> C16Result:
        result = C16Result()

        # 1 — Kelly
        kelly_res = self.kelly.from_trades(req.historical_pnls)
        if kelly_res:
            result.kelly = kelly_res.as_dict()
            risk_pct = kelly_res.recommended
        else:
            risk_pct = 0.01

        # 2 — Sizing ATR
        sizing = self.sizer.atr_based(
            pair=req.pair,
            atr_pips=req.atr_pips,
            tp_pips=req.tp_pips,
            risk_pct=risk_pct,
        )
        result.sizing = sizing.as_dict()

        # 3 — Vol scaling
        self.vol_scaler.feed(req.atr_pips)
        vol_scale = self.vol_scaler.scale(req.current_atr)
        result.vol_scale = vol_scale.as_dict()

        # 4 — Corrélation feed
        if req.pair_return != 0.0:
            self.corr_matrix.feed(req.pair, req.pair_return)

        # 5 — Exposition
        projected_exposure = sizing.lot_size * 0.01
        exp_check = self.exposure.check(req.pair, projected_exposure)
        result.exposure_check = exp_check.as_dict()

        # Lot final
        final_lot = round(sizing.lot_size * vol_scale.scale_factor, 2)
        final_lot = max(PositionSizer.MIN_LOT, min(PositionSizer.MAX_LOT, final_lot))

        result.final_lot = final_lot
        result.approved = exp_check.allowed
        result.summary = (
            f"{req.pair} | lot={final_lot} | kelly={risk_pct:.2%} "
            f"| vol={vol_scale.regime} | {'OK' if result.approved else 'BLOCKED: ' + exp_check.reason}"
        )

        return result

    def confirm_open(self, pair: str, lot: float) -> None:
        self.exposure.open_position(pair, lot * 0.01)

    def confirm_close(self, pair: str) -> None:
        self.exposure.close_position(pair)

    def reset(self) -> None:
        self.vol_scaler.reset()
        self.corr_matrix.reset()
        self.exposure.reset()
