"""V10 Multi-TF Confluence Engine — score de confluence pondéré sur 7 TF.

Fusionne le Currency Strength (Phase 1) et le VSA Engine (Phase 2) sur
les 7 timeframes (M1/M5/M15/M30/H1/H4/D1) pour produire un score de
confluence 0-1 par paire, plus le bias dominant et les TF alignés.

Doctrine §6 PHASE 3 plan Edge Fund :
  IN  : { tf : {currency_scores, vsa_states_per_pair, pair_to_track} }
  CALC :
    - Pondération fixe (overridable) :
        D1/H4  = 25 % chacun (50 % total)
        H1/M30 = 15 % chacun (30 % total)
        M15/M5 = 7.5 % chacun (15 % total)
        M1     = 5 %
    - M30 = "bridge" : si M30 bullish ET (M15 bullish OU H1 bullish)
      ET scores devises alignés → boost.
    - Score confluence = somme pondérée des "alignment_per_tf"
      où alignment_per_tf ∈ [0,1] combine :
        * scores devises (rang 1-2 = bon, 6-7 = mauvais)
        * VSA directionnel (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION)
        * état structurel BOS (bonus)
    - Score borné [0, 1] → ≥ 0.85 → A1 (high conviction)
                          → ≥ 0.72 → A2 (medium)
                          → ≥ 0.50 → A3 (low)
                          → sinon NONE
  OUT : ConflSummary dataclass (score, aligned_tfs, dominant_bias,
        m30_bridge_active, audit metadata)

Doctrine V10 : R2 additif pur, R6 fail-open (TF manquant -> poids=0,
               pas d'erreur, log debug), R9 audit (seeds + pondérations
               + tf_used conservés), R10 zéro ordre réel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Pondération par défaut (overridable via overrides)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_TF_WEIGHTS: Dict[str, float] = {
    "D1": 0.25,
    "H4": 0.25,
    "H1": 0.15,
    "M30": 0.15,
    "M15": 0.075,
    "M5": 0.075,
    "M1": 0.05,
}

# M30 joue un rôle de bridge entre M15 (entrée) et H1 (biais)
DEFAULT_BRIDGE_TFS: Tuple[str, str, str] = ("M15", "M30", "H1")

# Seuils de score (intervalles Phase 4)
SCORE_A1_THRESHOLD = 0.85
SCORE_A2_THRESHOLD = 0.72
SCORE_A3_THRESHOLD = 0.50


class ConfBias(str, Enum):
    """Biais directionnel agrégé sur les 7 TF."""

    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"

    def sign(self) -> int:
        return {ConfBias.LONG: +1, ConfBias.SHORT: -1, ConfBias.NONE: 0}[self]


# ─────────────────────────────────────────────────────────────────────
# Dataclass sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class ConflSummary:
    """Résultat confluence pour un couple (pair × timestamp)."""

    symbol: str
    timestamp: str
    pair: str                       # devise de référence (ex "EURUSD")
    direction: str                  # "BUY"/"SELL" anticipé selon bias dominant

    score: float = 0.0              # [0, 1]
    dominant_bias: ConfBias = ConfBias.NONE
    aligned_tfs: Tuple[str, ...] = field(default_factory=tuple)
    misaligned_tfs: Tuple[str, ...] = field(default_factory=tuple)

    m30_bridge_active: bool = False
    m30_bridge_reason: str = ""

    # Contributions par TF pour debug
    contributions: Dict[str, float] = field(default_factory=dict)
    currency_alignment: Dict[str, int] = field(default_factory=dict)

    # Audit
    weights_used: Dict[str, float] = field(default_factory=dict)
    tfs_missing: Tuple[str, ...] = field(default_factory=tuple)
    seed: Optional[int] = None

    def signal_level(self) -> str:
        """A1 / A2 / A3 / NONE selon le score."""
        if self.score >= SCORE_A1_THRESHOLD:
            return "A1"
        if self.score >= SCORE_A2_THRESHOLD:
            return "A2"
        if self.score >= SCORE_A3_THRESHOLD:
            return "A3"
        return "NONE"

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "pair": self.pair,
            "direction": self.direction,
            "score": round(self.score, 4),
            "signal_level": self.signal_level(),
            "dominant_bias": self.dominant_bias.value,
            "aligned_tfs": list(self.aligned_tfs),
            "misaligned_tfs": list(self.misaligned_tfs),
            "m30_bridge_active": self.m30_bridge_active,
            "m30_bridge_reason": self.m30_bridge_reason,
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
            "currency_alignment": dict(self.currency_alignment),
            "audit": {
                "weights_used": {k: round(v, 4) for k, v in self.weights_used.items()},
                "tfs_missing": list(self.tfs_missing),
                "seed": self.seed,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers purs
# ─────────────────────────────────────────────────────────────────────
def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Renormalise les poids pour qu'ils somment à 1.

    Les poids manquants sont traités comme 0 (R6 : TF manquant = pas de voix).
    Les poids négatifs sont clampés à 0 (R10 conservateur).
    """
    cleaned = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return cleaned  # tous zéro (data absente) — laissés tels quels
    return {k: v / total for k, v in cleaned.items()}


