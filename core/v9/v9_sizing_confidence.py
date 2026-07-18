"""v9_sizing_confidence — sizing continu par confiance (Kelly fractionnel).

Chantier 3 du « saut quantique agressif » (2026-07-18, recadré motion CEO).

Remplace le sizing binaire (1.0 / 0.0) par un sizing **continu** proportionnel
à l'edge post-calibration. Formule de Kelly fractionnel :

    f_kelly = p - (1 - p) / R            (R = TP / SL, les "odds")
    size    = clamp(f_kelly · K · (1 - dd_ratio), SIZING_MIN, SIZING_MAX)

où :
    p        = probabilité calibrée (v9_bayesian_predictor.predict)
    K        = fraction de Kelly (0.25 = quart-Kelly, conservateur)
    dd_ratio = drawdown courant / drawdown max (réduit la taille en stress)

Garde-fou (motion CEO) : ``gated=True`` (short hors régime autorisé, cf.
v9_aggressive_strategy.is_short_gated) → taille **0.0** (pas de trade), ce qui
prime sur le plancher [0.3, 2.0].

Réutilise les constantes de ``config`` (KELLY_FRACTION, SIZING_MIN/MAX) —
aucune redéfinition (R2 additif). Stdlib pure (R18), fallback conservateur (R6).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

try:  # R6 — dégradation propre si config indisponible.
    from core.v9 import config as _cfg
    _KELLY_FRACTION = float(getattr(_cfg, "KELLY_FRACTION", 0.25))
    _SIZING_MIN = float(getattr(_cfg, "SIZING_MIN", 0.3))
    _SIZING_MAX = float(getattr(_cfg, "SIZING_MAX", 2.0))
except Exception:  # pragma: no cover - défensif
    _KELLY_FRACTION, _SIZING_MIN, _SIZING_MAX = 0.25, 0.3, 2.0

SIZING_CONFIDENCE_VERSION = "1.0"

# Taille "no trade" — prime sur le plancher SIZING_MIN quand gated/edge nul.
SIZE_NO_TRADE = 0.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class SizingDecision:
    """Décision de sizing continue (lecture seule, backtest)."""

    size: float                 # multiplicateur final ∈ {0.0} ∪ [SIZING_MIN, SIZING_MAX]
    edge: float                 # p·TP - (1-p)·SL (pips espérés)
    p_win: float                # proba calibrée utilisée
    rr_ratio: float             # TP / SL
    raw_kelly: float            # fraction de Kelly brute (peut être négative)
    kelly_fraction: float       # K appliqué
    dd_ratio: float             # drawdown courant / max
    gated: bool                 # True → taille forcée 0
    capped: bool                # True → borne dure atteinte
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def kelly_fraction_raw(p_win: float, rr_ratio: float) -> float:
    """Fraction de Kelly brute : p - (1-p)/R. Peut être négative (edge < 0)."""
    try:
        p = _clamp(float(p_win), 0.0, 1.0)
        r = float(rr_ratio)
        if r <= 0:
            return 0.0
        return p - (1.0 - p) / r
    except (TypeError, ValueError):
        return 0.0


def compute_size(
    p_win: float,
    tp: float,
    sl: float,
    *,
    dd_ratio: float = 0.0,
    kelly_fraction: float | None = None,
    gated: bool = False,
) -> SizingDecision:
    """Calcule la taille continue via Kelly fractionnel.

    Args:
        p_win : probabilité calibrée (0-1).
        tp, sl : cibles en pips (sl > 0).
        dd_ratio : drawdown courant / max (0 = pas de stress, 1 = max).
        kelly_fraction : override de K (défaut config KELLY_FRACTION).
        gated : True (short hors régime) → taille 0.

    Returns:
        SizingDecision. La taille vaut 0.0 si gated OU edge ≤ 0, sinon
        clamp([SIZING_MIN, SIZING_MAX]).
    """
    try:
        K = _KELLY_FRACTION if kelly_fraction is None else float(kelly_fraction)
        p = _clamp(float(p_win), 0.0, 1.0)
        tp_f = float(tp)
        sl_f = float(sl)
        dd = _clamp(float(dd_ratio), 0.0, 1.0)
    except (TypeError, ValueError):
        return SizingDecision(
            size=_SIZING_MIN, edge=0.0, p_win=0.5, rr_ratio=0.0, raw_kelly=0.0,
            kelly_fraction=_KELLY_FRACTION, dd_ratio=0.0, gated=gated,
            capped=True, rationale="fallback_bad_input",
        )

    rr = round(tp_f / sl_f, 4) if sl_f > 0 else 0.0
    edge = round(p * tp_f - (1.0 - p) * sl_f, 3)
    raw = kelly_fraction_raw(p, rr)

    if gated:
        return SizingDecision(
            size=SIZE_NO_TRADE, edge=edge, p_win=round(p, 4), rr_ratio=rr,
            raw_kelly=round(raw, 4), kelly_fraction=K, dd_ratio=round(dd, 4),
            gated=True, capped=False, rationale="gated_no_trade",
        )

    # Edge non favorable → pas de trade (Kelly ≤ 0).
    if raw <= 0:
        return SizingDecision(
            size=SIZE_NO_TRADE, edge=edge, p_win=round(p, 4), rr_ratio=rr,
            raw_kelly=round(raw, 4), kelly_fraction=K, dd_ratio=round(dd, 4),
            gated=False, capped=False, rationale="negative_edge_no_trade",
        )

    target = raw * K * (1.0 - dd)
    size = _clamp(target, _SIZING_MIN, _SIZING_MAX)
    capped = size in (_SIZING_MIN, _SIZING_MAX) and abs(target - size) > 1e-9

    return SizingDecision(
        size=round(size, 4), edge=edge, p_win=round(p, 4), rr_ratio=rr,
        raw_kelly=round(raw, 4), kelly_fraction=K, dd_ratio=round(dd, 4),
        gated=False, capped=capped,
        rationale=f"kelly={round(raw,3)}·K={K}·(1-dd={round(dd,2)})→{round(size,3)}",
    )
