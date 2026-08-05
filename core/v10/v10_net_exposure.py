"""V10 Net Exposure — exposition nette par devise + blocage doubles opposées (Sprint 9).

Ferme le trou R10 du portfolio manager : il bloque les positions corrélées
(>0.7, max 3) mais PAS les doubles positions directement opposées ni
l'exposition nette excessive par devise. Ce module additif (R2) :

  1. `compute_net_exposure(positions)` → exposition nette par devise
     (long + / short -, en lots). Empêche l'exposition nette USD > limite.
  2. `find_directly_opposed(candidate, positions)` → True si une position
     ouverte sur la MÊME paire avec la direction OPPOSÉE existe.
  3. `exposure_gate(pair, direction, positions, max_net_by_ccy)` → décision
     R10 : autorise si pas d'opposition directe ET net exposure par devise
     sous la limite.

Paires majeures → (base, quote) : EURUSD=(EUR,USD), GBPUSD=(GBP,USD),
USDJPY=(USD,JPY), USDCHF=(USD,CHF), AUDUSD=(AUD,USD), USDCAD=(USD,CAD),
NZDUSD=(NZD,USD).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 audit, R10.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Paires majeures → (base, quote)
MAJOR_PAIRS: Dict[str, tuple] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"),
}

# Direction → signe (+1 long, -1 short)
DIRECTION_SIGN = {"long": +1, "buy": +1, "short": -1, "sell": -1}


@dataclass
class Position:
    """Position ouverte ou hypothétique (alignée portfolio_manager.Position)."""
    position_id: str = ""
    pair: str = ""
    direction: str = ""       # long/short
    lot_size: float = 0.0
    status: str = "OPEN"      # OPEN/CLOSED

    def as_dict(self) -> Dict:
        return {
            "position_id": self.position_id, "pair": self.pair,
            "direction": self.direction, "lot_size": round(self.lot_size, 4),
            "status": self.status,
        }


@dataclass
class NetExposureResult:
    exposures: Dict[str, float] = field(default_factory=dict)  # ccy → net lots
    total_gross: float = 0.0
    n_positions: int = 0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "exposures": {k: round(v, 4) for k, v in self.exposures.items()},
            "total_gross": round(self.total_gross, 4),
            "n_positions": self.n_positions,
            "audit": dict(self.audit),
        }


@dataclass
class ExposureGate:
    pair: str = ""
    direction: str = ""
    can_enter: bool = True
    blocked_reason: str = ""
    net_exposure: Dict[str, float] = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "direction": self.direction,
            "can_enter": self.can_enter, "blocked_reason": self.blocked_reason,
            "net_exposure": {k: round(v, 4) for k, v in self.net_exposure.items()},
            "audit": dict(self.audit),
        }


def _open_positions(positions: List[Position]) -> List[Position]:
    return [p for p in positions if p.status == "OPEN" and p.pair]


def _split_pair(pair: str) -> Optional[tuple]:
    return MAJOR_PAIRS.get(pair.upper())


def _sign(direction: str) -> int:
    return DIRECTION_SIGN.get(direction.lower(), 0)


def compute_net_exposure(positions: List[Position]) -> NetExposureResult:
    """Exposition nette par devise depuis les positions ouvertes.

    Chaque position long sur (base, quote) : +lot sur base, -lot sur quote.
    short : -lot sur base, +lot sur quote.
    R6 : paire inconnue → ignorée (log warning).
    """
    res = NetExposureResult()
    net: Dict[str, float] = defaultdict(float)
    gross = 0.0
    n = 0
    for p in _open_positions(positions):
        parts = _split_pair(p.pair)
        if parts is None:
            res.audit.setdefault("skipped_pairs", []).append(p.pair)
            continue
        base, quote = parts
        sign = _sign(p.direction)
        if sign == 0:
            res.audit.setdefault("unknown_directions", []).append(p.direction)
            continue
        lot = float(p.lot_size or 0.0)
        net[base] += sign * lot
        net[quote] -= sign * lot
        gross += lot
        n += 1
    res.exposures = dict(net)
    res.total_gross = gross
    res.n_positions = n
    res.audit["computed"] = True
    return res


def find_directly_opposed(candidate_pair: str, candidate_direction: str,
                          positions: List[Position]) -> bool:
    """True si une position ouverte sur la même paire, direction opposée."""
    cpair = candidate_pair.upper()
    csign = _sign(candidate_direction)
    if csign == 0:
        return False
    for p in _open_positions(positions):
        if p.pair.upper() != cpair:
            continue
        if _sign(p.direction) == -csign:
            return True
    return False


def exposure_gate(
    pair: str,
    direction: str,
    positions: List[Position],
    *,
    max_net_by_ccy: float = 5.0,   # lots nets max par devise (R10 levier)
    allow_opposed: bool = False,
) -> ExposureGate:
    """Décision R10 d'entrée sur (pair, direction) compte tenu du portefeuille.

    Bloque si :
      1. Position directement opposée ouverte (sauf allow_opposed=True).
      2. Exposition nette résultante d'une devise > max_net_by_ccy lots.

    R6 fail-open : paire inconnue → can_enter=True (on ne bloque pas sur
    un doute), audit note le skip.
    """
    gate = ExposureGate(pair=pair, direction=direction)

    parts = _split_pair(pair)
    if parts is None:
        gate.audit["reason"] = "unknown_pair_fail_open"
        return gate

    # 1. Double opposée
    if not allow_opposed and find_directly_opposed(pair, direction, positions):
        gate.can_enter = False
        gate.blocked_reason = f"DIRECTLY_OPPOSED {pair} {direction}"
        gate.audit["reason"] = "directly_opposed"
        return gate

    # 2. Exposition nette résultante
    base, quote = parts
    sign = _sign(direction)
    if sign == 0:
        gate.audit["reason"] = "unknown_direction"
        gate.can_enter = False
        gate.blocked_reason = f"UNKNOWN_DIRECTION {direction}"
        return gate

    current = compute_net_exposure(positions)
    gate.net_exposure = dict(current.exposures)

    new_base = current.exposures.get(base, 0.0) + sign * 1.0  # hypothèse 1 lot
    new_quote = current.exposures.get(quote, 0.0) - sign * 1.0

    if abs(new_base) > max_net_by_ccy:
        gate.can_enter = False
        gate.blocked_reason = (
            f"NET_EXPOSURE {base} would be {new_base:.2f} > "
            f"{max_net_by_ccy} lots")
        gate.audit["reason"] = "net_exposure_base"
        return gate
    if abs(new_quote) > max_net_by_ccy:
        gate.can_enter = False
        gate.blocked_reason = (
            f"NET_EXPOSURE {quote} would be {new_quote:.2f} > "
            f"{max_net_by_ccy} lots")
        gate.audit["reason"] = "net_exposure_quote"
        return gate

    gate.audit["reason"] = "ok"
    gate.audit["projected"] = {
        base: round(new_base, 3), quote: round(new_quote, 3),
    }
    return gate


__all__ = [
    "Position",
    "NetExposureResult",
    "ExposureGate",
    "compute_net_exposure",
    "find_directly_opposed",
    "exposure_gate",
    "MAJOR_PAIRS",
]
