"""v9_pyramiding_engine — adaptateur facteur-taille sur convergence de principes.

Chantier 2 du « saut quantique agressif » (2026-07-18, recadré motion CEO).

**Réutilisation, pas duplication** : le moteur ``PyramidingEngine``
(core/v9/pyramiding_engine.py, Phase 13.2) existe déjà et est câblé dans
``trade_engine.process()``. Ce module ne le réimplémente pas — il :

  1. expose ``compute_pyramiding_factor(...)`` → float ∈ [0.5, 2.0], l'interface
     continue dont le backtest a besoin ;
  2. ajoute la logique que le moteur existant n'a PAS : les paliers de confiance
     (1 principe conf≥80 → ×1.0 ; 2 conf≥70 → ×1.5 ; 3+ conf≥60 → ×2.0) et la
     **réduction sur signaux contradictoires → ×0.5** ;
  3. délègue au moteur existant via ``pyramiding_factor_from_engine`` pour le
     chemin contextuel (confluence MTF, régime, zone_type).

Stdlib pure (R18), additif (R2), fallback conservateur R6 (×1.0 baseline).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

PYRAMIDING_ADAPTER_VERSION = "1.0"

# Bornes du facteur (motion : ×0.5 contradiction … ×2.0 forte convergence).
PYRAMID_FACTOR_MIN = 0.5
PYRAMID_FACTOR_MAX = 2.0
PYRAMID_BASELINE = 1.0

# Paliers (n_convergent, conf_min, facteur).
CONF_TIER_1 = 80.0   # 1 principe fort → baseline
CONF_TIER_2 = 70.0   # 2 principes convergents → ×1.5
CONF_TIER_3 = 60.0   # 3+ principes convergents → ×2.0

FACTOR_TIER_2 = 1.5
FACTOR_TIER_3 = 2.0
FACTOR_CONTRADICTION = 0.5

_LONG = ("haussiere", "long", "buy", "bull", "up")
_SHORT = ("baissiere", "short", "sell", "bear", "down")


def _norm_dir(d: str | None) -> str:
    if not d:
        return "neutre"
    dl = str(d).lower()
    if dl in _LONG:
        return "long"
    if dl in _SHORT:
        return "short"
    return "neutre"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class PyramidingDecision:
    """Décision de pyramiding continue (lecture seule, backtest)."""

    factor: float                       # ∈ [0.5, 2.0]
    n_principles_convergent: int        # principes alignés sur la direction majoritaire
    n_principles_total: int
    direction_majoritaire: str          # "long" | "short" | "neutre"
    contradictory: bool                 # signaux dans les deux directions
    min_conf_convergent: float          # confiance min parmi les convergents
    rationale: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_pyramiding_factor(
    principles_triggered: Sequence[str],
    confidences: Sequence[float],
    phase: str = "",
    *,
    directions: Sequence[str] | None = None,
) -> PyramidingDecision:
    """Facteur de taille ∈ [0.5, 2.0] selon la convergence des principes.

    Args:
        principles_triggered : ids/noms des principes déclenchés.
        confidences : confiances (0-100) parallèles à principles_triggered.
        phase : phase de marché (informatif ; climax pénalise légèrement).
        directions : direction par principe (pour détecter la contradiction).
            Si None, tous supposés même direction (pas de contradiction).

    Règles :
        - contradiction (support significatif dans les 2 sens) → ×0.5
        - ≥3 convergents, conf_min ≥ 60 → ×2.0
        - 2 convergents, conf_min ≥ 70 → ×1.5
        - ≥1 convergent, conf ≥ 80 → ×1.0 (baseline)
        - sinon → baseline (×1.0) si signaux faibles.

    R6 : jamais d'exception — fallback ×1.0.
    """
    try:
        principles = list(principles_triggered or [])
        confs = [float(c) for c in (confidences or [])]
        n_total = len(principles)
        reasons: list[str] = []

        if n_total == 0:
            return PyramidingDecision(
                factor=PYRAMID_BASELINE, n_principles_convergent=0,
                n_principles_total=0, direction_majoritaire="neutre",
                contradictory=False, min_conf_convergent=0.0,
                rationale="no_principle", reasons=["aucun principe → baseline"],
            )

        # Directions normalisées.
        if directions is not None:
            dirs = [_norm_dir(d) for d in directions]
        else:
            dirs = ["long"] * n_total  # supposés alignés

        # Support pondéré par direction (compte des principes non neutres).
        long_confs = [c for d, c in zip(dirs, confs) if d == "long"]
        short_confs = [c for d, c in zip(dirs, confs) if d == "short"]
        n_long, n_short = len(long_confs), len(short_confs)

        # Contradiction : au moins 1 principe de chaque côté (support réel).
        contradictory = n_long >= 1 and n_short >= 1
        if contradictory:
            return PyramidingDecision(
                factor=FACTOR_CONTRADICTION,
                n_principles_convergent=max(n_long, n_short),
                n_principles_total=n_total,
                direction_majoritaire="long" if n_long >= n_short else "short",
                contradictory=True,
                min_conf_convergent=0.0,
                rationale=f"contradiction long={n_long}/short={n_short} → ×0.5",
                reasons=[f"signaux contradictoires ({n_long} long / {n_short} short)"],
            )

        # Direction majoritaire (une seule présente ici hors neutres).
        if n_long >= n_short and n_long > 0:
            direction, conv_confs = "long", long_confs
        elif n_short > 0:
            direction, conv_confs = "short", short_confs
        else:
            # Que des neutres.
            return PyramidingDecision(
                factor=PYRAMID_BASELINE, n_principles_convergent=0,
                n_principles_total=n_total, direction_majoritaire="neutre",
                contradictory=False, min_conf_convergent=0.0,
                rationale="neutral_only", reasons=["principes neutres → baseline"],
            )

        n_conv = len(conv_confs)
        conf_min = min(conv_confs) if conv_confs else 0.0

        factor = PYRAMID_BASELINE
        if n_conv >= 3 and conf_min >= CONF_TIER_3:
            factor = FACTOR_TIER_3
            reasons.append(f"{n_conv} convergents conf≥{CONF_TIER_3} → ×{FACTOR_TIER_3}")
        elif n_conv >= 2 and conf_min >= CONF_TIER_2:
            factor = FACTOR_TIER_2
            reasons.append(f"{n_conv} convergents conf≥{CONF_TIER_2} → ×{FACTOR_TIER_2}")
        elif n_conv >= 1 and max(conv_confs) >= CONF_TIER_1:
            factor = PYRAMID_BASELINE
            reasons.append(f"1 principe conf≥{CONF_TIER_1} → baseline")
        else:
            reasons.append("convergence/conf insuffisante → baseline")

        # Climax : légère prudence (ne dépasse pas le plafond de toute façon).
        if phase == "culmination" and factor > PYRAMID_BASELINE:
            factor = max(PYRAMID_BASELINE, factor - 0.25)
            reasons.append("climax → prudence (-0.25)")

        factor = _clamp(factor, PYRAMID_FACTOR_MIN, PYRAMID_FACTOR_MAX)

        return PyramidingDecision(
            factor=round(factor, 2),
            n_principles_convergent=n_conv,
            n_principles_total=n_total,
            direction_majoritaire=direction,
            contradictory=False,
            min_conf_convergent=round(conf_min, 1),
            rationale=f"n_conv={n_conv} conf_min={round(conf_min,1)} → ×{round(factor,2)}",
            reasons=reasons,
        )
    except Exception:
        return PyramidingDecision(
            factor=PYRAMID_BASELINE, n_principles_convergent=0,
            n_principles_total=0, direction_majoritaire="neutre",
            contradictory=False, min_conf_convergent=0.0,
            rationale="fallback_error", reasons=["erreur → baseline"],
        )


def pyramiding_factor_from_engine(
    arbiter_result: dict, context: dict | None = None,
) -> float:
    """Délègue au ``PyramidingEngine`` existant (confluence MTF, régime, zone).

    Retourne son ``multiplier`` (∈ [1.0, 2.0]) ou 1.0 en cas d'erreur (R6).
    C'est le chemin de « réutilisation » littérale du moteur Phase 13.2.
    """
    try:
        from core.v9.pyramiding_engine import PyramidingEngine
        res = PyramidingEngine().evaluate(arbiter_result, context or {})
        return float(res.get("multiplier", 1.0))
    except Exception:
        return PYRAMID_BASELINE