def _vsa_directional_signal(vsa_state: Optional[str]) -> int:
    """Renvoie +1 (bullish), -1 (bearish), 0 (neutre) pour un état VSA.

    MARKDOWN/DISTRIBUTION = -1, MARKUP/ACCUMULATION = +1, NEUTRAL/absent = 0.
    """
    if not vsa_state:
        return 0
    s = str(vsa_state).upper()
    if s in ("MARKUP", "ACCUMULATION"):
        return +1
    if s in ("MARKDOWN", "DISTRIBUTION"):
        return -1
    return 0


def _currency_alignment_score(
    currency: str,
    pair: str,
    scores: Dict[str, float],
    ranks: Dict[str, int],
    direction_sign: int,
) -> float:
    """Score [0, 1] d'alignement devise pour une paire et direction donnée.

    Logique :
      - Si on veut BUY (direction_sign=+1) la pair EURUSD :
          EUR doit être fort (rank petit) ET USD faible (rank grand).
      - Si on veut BUY USDJPY :
          USD fort (rank petit) ET JPY faible (rank grand).
      - Combinaison pondérée 60/40 entre deux devises.

    R6 fail-open : si une devise manque dans scores, contribution = 0.5.
    """
    if not scores:
        return 0.5

    # Pour EURUSD : si BUY, on veut EUR rank=1 (top), USD rank=7 (bot)
    pair_l = pair.upper().replace("/", "").replace("_", "")
    if currency.upper() not in pair_l:
        # currency doit être base ou quote de la pair
        return 0.5

    # Identifier base et quote de la paire (heuristique simple)
    base = pair_l[:3]
    quote = pair_l[3:6] if len(pair_l) >= 6 else ""

    def _dev_score(dev: str) -> float:
        """Score dispositif pour la devise `dev` selon direction attendue."""
        if dev not in ranks:
            return 0.5
        r = ranks[dev]
        # rank 1 -> 1.0 (top), rank 7 -> 0.0 (bot)
        n = max(ranks.values()) if ranks else 7
        return max(0.0, min(1.0, (n - r) / max(n - 1, 1)))

    if not base or not quote:
        return _dev_score(currency.upper())

    if direction_sign > 0:
        # BUY : base fort, quote faible
        base_score = _dev_score(base)
        quote_score = 1.0 - _dev_score(quote)
    elif direction_sign < 0:
        # SELL : base faible, quote fort
        base_score = 1.0 - _dev_score(base)
        quote_score = _dev_score(quote)
    else:
        return 0.5

    return 0.6 * base_score + 0.4 * quote_score


