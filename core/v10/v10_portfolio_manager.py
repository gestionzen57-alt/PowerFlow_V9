"""V10 Portfolio Manager — corrélations + position sizing (ÉTAPE 8).

Plan HERMES_PLAN_V10 §MODULE 8 :
  - Gestion corrélations devises (max 3 positions simultanées corrélées >0.7)
  - Taille positions basées sur risque (Kelly fractionné ou fixed)
  - Max drawdown journalier → halt trading
  - Output : lot_size, position_id, risk_pct, portfolio_pnl

Doctrine V10 : R2 additif pur (stdlib + math only), R6 fail-open,
R8 paramètres surchargeables, R9 audit sérialisable,
R10 (compute only, aucune exécution réelle).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# Config R8 surchargeable
# ─────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: Dict = {
    "max_correlated_positions": 3,
    "correlation_threshold": 0.7,
    "max_daily_dd_pct": 2.0,
    "kelly_fraction": 0.25,
    "max_position_pct_per_trade": 2.0,
    "max_total_exposure_pct": 6.0,
}

VALID_PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF",
               "AUDUSD", "USDCAD", "NZDUSD")


# ─────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Position:
    """Une position ouverte ou hypothétique."""
    position_id: str = ""
    pair: str = ""
    direction: str = ""   # LONG / SHORT
    lot_size: float = 0.0
    entry_price: float = 0.0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    risk_pct: float = 0.0
    opened_at: str = ""
    status: str = "OPEN"  # OPEN / CLOSED / HALTED

    def as_dict(self) -> Dict:
        return {
            "position_id": self.position_id, "pair": self.pair,
            "direction": self.direction, "lot_size": round(self.lot_size, 4),
            "entry_price": round(self.entry_price, 5),
            "sl_pips": round(self.sl_pips, 1),
            "tp_pips": round(self.tp_pips, 1),
            "risk_pct": round(self.risk_pct, 3),
            "opened_at": self.opened_at, "status": self.status,
        }


@dataclass
class CorrelationMatrix:
    """Matrice de corrélation entre paires."""
    pair_a: str = ""
    pair_b: str = ""
    corr: float = 0.0
    n_observations: int = 0

    def as_dict(self) -> Dict:
        return {"pair_a": self.pair_a, "pair_b": self.pair_b,
                "corr": round(self.corr, 3),
                "n_observations": self.n_observations}


@dataclass
class PortfolioDecision:
    """Décision du portfolio manager pour un nouveau trade."""
    can_enter: bool = False
    pair: str = ""
    direction: str = ""
    lot_size: float = 0.0
    risk_pct: float = 0.0
    blocked_reason: str = ""
    correlated_positions_count: int = 0
    daily_dd_pct: float = 0.0
    portfolio_pnl_pips: float = 0.0
    notes: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "can_enter": self.can_enter,
            "pair": self.pair, "direction": self.direction,
            "lot_size": round(self.lot_size, 4),
            "risk_pct": round(self.risk_pct, 3),
            "blocked_reason": self.blocked_reason,
            "correlated_positions_count": self.correlated_positions_count,
            "daily_dd_pct": round(self.daily_dd_pct, 2),
            "portfolio_pnl_pips": round(self.portfolio_pnl_pips, 1),
            "notes": dict(self.notes),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _parse_pair_returns(closes_a: List[float],
                         closes_b: List[float]) -> Optional[Tuple[float, int]]:
    """Calcule la corrélation de Pearson sur les retours journaliers."""
    if len(closes_a) != len(closes_b) or len(closes_a) < 5:
        return None
    n = len(closes_a)
    returns_a = [(closes_a[i] - closes_a[i - 1]) / closes_a[i - 1]
                 for i in range(1, n) if closes_a[i - 1] != 0]
    returns_b = [(closes_b[i] - closes_b[i - 1]) / closes_b[i - 1]
                 for i in range(1, n) if closes_b[i - 1] != 0]
    if len(returns_a) < 5:
        return None
    ma = sum(returns_a) / len(returns_a)
    mb = sum(returns_b) / len(returns_b)
    cov = sum((returns_a[i] - ma) * (returns_b[i] - mb)
              for i in range(len(returns_a)))
    va = sum((r - ma) ** 2 for r in returns_a)
    vb = sum((r - mb) ** 2 for r in returns_b)
    if va <= 0 or vb <= 0:
        return 0.0, len(returns_a)
    return cov / (va * vb) ** 0.5, len(returns_a)


def compute_correlation_matrix(
    pair_closes: Dict[str, List[float]],
) -> List[CorrelationMatrix]:
    """Matrice symétrique de corrélation entre toutes les paires.
    R6 : paires vides → liste vide, pas de crash."""
    out: List[CorrelationMatrix] = []
    pairs = list(pair_closes.keys())
    seen: set = set()
    for i, pa in enumerate(pairs):
        for j, pb in enumerate(pairs):
            if j <= i:
                continue
            key = tuple(sorted([pa, pb]))
            if key in seen:
                continue
            seen.add(key)
            res = _parse_pair_returns(pair_closes[pa], pair_closes[pb])
            if res is None:
                continue
            corr, n = res
            out.append(CorrelationMatrix(pair_a=pa, pair_b=pb,
                                         corr=corr, n_observations=n))
    return out


def find_correlated_positions(
    pair: str,
    corr_matrix: List[CorrelationMatrix],
    threshold: float,
    positions: List[Position],
) -> int:
    """Nombre de positions ouvertes corrélées >threshold avec `pair`."""
    open_positions = [p for p in positions if p.status == "OPEN" and p.pair != pair]
    if not open_positions:
        return 0
    n = 0
    for cm in corr_matrix:
        if cm.pair_a != pair and cm.pair_b != pair:
            continue
        if abs(cm.corr) < threshold:
            continue
        other = cm.pair_b if cm.pair_a == pair else cm.pair_a
        if any(p.pair == other for p in open_positions):
            n += 1
    return n


def compute_kelly_lot_size(
    capital: float,
    win_prob: float,
    rr_ratio: float,
    *,
    kelly_fraction: float = 0.25,
    max_position_pct: float = 2.0,
) -> float:
    """Kelly fractionné — R8 + R10 (capital protection par fraction).

    Sortie : capital exposé en USD (pas en lots). Le caller
    (evaluate_entry) convertit ensuite en lots standards via le
    sl_pips du trade (1 pip sur paire 4 décimales = 10 USD par
    lot standard de 100_000).
    """
    if capital <= 0 or rr_ratio <= 0 or win_prob <= 0 or win_prob >= 1:
        return 0.0
    edge = win_prob - (1 - win_prob) / rr_ratio
    if edge <= 0:
        return 0.0
    sized = capital * edge / rr_ratio * kelly_fraction
    cap = capital * max_position_pct / 100.0
    return float(min(sized, cap))


# ─────────────────────────────────────────────────────────────────────
# Décision portfolio manager
# ─────────────────────────────────────────────────────────────────────
def evaluate_entry(
    candidate_pair: str,
    candidate_direction: str,
    candidate_sl_pips: float,
    candidate_tp_pips: float,
    *,
    capital: float = 100_000.0,
    win_prob: float = 0.55,
    open_positions: Optional[List[Position]] = None,
    corr_matrix: Optional[List[CorrelationMatrix]] = None,
    daily_pnl_pips: float = 0.0,
    config: Optional[Dict] = None,
) -> PortfolioDecision:
    """Décide si une nouvelle entrée est autorisée (R10 + R7).

    Règle plan :
      1. Si max_daily_dd_pct atteint → blocked (DD halt)
      2. Si > 3 positions simultanées corrélées >0.7 avec la candidate
      3. Kelly fractionné × 0.25, cap 2% capital par trade (R10 capital)
      4. Output : lot_size, risk_pct
    """
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    positions = open_positions or []	
    corrs = corr_matrix or []
    d = PortfolioDecision(pair=candidate_pair, direction=candidate_direction,
                          daily_dd_pct=abs(daily_pnl_pips) if daily_pnl_pips < 0 else 0.0,
                          portfolio_pnl_pips=daily_pnl_pips)

    # 1. Daily DD check
    if d.daily_dd_pct >= cfg["max_daily_dd_pct"]:
        d.can_enter = False
        d.blocked_reason = (
            f"DAILY_DD_HALT (DD={d.daily_dd_pct:.2f}% >= "
            f"{cfg['max_daily_dd_pct']}%)"
        )
        return d

    # 2. Correlated positions count
    d.correlated_positions_count = find_correlated_positions(
        candidate_pair, corrs, cfg["correlation_threshold"], positions,
    )
    if d.correlated_positions_count >= cfg["max_correlated_positions"]:
        d.can_enter = False
        d.blocked_reason = (
            f"TOO_MANY_CORRELATED ({d.correlated_positions_count} >= "
            f"{cfg['max_correlated_positions']})"
        )
        return d

    # 3. Compute lot size via Kelly fractionné (USD → lots)
    if candidate_tp_pips > 0 and candidate_sl_pips > 0:
        rr = candidate_tp_pips / candidate_sl_pips
    else:
        rr = 2.0  # défaut R10
    exposure_usd = compute_kelly_lot_size(
        capital, win_prob, rr,
        kelly_fraction=cfg["kelly_fraction"],
        max_position_pct=cfg["max_position_pct_per_trade"],
    )
    # Conversion USD → lots standards : 1 lot standard de 100_000 unités,
    # 1 pip sur paire 4 décimales = 10 USD. Donc 1 lot expose (sl_pips * 10) USD.
    if candidate_sl_pips > 0:
        d.lot_size = exposure_usd / (candidate_sl_pips * 10.0)
    else:
        d.lot_size = 0.0
    # Risque direct = exposure / capital (cohérence Kelly)
    if capital > 0:
        d.risk_pct = 100.0 * exposure_usd / capital
    d.can_enter = (d.lot_size > 0
                   and d.risk_pct <= cfg["max_position_pct_per_trade"])
    if not d.can_enter and not d.blocked_reason:
        d.blocked_reason = (f"RISK_TOO_HIGH ({d.risk_pct:.2f}% > "
                           f"{cfg['max_position_pct_per_trade']}%)")
    d.notes["win_prob"] = f"{win_prob:.2f}"
    d.notes["rr_ratio"] = f"{rr:.2f}"
    return d


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    "DEFAULT_CONFIG",
    "VALID_PAIRS",
    "Position",
    "CorrelationMatrix",
    "PortfolioDecision",
    "compute_correlation_matrix",
    "find_correlated_positions",
    "compute_kelly_lot_size",
    "evaluate_entry",
]
