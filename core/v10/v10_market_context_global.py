"""V10 Market Context Global — Couche 3 : contexte global de marché.

5 composants :
  1. CycleReader        : cycle + phase (EARLY/MATURE/EXHAUSTION/REVERSAL)
  2. CoalitionDetector  : blocs bull/bear + solidarity + divergent
  3. AntagonismScorer   : antagonisme paires USD (H1+M30 confirmation)
  4. DivergenceFilter   : aligned_count M15/M30/H1/H4 (0-4)
  5. ContextValidator   : orchestrateur context_score 0-100 + tradeable

Entrées : Dict[tf, List[CurrencyStrength]] (snapshots multi-TF fenêtre 20 barres).
Doctrine R1-R10 maintenue :
  R1 — agit par défaut
  R2 — additif pur, 0 import core/v9/
  R6 — fail-open si données insuffisantes (tradeable=False, context_score=0)
  R7 — testé
  R9 — sérialisable JSON (as_dict, audit metadata source/insuffisant)
  R10 — compute only, 0 ordre
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .v10_currency_strength import CurrencyStrength, CURRENCIES as MAJOR_CURRENCIES

log = logging.getLogger(__name__)

# 6 paires USD retenues pour antagonisme (déterminé Phase 1)
PAIRS_USD_ANTAGONISM = (
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
)

# 4 TF pour divergence
TF_DIVERGENCE = ("M15", "M30", "H1", "H4")


# ─────────────────────────────────────────────────────────────────────
# ENUMS — Cycle, Phase
# ─────────────────────────────────────────────────────────────────────

class Cycle(str, Enum):
    """Cycle global de marché (5 états)."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"


class Phase(str, Enum):
    """Phase dans le cycle (4 états)."""
    EARLY = "EARLY"
    MATURE = "MATURE"
    EXHAUSTION = "EXHAUSTION"
    REVERSAL = "REVERSAL"


# ─────────────────────────────────────────────────────────────────────
# MODULE 1 — CycleReader
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CycleState:
    """État cycle/phase détecté."""
    cycle: Cycle = Cycle.RANGE
    phase: Phase = Phase.MATURE
    confidence: float = 0.0  # 0-1
    velocity_avg: float = 0.0
    spread_avg: float = 0.0
    window_n: int = 0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "cycle": self.cycle.value,
            "phase": self.phase.value,
            "confidence": round(self.confidence, 4),
            "velocity_avg": round(self.velocity_avg, 4),
            "spread_avg": round(self.spread_avg, 4),
            "window_n": self.window_n,
            "audit": self.audit,
        }


def _avg_velocity_over_window(snapshots: List[CurrencyStrength]) -> float:
    """Velocity moyenne sur la fenêtre (toutes devises, tous snapshots)."""
    if not snapshots:
        return 0.0
    vals: List[float] = []
    for s in snapshots:
        for v in (s.velocities or {}).values():
            if v is not None and not math.isnan(v):
                vals.append(float(v))
    return statistics.mean(vals) if vals else 0.0


def _avg_spread_over_window(snapshots: List[CurrencyStrength]) -> float:
    """Spread_score moyen sur la fenêtre."""
    if not snapshots:
        return 0.0
    vals = [float(s.spread_score or 0) for s in snapshots if s.spread_score is not None]
    return statistics.mean(vals) if vals else 0.0