def _tf_contribution(
    direction_sign: int,
    vsa_signal: int,
    bos_bull: bool,
    bos_bear: bool,
    currency_alignment: float,
) -> float:
    """Score de contribution d'un TF ∈ [0, 1] (plus c'est aligné, plus c'est haut).

    Pondération interne :
      - 40% : alignment devise (currency_alignment ∈ [0, 1])
      - 35% : VSA directionnel (vsa_signal == direction_sign → 1, sinon 0.2, neutre → 0.5)
      - 25% : BOS aligné avec direction → +0.25, contre → -0.25 (clampé [0, 1])
    """
    if direction_sign == 0:
        return 0.5

    # 1. Currency alignment [0, 1]
    ca_part = max(0.0, min(1.0, currency_alignment))

    # 2. VSA alignment
    if vsa_signal == direction_sign:
        vsa_part = 1.0
    elif vsa_signal == 0:
        vsa_part = 0.5
    else:
        vsa_part = 0.2  # contre-tendance : on pénalise fort

    # 3. BOS alignment
    if direction_sign > 0 and bos_bull:
        bos_part = 1.0
    elif direction_sign < 0 and bos_bear:
        bos_part = 1.0
    elif direction_sign > 0 and bos_bear:
        bos_part = 0.0
    elif direction_sign < 0 and bos_bull:
        bos_part = 0.0
    else:
        bos_part = 0.5

    score = 0.40 * ca_part + 0.35 * vsa_part + 0.25 * bos_part
    return max(0.0, min(1.0, score))


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def compute_confluence(
    symbol: str,
    pair: str,
    timestamp: str,
    *,
    tf_data: Dict[str, Dict],
    tf_weights: Optional[Dict[str, float]] = None,
    bridge_tfs: Optional[Tuple[str, str, str]] = None,
    seed: Optional[int] = None,
) -> ConflSummary:
    """Calcule le score de confluence multi-TF pour un couple.

    Parameters
    ----------
    symbol : ex "EURUSD_m5", utilisé pour audit
    pair   : "EURUSD" (devise base/quote de référence)
    timestamp : ISO 8601 UTC
    tf_data : dict clé tf ∈ {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
              Valeur = {
                 "currency_scores": {c -> float (0-100 percentile)}, # optionnel
                 "currency_ranks": {c -> int rank},                  # optionnel
                 "vsa_state": "MARKUP"/"MARKDOWN"/...,"ACCUMULATION"...,
                 "bos": "BOS_BULL"/"BOS_BEAR"/"NONE",
              }
    tf_weights : override des poids par TF (sinon DEFAULT_TF_WEIGHTS).
    bridge_tfs : TFs du pont M15↔M30↔H1 (sinon default).
    seed : reproductibilité audit R9.

    Returns
    -------
    ConflSummary dataclass, sérialisable via as_dict().

    Doctrine
    --------
    R6 fail-open : un TF manquant se voit attribuer un poids effectif
    nul (poids redistribué au prorata des TFs présents). Si aucun TF
    n'est fourni → score=0, dominant_bias=NONE.
    """
    if bridge_tfs is None:
        bridge_tfs = DEFAULT_BRIDGE_TFS

    # Récupérer poids par défaut et normaliser
    base_weights: Dict[str, float] = dict(tf_weights) if tf_weights else dict(DEFAULT_TF_WEIGHTS)
    weights = _normalize_weights(base_weights)

    # Filtrer TFs réellement fournis
    tfs_provided = set(tf_data.keys())
    tfs_missing = tuple(sorted(set(weights.keys()) - tfs_provided))
    if tfs_missing:
        log.debug("v10_confluence: TFs manquants=%s (redistribution poids)", tfs_missing)

    # ÉTAPE 1 : déterminer direction_sign candidate
    # = agrégation des directions VSA fournies (majority vote pondéré par poids)
    vsa_by_tf: Dict[str, int] = {}
    for tf, d in tf_data.items():
        vsa_state = d.get("vsa_state") if isinstance(d, dict) else None
        vsa_by_tf[tf] = _vsa_directional_signal(vsa_state)

    if vsa_by_tf:
        weighted_sign = sum(
            weights.get(tf, 0) * sgn for tf, sgn in vsa_by_tf.items()
        )
    else:
        weighted_sign = 0.0

    if weighted_sign > 0.05:
        direction_sign = +1
        direction = "BUY"
    elif weighted_sign < -0.05:
        direction_sign = -1
        direction = "SELL"
    else:
        direction_sign = 0
        direction = "WAIT"

    # Si aucune info, fallback sur currency_strength (rang top vs bot)
    if direction_sign == 0:
        # Check si une TF a currency_scores + ranks pour décision
        for tf, d in tf_data.items():
            if not isinstance(d, dict):
                continue
            ranks = d.get("currency_ranks", {})
            if pair:
                # Si la base est top-2 et quote est bot-2 → BUY, inverse → SELL
                pair_l = pair.upper().replace("/", "")
                base = pair_l[:3]
                quote = pair_l[3:6]
                br = ranks.get(base)
                qr = ranks.get(quote)
                if br and qr:
                    if br <= 2 and qr >= 6:
                        direction_sign = +1
                        direction = "BUY"
                        break
                    if br >= 6 and qr <= 2:
                        direction_sign = -1
                        direction = "SELL"
                        break

    # ÉTAPE 2 : contributions par TF
    contributions: Dict[str, float] = {}
    currency_alignment_per_tf: Dict[str, int] = {}
    aligned_tfs: List[str] = []
    misaligned_tfs: List[str] = []

    if direction_sign == 0:
        # Pas de direction détectable
        summary = ConflSummary(
            symbol=symbol,
            timestamp=timestamp,
            pair=pair,
            direction="WAIT",
            score=0.0,
            dominant_bias=ConfBias.NONE,
            aligned_tfs=(),
            misaligned_tfs=(),
            contributions={tf: 0.0 for tf in weights if tf in tf_data},
            currency_alignment={},
            weights_used=weights,
            tfs_missing=tfs_missing,
            seed=seed,
        )
        return summary

    for tf, weight in weights.items():
        if tf not in tf_data:
            continue  # R6 : pas de voix
        d = tf_data[tf]
        if not isinstance(d, dict):
            continue

        vsa_signal = vsa_by_tf.get(tf, 0)
        bos = (d.get("bos") or "NONE").upper()
        bos_bull = bos == "BOS_BULL"
        bos_bear = bos == "BOS_BEAR"

        currency_alignment = _currency_alignment_score(
            currency="",
            pair=pair,
            scores=d.get("currency_scores", {}) or {},
            ranks=d.get("currency_ranks", {}) or {},
            direction_sign=direction_sign,
        )

        c = _tf_contribution(
            direction_sign=direction_sign,
            vsa_signal=vsa_signal,
            bos_bull=bos_bull,
            bos_bear=bos_bear,
            currency_alignment=currency_alignment,
        )

        # Pondéré par le poids du TF
        weighted = c * weight
        contributions[tf] = weighted
        # Mapper la "currency_alignment" pour audit (0-100)
        currency_alignment_per_tf[tf] = int(round(currency_alignment * 100))

        # Aligné si (vsa_signal == direction_sign) ET (bos aligné OU bos=NONE)
        aligned = (vsa_signal == direction_sign) and (
            bos == "NONE" or
            (direction_sign > 0 and bos_bull) or
            (direction_sign < 0 and bos_bear)
        )
        if aligned:
            aligned_tfs.append(tf)
        else:
            misaligned_tfs.append(tf)

    # Score agrégé
    score = sum(contributions.values())  # déjà pondéré

    # ÉTAPE 3 : M30 bridge
    m30_bridge = False
    m30_reason = ""
    m15, m30, h1 = bridge_tfs
    if m15 in tf_data and m30 in tf_data and h1 in tf_data:
        d_m15 = tf_data[m15]
        d_m30 = tf_data[m30]
        d_h1 = tf_data[h1]
        v_m15 = _vsa_directional_signal(
            d_m15.get("vsa_state") if isinstance(d_m15, dict) else None
        )
        v_m30 = _vsa_directional_signal(
            d_m30.get("vsa_state") if isinstance(d_m30, dict) else None
        )
        v_h1 = _vsa_directional_signal(
            d_h1.get("vsa_state") if isinstance(d_h1, dict) else None
        )
        # Bridge : M30 dans la direction, ET (M15 dans la direction OU H1 dans la direction)
        if v_m30 == direction_sign and (v_m15 == direction_sign or v_h1 == direction_sign):
            m30_bridge = True
            m30_reason = (
                f"M30={'OK' if v_m30 == direction_sign else 'KO'} "
                f"M15={'OK' if v_m15 == direction_sign else 'KO'} "
                f"H1={'OK' if v_h1 == direction_sign else 'KO'}"
            )
            # Boost : +0.10 si bridge actif, capped à 1.0
            score = min(1.0, score + 0.10)
            contributions[m30] = contributions.get(m30, 0) + 0.10

    # Biais dominant
    if direction_sign > 0:
        dominant_bias = ConfBias.LONG
    elif direction_sign < 0:
        dominant_bias = ConfBias.SHORT
    else:
        dominant_bias = ConfBias.NONE

    summary = ConflSummary(
        symbol=symbol,
        timestamp=timestamp,
        pair=pair,
        direction=direction,
        score=score,
        dominant_bias=dominant_bias,
        aligned_tfs=tuple(aligned_tfs),
        misaligned_tfs=tuple(misaligned_tfs),
        m30_bridge_active=m30_bridge,
        m30_bridge_reason=m30_reason,
        contributions=contributions,
        currency_alignment=currency_alignment_per_tf,
        weights_used=weights,
        tfs_missing=tfs_missing,
        seed=seed,
    )
    return summary