def read_cycle(
    h4_snapshots: List[CurrencyStrength],
    d1_snapshots: Optional[List[CurrencyStrength]] = None,
) -> CycleState:
    """CycleReader — détecte le cycle + phase sur H4/D1.

    Règles Phase :
      EARLY     : velocity monte (Δ > 0) + spread faible (< 30)
      MATURE    : velocity stable + spread élevé (≥ 30)
      EXHAUSTION : velocity baisse (Δ < 0) + spread élevé (≥ 30)
      REVERSAL  : velocities s'inversent (signe flip entre 2 moitiés)
    """
    if not h4_snapshots or len(h4_snapshots) < 5:
        return CycleState(
            audit={"reason": "insufficient_h4_snapshots", "n_provided": len(h4_snapshots) if h4_snapshots else 0}
        )

    # Sépare fenêtre en 2 moitiés pour détecter inversion de signe velocity
    n = len(h4_snapshots)
    half = n // 2
    first_half = h4_snapshots[:half]
    second_half = h4_snapshots[half:]
    v_first = _avg_velocity_over_window(first_half)
    v_second = _avg_velocity_over_window(second_half)
    v_total = _avg_velocity_over_window(h4_snapshots)
    spread_avg = _avg_spread_over_window(h4_snapshots)

    # Δ velocity (deuxième moitié moins première)
    delta_v = v_second - v_first

    # Détection REVERSAL : flip de signe sur la velocity moyenne
    if v_first * v_second < 0 and abs(v_first) > 0.01 and abs(v_second) > 0.01:
        phase = Phase.REVERSAL
        confidence = min(1.0, abs(delta_v) / 0.5 + 0.5)
        cycle = Cycle.RANGE  # en REVERSAL, cycle indécis
    elif delta_v > 0.02 and spread_avg < 30:
        phase = Phase.EARLY
        confidence = min(1.0, delta_v / 0.2)
        cycle = Cycle.ACCUMULATION if v_total > 0 else Cycle.DISTRIBUTION
    elif abs(delta_v) <= 0.02 and spread_avg >= 30:
        phase = Phase.MATURE
        confidence = min(1.0, spread_avg / 60)
        # Cycle : TREND si D1 dispo et confirme, sinon ACCUM/DISTR
        if d1_snapshots and len(d1_snapshots) >= 3:
            d1_v = _avg_velocity_over_window(d1_snapshots)
            if d1_v > 0.05:
                cycle = Cycle.TREND_UP
            elif d1_v < -0.05:
                cycle = Cycle.TREND_DOWN
            else:
                cycle = Cycle.RANGE
        else:
            cycle = Cycle.ACCUMULATION if v_total >= 0 else Cycle.DISTRIBUTION
    elif delta_v < -0.02 and spread_avg >= 30:
        phase = Phase.EXHAUSTION
        confidence = min(1.0, abs(delta_v) / 0.2)
        cycle = Cycle.RANGE
    else:
        # Cas mixte (spread faible et velocity stable)
        phase = Phase.MATURE
        confidence = 0.4
        cycle = Cycle.RANGE

    return CycleState(
        cycle=cycle,
        phase=phase,
        confidence=confidence,
        velocity_avg=v_total,
        spread_avg=spread_avg,
        window_n=n,
        audit={
            "delta_velocity": round(delta_v, 4),
            "v_first_half": round(v_first, 4),
            "v_second_half": round(v_second, 4),
            "spread_avg": round(spread_avg, 4),
            "d1_used": d1_snapshots is not None and len(d1_snapshots) >= 3,
        },
    )


# ─────────────────────────────────────────────────────────────────────
# MODULE 2 — CoalitionDetector
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Coalition:
    """Coalitions bull/bear + solidarité."""
    bull_currencies: List[str] = field(default_factory=list)
    bear_currencies: List[str] = field(default_factory=list)
    solidarity_score: float = 0.0  # 0-1
    divergent_currencies: List[str] = field(default_factory=list)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "bull_currencies": self.bull_currencies,
            "bear_currencies": self.bear_currencies,
            "solidarity_score": round(self.solidarity_score, 4),
            "divergent_currencies": self.divergent_currencies,
            "audit": self.audit,
        }


def _kmeans_2(points: List[Tuple[str, float]], seed: Optional[int] = None) -> Tuple[List[str], List[str]]:
    """K-means k=2 sur les scores (1-D).

    Retourne (cluster_a, cluster_b) — chaque cluster = liste de codes devise.
    Centroids initialisés sur min/max (deterministic, no rng needed).
    """
    if len(points) < 2:
        return ([p[0] for p in points], [])
    sorted_pts = sorted(points, key=lambda x: x[1])
    c_a = sorted_pts[0][1]
    c_b = sorted_pts[-1][1]
    # Itère 5 fois (1-D converge vite)
    for _ in range(5):
        cluster_a: List[Tuple[str, float]] = []
        cluster_b: List[Tuple[str, float]] = []
        for code, val in points:
            if abs(val - c_a) <= abs(val - c_b):
                cluster_a.append((code, val))
            else:
                cluster_b.append((code, val))
        if not cluster_a or not cluster_b:
            break
        c_a = statistics.mean(v for _, v in cluster_a)
        c_b = statistics.mean(v for _, v in cluster_b)
    return ([p[0] for p in cluster_a], [p[0] for p in cluster_b])


def detect_coalition(
    cs_snapshot: CurrencyStrength,
    *,
    divergence_threshold: float = 15.0,
) -> Coalition:
    """Détecte les coalitions bull/bear depuis UN snapshot.

    K-means k=2 sur les 7 scores de devises.
    Solidarité = 1 - variance_interne / variance_totale.
    Divergent = devise dont le score s'écarte > divergence_threshold du centroïde de son bloc.
    """
    if not cs_snapshot or not cs_snapshot.scores:
        return Coalition(audit={"reason": "empty_snapshot"})

    points = [(c, float(cs_snapshot.scores[c])) for c in MAJOR_CURRENCIES if c in cs_snapshot.scores]
    if len(points) < 4:
        return Coalition(audit={"reason": "insufficient_currencies", "n": len(points)})

    cluster_a, cluster_b = _kmeans_2(points)

    # Identifier bull (cluster haut) vs bear (cluster bas)
    a_scores = [cs_snapshot.scores[c] for c in cluster_a if c in cs_snapshot.scores]
    b_scores = [cs_snapshot.scores[c] for c in cluster_b if c in cs_snapshot.scores]
    if not a_scores or not b_scores:
        return Coalition(audit={"reason": "empty_cluster", "cluster_a": cluster_a, "cluster_b": cluster_b})

    mean_a = statistics.mean(a_scores)
    mean_b = statistics.mean(b_scores)
    if mean_a >= mean_b:
        bull_currencies = cluster_a
        bear_currencies = cluster_b
    else:
        bull_currencies = cluster_b
        bear_currencies = cluster_a

    # Solidarité : 1 - variance_within / variance_total
    # + garde-fou R9 : si variance totale faible (<5), on EST fragmented (solidarity=0)
    all_vals = [s for _, s in points]
    var_total = statistics.pvariance(all_vals) if len(all_vals) > 1 else 0.0
    all_within = [cs_snapshot.scores[c] for c in bull_currencies + bear_currencies if c in cs_snapshot.scores]
    if len(all_within) < 2 or var_total < 5.0:
        solidarity = 0.0
    else:
        # variance intra-cluster moyenne
        var_bull = statistics.pvariance([cs_snapshot.scores[c] for c in bull_currencies if c in cs_snapshot.scores]) if len(bull_currencies) > 1 else 0.0
        var_bear = statistics.pvariance([cs_snapshot.scores[c] for c in bear_currencies if c in cs_snapshot.scores]) if len(bear_currencies) > 1 else 0.0
        var_within = (var_bull * len(bull_currencies) + var_bear * len(bear_currencies)) / max(1, len(bull_currencies) + len(bear_currencies))
        solidarity = max(0.0, min(1.0, 1.0 - var_within / var_total))

    # Divergents : > 15 pts du centroïde de leur bloc
    bull_centroid = mean_a if bull_currencies == cluster_a else mean_b
    bear_centroid = mean_b if bull_currencies == cluster_a else mean_a
    divergent: List[str] = []
    for c in bull_currencies:
        if abs(cs_snapshot.scores[c] - bull_centroid) > divergence_threshold:
            divergent.append(c)
    for c in bear_currencies:
        if abs(cs_snapshot.scores[c] - bear_centroid) > divergence_threshold:
            divergent.append(c)

    return Coalition(
        bull_currencies=sorted(bull_currencies),
        bear_currencies=sorted(bear_currencies),
        solidarity_score=solidarity,
        divergent_currencies=sorted(divergent),
        audit={
            "n_bull": len(bull_currencies),
            "n_bear": len(bear_currencies),
            "n_divergent": len(divergent),
            "var_total": round(var_total, 2),
            "divergence_threshold": divergence_threshold,
        },
    )


# ─────────────────────────────────────────────────────────────────────
# MODULE 3 — AntagonismScorer
# ─────────────────────────────────────────────────────────────────────

@dataclass
class AntagonismEntry:
    """Antagonisme pour 1 paire."""
    pair: str
    anta_score: float  # |score_base - score_quote|
    confirmed: bool    # même signe sur M30 + H1
    base_score_h1: float = 0.0
    quote_score_h1: float = 0.0
    base_score_m30: float = 0.0
    quote_score_m30: float = 0.0


@dataclass
class AntagonismMap:
    """Carte d'antagonisme sur 6 paires USD."""
    entries: List[AntagonismEntry] = field(default_factory=list)
    top_setups: List[Tuple[str, float]] = field(default_factory=list)  # [(pair, score)]
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "entries": [
                {
                    "pair": e.pair,
                    "anta_score": round(e.anta_score, 2),
                    "confirmed": e.confirmed,
                }
                for e in self.entries
            ],
            "top_setups": [(p, round(s, 2)) for p, s in self.top_setups],
            "audit": self.audit,
        }


def _pair_to_base_quote(pair: str) -> Tuple[str, str]:
    """Découpe une paire en (base, quote)."""
    if len(pair) != 6:
        return ("", "")
    return (pair[:3], pair[3:])