# ─────────────────────────────────────────────────────────────────────
# API multi-paire (utile pour orchestrateur Phase 4)
# ─────────────────────────────────────────────────────────────────────
def compute_confluence_multi_pair(
    pairs: Iterable[str],
    *,
    timestamp: str,
    tf_data_by_pair: Dict[str, Dict[str, Dict]],
    tf_weights: Optional[Dict[str, float]] = None,
    seed: Optional[int] = None,
) -> Dict[str, ConflSummary]:
    """Compute confluence pour plusieurs paires.

    tf_data_by_pair : { pair : tf_data } où tf_data est comme compute_confluence.

    Returns : { pair : ConflSummary }
    """
    out: Dict[str, ConflSummary] = {}
    for pair in pairs:
        tf_data = tf_data_by_pair.get(pair, {})
        out[pair] = compute_confluence(
            symbol=f"{pair}_conf",
            pair=pair,
            timestamp=timestamp,
            tf_data=tf_data,
            tf_weights=tf_weights,
            seed=seed,
        )
    return out


__all__ = [
    "ConflSummary",
    "ConfBias",
    "compute_confluence",
    "compute_confluence_multi_pair",
    "DEFAULT_TF_WEIGHTS",
    "DEFAULT_BRIDGE_TFS",
    "SCORE_A1_THRESHOLD",
    "SCORE_A2_THRESHOLD",
    "SCORE_A3_THRESHOLD",
    "_normalize_weights",
    "_vsa_directional_signal",
    "_currency_alignment_score",
    "_tf_contribution",
]


# R2 additif (Mission 1 prep)
DEFAULT_TF_WEIGHTS = {'M1':0.05,'M5':0.10,'M15':0.20,'M30':0.20,'H1':0.25,'H4':0.15,'D1':0.05}
DEFAULT_BRIDGE_TFS = ('M15', 'H1')