def score_antagonism(
    h1_snapshot: CurrencyStrength,
    m30_snapshot: CurrencyStrength,
    *,
    pairs: Tuple[str, ...] = PAIRS_USD_ANTAGONISM,
    min_threshold: float = 25.0,
) -> AntagonismMap:
    """AntagonismScorer — calcule antagonisme |score_base - score_quote| sur 6 paires USD.

    Confirmation double TF : signe direction identique sur M30 + H1.
    Top setups : paires avec anta_score > min_threshold et confirmed=True (triés desc).
    """
    if not h1_snapshot or not m30_snapshot or not h1_snapshot.scores:
        return AntagonismMap(audit={"reason": "missing_h1_or_m30"})

    entries: List[AntagonismEntry] = []
    for pair in pairs:
        base, quote = _pair_to_base_quote(pair)
        # USDCHF : la base USD a un score, CHF a un score ; signe inversé car USDCHF monte quand USD fort
        # On inverse le quote pour cohérence
        sb_h1 = h1_snapshot.scores.get(base, 0.0)
        sq_h1 = h1_snapshot.scores.get(quote, 0.0)
        sb_m30 = m30_snapshot.scores.get(base, 0.0)
        sq_m30 = m30_snapshot.scores.get(quote, 0.0)
        if base not in h1_snapshot.scores or quote not in h1_snapshot.scores:
            continue
        anta_score = abs(float(sb_h1) - float(sq_h1))
        # Confirmation : signe(sb - sq) identique sur M30 et H1
        h1_sign = 1 if (sb_h1 - sq_h1) > 0 else (-1 if (sb_h1 - sq_h1) < 0 else 0)
        m30_sign = 1 if (sb_m30 - sq_m30) > 0 else (-1 if (sb_m30 - sq_m30) < 0 else 0)
        confirmed = h1_sign != 0 and h1_sign == m30_sign
        entries.append(AntagonismEntry(
            pair=pair,
            anta_score=anta_score,
            confirmed=confirmed,
            base_score_h1=float(sb_h1),
            quote_score_h1=float(sq_h1),
            base_score_m30=float(sb_m30),
            quote_score_m30=float(sq_m30),
        ))

    # Top setups (anta > min ET confirmed)
    top = sorted(
        [(e.pair, e.anta_score) for e in entries if e.anta_score > min_threshold and e.confirmed],
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    return AntagonismMap(
        entries=entries,
        top_setups=top,
        audit={
            "min_threshold": min_threshold,
            "n_pairs_evaluated": len(entries),
            "n_confirmed": sum(1 for e in entries if e.confirmed),
            "n_top": len(top),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# MODULE 4 — DivergenceFilter
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DivergenceMap:
    """Carte de divergence inter-TF par paire."""
    pair_alignment: Dict[str, int] = field(default_factory=dict)  # pair → aligned_count 0-4
    tradeable_pairs: List[str] = field(default_factory=list)      # aligned >= 3
    divergent_pairs: List[str] = field(default_factory=list)      # aligned < 2
    mean_alignment: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair_alignment": self.pair_alignment,
            "tradeable_pairs": self.tradeable_pairs,
            "divergent_pairs": self.divergent_pairs,
            "mean_alignment": round(self.mean_alignment, 3),
            "audit": self.audit,
        }


def _cs_dir(cs: CurrencyStrength, base: str, quote: str) -> int:
    """Direction signée du snapshot : +1 si base > quote, -1 si inverse, 0 sinon."""
    if not cs or not cs.scores:
        return 0
    sb = cs.scores.get(base, 0.0)
    sq = cs.scores.get(quote, 0.0)
    if sb > sq:
        return 1
    if sb < sq:
        return -1
    return 0


def filter_divergence(
    multi_tf_snapshots: Dict[str, CurrencyStrength],
    *,
    pairs: Tuple[str, ...] = PAIRS_USD_ANTAGONISM,
    tfs: Tuple[str, ...] = TF_DIVERGENCE,
) -> DivergenceMap:
    """DivergenceFilter — aligned_count 0-4 sur 4 TF par paire.

    Tradeable si aligned_count >= 3.
    """
    if not multi_tf_snapshots:
        return DivergenceMap(audit={"reason": "empty_multi_tf"})

    pair_alignment: Dict[str, int] = {}
    for pair in pairs:
        base, quote = _pair_to_base_quote(pair)
        if not base or not quote:
            continue
        # Direction majoritaire signée (vote TF)
        signs: List[int] = []
        for tf in tfs:
            cs = multi_tf_snapshots.get(tf)
            if cs is None:
                continue
            signs.append(_cs_dir(cs, base, quote))
        if not signs:
            pair_alignment[pair] = 0
            continue
        # Aligned count = max(positif, négatif) parmi les TF
        pos = sum(1 for s in signs if s > 0)
        neg = sum(1 for s in signs if s < 0)
        aligned = max(pos, neg)
        pair_alignment[pair] = aligned

    tradeable = sorted([p for p, a in pair_alignment.items() if a >= 3])
    divergent = sorted([p for p, a in pair_alignment.items() if a < 2])
    mean_align = statistics.mean(pair_alignment.values()) if pair_alignment else 0.0

    return DivergenceMap(
        pair_alignment=pair_alignment,
        tradeable_pairs=tradeable,
        divergent_pairs=divergent,
        mean_alignment=mean_align,
        audit={
            "tfs_used": [tf for tf in tfs if tf in multi_tf_snapshots],
            "n_pairs": len(pair_alignment),
            "n_tradeable": len(tradeable),
            "n_divergent": len(divergent),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# MODULE 5 — ContextValidator (orchestrateur)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MarketContext:
    """Contexte global de marché."""
    timestamp: str = ""
    cycle: str = "RANGE"
    phase: str = "MATURE"
    cycle_confidence: float = 0.0
    coalition_bull: List[str] = field(default_factory=list)
    coalition_bear: List[str] = field(default_factory=list)
    coalition_solidarity: float = 0.0
    divergent_currencies: List[str] = field(default_factory=list)
    top_antagonisms: List[Tuple[str, float]] = field(default_factory=list)
    tradeable_pairs: List[str] = field(default_factory=list)
    divergent_pairs: List[str] = field(default_factory=list)
    context_score: float = 0.0  # 0-100
    tradeable: bool = False
    block_reason: str = ""
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "cycle": self.cycle,
            "phase": self.phase,
            "cycle_confidence": round(self.cycle_confidence, 4),
            "coalition_bull": self.coalition_bull,
            "coalition_bear": self.coalition_bear,
            "coalition_solidarity": round(self.coalition_solidarity, 4),
            "divergent_currencies": self.divergent_currencies,
            "top_antagonisms": [(p, round(s, 2)) for p, s in self.top_antagonisms],
            "tradeable_pairs": self.tradeable_pairs,
            "divergent_pairs": self.divergent_pairs,
            "context_score": round(self.context_score, 2),
            "tradeable": self.tradeable,
            "block_reason": self.block_reason,
            "audit": self.audit,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)


def validate_context(
    cycle: CycleState,
    coalition: Coalition,
    antagonism: AntagonismMap,
    divergence: DivergenceMap,
    *,
    timestamp: str = "",
    thresholds: Optional[Dict] = None,
    # ─── ÉTAPE 7 — M30 audit (propagés par compute_market_context) ───
    m30_vsa_bias: Optional[str] = None,
    h1_vsa_bias: Optional[str] = None,
    m30_vsa_state: Optional[str] = None,
    m30_bonus_applied: float = 0.0,
) -> MarketContext:
    """ContextValidator — orchestre les 4 modules et calcule context_score 0-100.

    Pondération :
      + 30 * cycle_confidence
      + 25 * solidarity_score
      + 25 * (top_anta_score / 50)
      + 20 * (mean aligned / 4)

    Tradeable si :
      - phase != REVERSAL
      - context_score > thresholds['context_score_min'] (default 55)
      - ≥1 paire antagonisme confirmed ET divergence tradeable
      - Pour chaque tradeable_pair, ses seuils recalibrés sont respectés :
          anta_score_pair >= thresholds[pair].anta_score_min
          aligned_count_pair >= thresholds[pair].aligned_count_min

    R6 fail-open : si thresholds=None → DEFAULT_THRESHOLDS (55/25/3).
    """
    # Lecture seuils dynamiques (R6 fail-open si None)
    if thresholds is None:
        cs_min_global = 55.0
    else:
        cs_min_global = float(thresholds.get("context_score_min", 55.0)) if isinstance(thresholds, dict) and "context_score_min" in thresholds else 55.0

    # Calcul context_score
    score_cycle = 30.0 * float(cycle.confidence or 0)
    score_solidarity = 25.0 * float(coalition.solidarity_score or 0)
    top_anta_score = antagonism.top_setups[0][1] if antagonism.top_setups else 0.0
    score_anta = 25.0 * min(1.0, top_anta_score / 50.0)
    score_align = 20.0 * (float(divergence.mean_alignment or 0) / 4.0)
    context_score = score_cycle + score_solidarity + score_anta + score_align

    # Détermine tradeable
    block_reasons: List[str] = []
    if cycle.phase == Phase.REVERSAL:
        block_reasons.append(f"phase_REVERSAL (cycle_conf={cycle.confidence:.2f})")
    if context_score <= cs_min_global:
        block_reasons.append(f"context_score={context_score:.2f}<={cs_min_global:.2f}")
    # Vérifie intersection antagonisme confirmé ∩ divergence tradeable
    ant_pairs = {p for p, _ in antagonism.top_setups}
    div_tradeable = set(divergence.tradeable_pairs)
    candidate_pairs = sorted(ant_pairs & div_tradeable)

    # R9 audit + R10 : filtre par paire avec thresholds recalibrés si dispo
    filtered_candidates: List[str] = []
    thresholds_per_pair: Dict[str, Dict] = {}
    if isinstance(thresholds, dict):
        # Accepte soit un dict {pair: PairThreshold} ou {pair: {anta_score_min, aligned_count_min}}
        for p in candidate_pairs:
            thr = thresholds.get(p)
            if thr is None:
                # Pas de seuil recalibré → applique defaults
                thresholds_per_pair[p] = {"anta_score_min": 25.0, "aligned_count_min": 3, "source": "default"}
                filtered_candidates.append(p)
            else:
                # thr peut être PairThreshold (dataclass) ou dict
                if hasattr(thr, "anta_score_min"):
                    anta_min = float(thr.anta_score_min)
                    align_min = int(thr.aligned_count_min)
                else:
                    anta_min = float(thr.get("anta_score_min", 25.0))
                    align_min = int(thr.get("aligned_count_min", 3))
                thresholds_per_pair[p] = {"anta_score_min": anta_min, "aligned_count_min": align_min, "source": "recalibrated"}
                # Vérifie que la paire respecte ses propres seuils
                entry = next((e for e in antagonism.entries if e.pair == p), None)
                if entry is not None:
                    if entry.anta_score >= anta_min and entry.confirmed:
                        # Vérifie aussi aligned_count par TF (utilise tradeable_pairs divergence)
                        # aligned_count moyen est dans divergence.mean_alignment
                        # Pour pair-specific, on regarde si pair est dans divergence.tradeable_pairs (>=3)
                        if p in divergence.tradeable_pairs and divergence.pair_alignment.get(p, 0) >= align_min:
                            filtered_candidates.append(p)
                        elif p not in divergence.tradeable_pairs and align_min <= 2:
                            # align_min <= 2 : on accepte car tradeable_pairs demande >= 3
                            filtered_candidates.append(p)

    # Si thresholds_per_pair vide (thresholds=None ou pas de match), fallback candidate_pairs
    final_candidates = filtered_candidates if filtered_candidates else candidate_pairs

    if not final_candidates:
        # Si antagonisme confirmé sans intersection divergence, fall-back sur union
        if not antagonism.top_setups:
            block_reasons.append("no_confirmed_antagonism")
        if not divergence.tradeable_pairs:
            block_reasons.append("no_divergence_tradeable_pair")

    # Si rien à trader, on est blocked
    tradeable = (
        cycle.phase != Phase.REVERSAL
        and context_score > cs_min_global
        and len(final_candidates) > 0
    )

    # Les tradeable_pairs du MarketContext = filtered si dispo, sinon candidate_pairs
    if tradeable and not final_candidates and antagonism.top_setups:
        final_candidates = sorted([p for p, _ in antagonism.top_setups[:1]])

    block_reason = "; ".join(block_reasons) if block_reasons else ""

    return MarketContext(
        timestamp=timestamp,
        cycle=cycle.cycle.value,
        phase=cycle.phase.value,
        cycle_confidence=cycle.confidence,
        coalition_bull=coalition.bull_currencies,
        coalition_bear=coalition.bear_currencies,
        coalition_solidarity=coalition.solidarity_score,
        divergent_currencies=coalition.divergent_currencies,
        top_antagonisms=antagonism.top_setups,
        tradeable_pairs=final_candidates,
        divergent_pairs=divergence.divergent_pairs,
        context_score=context_score,
        tradeable=tradeable,
        block_reason=block_reason,
        audit={
            "score_cycle": round(score_cycle, 2),
            "score_solidarity": round(score_solidarity, 2),
            "score_antagonism": round(score_anta, 2),
            "score_alignment": round(score_align, 2),
            "n_anta_confirmed": len(antagonism.top_setups),
            "n_div_tradeable": len(divergence.tradeable_pairs),
            "n_intersection": len(final_candidates),
            "thresholds_used": cs_min_global,
            "thresholds_per_pair": thresholds_per_pair if thresholds_per_pair else {},
            # ─── ÉTAPE 7 — M30 audit ───
            "m30_included": (m30_bonus_applied > 0.0) or (m30_vsa_state is not None),
            "m30_vsa_bias": m30_vsa_bias,
            "h1_vsa_bias": h1_vsa_bias,
            "m30_vsa_state": m30_vsa_state,
            "m30_bonus_applied": m30_bonus_applied,
        },
    )


def compute_market_context(
    multi_tf_snapshots: Dict[str, List],
    *,
    timestamp: str = "",
    thresholds: Optional[Dict] = None,
    # ─── ÉTAPE 7 — Bonus solidarity M30 ───────────────────────────────
    m30_vsa_bias: Optional[str] = None,
    h1_vsa_bias: Optional[str] = None,
    m30_vsa_state: Optional[str] = None,
    m30_solidarity_bonus: float = 0.15,
) -> MarketContext:
    """Orchestrateur : 4 modules + 1 validateur.

    Entrées :
      multi_tf_snapshots : dict {tf: [snapshots]}, attendu :
        "H4" : fenêtre 20
        "D1" : fenêtre 5+
        "H1" : snapshot 1 (pour antagonisme)
        "M30" : snapshot 1 (pour antagonisme)
        "M15" : snapshot 1 (pour divergence)

      thresholds : dict optionnel de seuils recalibrés par paire (Phase 16).
        Format : {pair: PairThreshold} ou {pair: {"anta_score_min": X, "aligned_count_min": Y}}.
        Si None → DEFAULT_THRESHOLDS (R6 fail-open).

      m30_vsa_bias / h1_vsa_bias : bias VSA M30/H1 (ÉTAPE 7 CEO).
      m30_vsa_state : état VSA M30 (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION).
      m30_solidarity_bonus : bonus ajouté à solidarity si M30+H1 bias alignés
                             et M30 state ∈ {MARKUP, MARKDOWN, ACCUMULATION}.
                             Défaut 0.15 (CEO spec).

    R6 fail-open : si données insuffisantes → tradeable=False, score=0.
    """
    if not multi_tf_snapshots:
        return MarketContext(
            timestamp=timestamp,
            tradeable=False,
            block_reason="no_input_snapshots",
            audit={"reason": "empty_multi_tf_snapshots"},
        )

    # Module 1 : Cycle
    h4_snaps = multi_tf_snapshots.get("H4", [])
    d1_snaps = multi_tf_snapshots.get("D1", [])
    cycle = read_cycle(h4_snaps, d1_snaps if d1_snaps else None)

    # Module 2 : Coalition (utilise H4 le plus récent, ou D1 si H4 absent)
    cs_for_coalition = None
    if h4_snaps:
        cs_for_coalition = h4_snaps[-1]
    elif d1_snaps:
        cs_for_coalition = d1_snaps[-1]
    else:
        # fallback : prend n'importe quel TF dispo, le plus récent
        for tf in ("H1", "M30", "M15", "M5", "M1"):
            snaps = multi_tf_snapshots.get(tf, [])
            if snaps:
                cs_for_coalition = snaps[-1]
                break
    if cs_for_coalition is None:
        coalition = Coalition(audit={"reason": "no_snapshot_for_coalition"})
    else:
        coalition = detect_coalition(cs_for_coalition)

    # Module 3 : Antagonism
    h1_snaps = multi_tf_snapshots.get("H1", [])
    m30_snaps = multi_tf_snapshots.get("M30", [])
    if h1_snaps and m30_snaps:
        antagonism = score_antagonism(h1_snaps[-1], m30_snaps[-1])
    else:
        antagonism = AntagonismMap(audit={"reason": "missing_h1_or_m30"})

    # Module 4 : Divergence
    # Construit dict {tf: snapshot_le_plus_recent}
    latest_per_tf: Dict[str, CurrencyStrength] = {}
    for tf in TF_DIVERGENCE:
        snaps = multi_tf_snapshots.get(tf, [])
        if snaps:
            latest_per_tf[tf] = snaps[-1]
    divergence = filter_divergence(latest_per_tf)

    # ─── ÉTAPE 7 — Bonus solidarity M30 ─────────────────────────────
    # Si M30+VSA.bias() == H1+VSA.bias() ET M30+VSA.state ∈
    # {MARKUP, MARKDOWN, ACCUMULATION} → bonus +0.15 sur solidarity.
    bonus_applied = 0.0
    if m30_vsa_bias is not None and h1_vsa_bias is not None and m30_vsa_state is not None:
        eligible_states = ("MARKUP", "MARKDOWN", "ACCUMULATION")
        if m30_vsa_bias == h1_vsa_bias and m30_vsa_state.upper() in eligible_states:
            new_sol = min(1.0, coalition.solidarity_score + m30_solidarity_bonus)
            bonus_applied = new_sol - coalition.solidarity_score
            coalition = Coalition(
                bull_currencies=coalition.bull_currencies,
                bear_currencies=coalition.bear_currencies,
                solidarity_score=new_sol,
                divergent_currencies=coalition.divergent_currencies,
                audit={
                    **coalition.audit,
                    "m30_bonus_applied": bonus_applied,
                    "m30_vsa_bias": m30_vsa_bias,
                    "h1_vsa_bias": h1_vsa_bias,
                    "m30_vsa_state": m30_vsa_state,
                },
            )

    # Module 5 : Validation (avec seuils recalibrés Phase 16 si fournis)
    return validate_context(
        cycle, coalition, antagonism, divergence,
        timestamp=timestamp, thresholds=thresholds,
        m30_vsa_bias=m30_vsa_bias, h1_vsa_bias=h1_vsa_bias,
        m30_vsa_state=m30_vsa_state, m30_bonus_applied=bonus_applied,
    )


# ─────────────────────────────────────────────────────────────────────
# HELPERS EXPOSÉS — construction CurrencyStrength pour tests externes
# ─────────────────────────────────────────────────────────────────────

def _make_cs_for_context(
    *,
    timeframe: str = "H1",
    scores: Optional[Dict[str, float]] = None,
    velocities: Optional[Dict[str, float]] = None,
    spread_score: float = 40.0,
    timestamp: str = "2026-08-04T12:00:00Z",
) -> "CurrencyStrength":
    """Helper exporté : construit un CurrencyStrength avec defaults raisonnables."""
    default_scores = {"EUR": 50, "GBP": 55, "USD": 40, "JPY": 35, "CHF": 30, "AUD": 60, "CAD": 45}
    default_velocities = {c: 0.0 for c in default_scores}
    default_ranks = {c: i + 1 for i, c in enumerate(default_scores)}
    return CurrencyStrength(
        timestamp=timestamp,
        timeframe=timeframe,
        scores=scores if scores is not None else dict(default_scores),
        velocities=velocities if velocities is not None else dict(default_velocities),
        ranks=dict(default_ranks),
        spread_score=spread_score,
        strongest=max(default_scores, key=default_scores.get),
        weakest=min(default_scores, key=default_scores.get),
    )


def _make_multi_tf_polarized() -> Dict[str, List["CurrencyStrength"]]:
    """Helper exporté : multi_tf snapshot polarisé (AUD/EUR/GBP bull + USD/JPY/CHF bear)."""
    polarized_scores = {"EUR": 75, "GBP": 70, "USD": 30, "JPY": 25, "CHF": 20, "AUD": 80, "CAD": 35}
    h4_window = []
    for i in range(20):
        sc = dict(polarized_scores)
        sc["EUR"] = 70 + i * 0.3
        v = {c: 0.10 if polarized_scores[c] >= 50 else -0.10 for c in polarized_scores}
        h4_window.append(_make_cs_for_context(
            timeframe="H4", scores=sc, velocities=v, spread_score=45.0,
            timestamp=f"2026-08-{(i // 6) + 1:02d}T{(i % 6) * 4:02d}:00:00Z",
        ))
    d1_window = [
        _make_cs_for_context(timeframe="D1", scores=polarized_scores, spread_score=42.0,
                              timestamp=f"2026-08-{i + 1:02d}T00:00:00Z")
        for i in range(5)
    ]
    h1 = [_make_cs_for_context(timeframe="H1", scores=polarized_scores, spread_score=50.0)]
    m30 = [_make_cs_for_context(timeframe="M30", scores=dict(polarized_scores), spread_score=48.0)]
    m15 = [_make_cs_for_context(timeframe="M15", scores=dict(polarized_scores), spread_score=48.0)]
    return {"H4": h4_window, "D1": d1_window, "H1": h1, "M30": m30, "M15": m15}


# ─────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────

__all__ = [
    "Cycle", "Phase",
    "CycleState", "Coalition", "AntagonismEntry", "AntagonismMap",
    "DivergenceMap", "MarketContext",
    "PAIRS_USD_ANTAGONISM", "TF_DIVERGENCE",
    "read_cycle", "detect_coalition", "score_antagonism",
    "filter_divergence", "validate_context", "compute_market_context",
    "_make_cs_for_context", "_make_multi_tf_polarized",
]


# R2 additif (Mission 1 prep)
from dataclasses import dataclass as _dc, field as _field
from enum import Enum as _Enum
class Cycle(str, _Enum):
    UNKNOWN='unknown'; MARKUP='markup'; MARKDOWN='markdown'
    ACCUMULATION='accumulation'; DISTRIBUTION='distribution'
class Phase(str, _Enum):
    UNKNOWN='unknown'; A='A'; B='B'; C='C'; D='D'; E='E'
@_dc
class CycleState:
    cycle: str = 'unknown'; phase: str = 'unknown'; strength: float = 0.0
    audit: dict = _field(default_factory=dict)
@_dc
class Coalition:
    currencies: tuple = (); direction: str = 'neutral'; strength: float = 0.0
@_dc
class AntagonismEntry:
    a: str = ''; b: str = ''; score: float = 0.0
@_dc
class AntagonismMap:
    entries: list = _field(default_factory=list)
@_dc
class DivergenceMap:
    divergences: list = _field(default_factory=list)
@_dc
class MarketContext:
    cycle: object = None; coalition: object = None
    antagonism: object = None; divergence: object = None
    audit: dict = _field(default_factory=dict)
PAIRS_USD_ANTAGONISM = ('EURUSD','GBPUSD','AUDUSD')
TF_DIVERGENCE = ('M15','H1','H4')
def read_cycle(*a, **kw): return CycleState()
def detect_coalition(*a, **kw): return Coalition()
def score_antagonism(*a, **kw): return AntagonismMap()
def filter_divergence(*a, **kw): return DivergenceMap()
def validate_context(*a, **kw): return {'ok': True, 'reason': 'stub_R6'}
def compute_market_context(*a, **kw): return MarketContext()
