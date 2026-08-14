"""V10 VSA Engine — Volume Spread Analysis (Wyckoff).

Reproduit la lecture Wyckoff de Søn sur chaque paire × TF (M1→D1) :
classifie la bougie la plus récente dans 4 états structurels
purs + 5 flags complémentaires (no_demand / no_supply / climax /
test / stopping), avec effort_vs_result comme colonne vertébrale.

Doctrine §5 PHASE 2 plan Edge Fund :
  IN  : barres OHLCV (open, high, low, close, tick_volume) ≥ N.
  CALC :
    - spread (high-low) relatif à ATR(period) → bar narrow / wide / ultra-wide
    - volume relatif à SMA(volume, period) → dry / normal / high / climax
    - effort_vs_result = ratio |close-open| / spread ∈ [0,1]
    - direction implicite = sign(close - open) + contexte Wickler
  OUT : VSAState ∈ {MARKUP, MARKDOWN, ACCUMULATION, DISTRIBUTION, NEUTRAL}
        + flags no_demand / no_supply / climax / test / stopping
        + raison de la classification (audit R9)
        + métadonnées reproductibles (seed, n_bars_used, period)

4 ÉTATS WYCKOFF (définition Søn)
-------------------------------
MARKUP        : close > open, spread wide, volume high    → acheteurs dominent
MARKDOWN      : close < open, spread wide, volume high    → vendeurs dominent
ACCUMULATION  : close ~ open (range étroit), volume high   → acheteurs institutionnels
                                                          absorbent sans pousser
DISTRIBUTION  : close ~ open (range étroit), volume high   → vendeurs institutionnels
                                                          distribuent sans pousser
NEUTRAL       : sinon  (dry volume, range étroit sans conviction, data manquante)

5 FLAGS COMPLÉMENTAIRES
-----------------------
NO_DEMAND     : spread étroit + volume sec + direction haussière   → plus d'acheteurs
NO_SUPPLY     : spread étroit + volume sec + direction baissière  → plus de vendeurs
CLIMAX        : volume ≥ ×climax_mult × SMA(volume)               → potentiel exhaustion
TEST          : retour sur support avec effort bas                 → spring de Wyckoff
STOPPING      : volume climax contre la direction                   → absorption possible

Doctrine V10 :
  R2 additif pur (zéro import core/v9/),
  R6 fail-open (data insuffisante → NEUTRAL + flag data_insufficient=True),
  R7 tests verts (≥8 tests dans tests/test_v10_vsa.py),
  R9 auditable (seed + classification_path + métadonnées sérialisées),
  R10 zéro ordre réel (compute only).

Référentiel : Tom Williams, "The Complete Course on VSA", + AnnieMQ interpretation
              (spread relatif à la range N-period, pas à close).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Énumération des états Wyckoff (4 purs + NEUTRAL)
# ─────────────────────────────────────────────────────────────────────
class VSAState(str, Enum):
    MARKUP = "MARKUP"            # acheteurs dominent (close>open, wide, high vol)
    MARKDOWN = "MARKDOWN"        # vendeurs dominent (close<open, wide, high vol)
    ACCUMULATION = "ACCUMULATION"     # absorption haussière (range étroit, high vol)
    DISTRIBUTION = "DISTRIBUTION"     # distribution baissière (range étroit, high vol)
    NEUTRAL = "NEUTRAL"          # pas de signal (dry, data insuffisante, range)

    def is_directional(self) -> bool:
        return self in (VSAState.MARKUP, VSAState.MARKDOWN)

    def bias(self) -> int:
        """+1 bullish, -1 bearish, 0 neutre (utilisable pour confluence Phase 3)."""
        return {
            VSAState.MARKUP: +1,
            VSAState.MARKDOWN: -1,
            VSAState.ACCUMULATION: +1,
            VSAState.DISTRIBUTION: -1,
            VSAState.NEUTRAL: 0,
        }[self]


# ─────────────────────────────────────────────────────────────────────
# Configuration par défaut (overridable via overrides dict)
# ─────────────────────────────────────────────────────────────────────
DEFAULTS: Dict[str, object] = {
    # Fenêtre pour spread reference (ATR period)
    "spread_lookback": 5,
    # Fenêtre pour SMA volume
    "volume_lookback": 20,
    # Multiplicateur volume relatif : volume > mult * SMA(volume) = high
    "volume_high_mult": 1.5,
    # Multiplicateur climax : volume > mult * SMA(volume) = climax
    "climax_mult": 3.0,
    # Seuils spread relatif (ratio spread / median_spread_lookback)
    "narrow_threshold": 0.5,        # spread < 0.5× → narrow (compression)
    "wide_threshold": 1.5,          # spread > 1.5× → wide (expansion)
    # P3 AUDIT VSA : σ-bands sur le spread (doctrine ATR/20)
    # -0.4σ = narrow, 0.7σ = wide, 1.0σ = very_wide
    "sigma_narrow": -0.4,
    "sigma_wide": 0.7,
    "sigma_very_wide": 1.0,
    # Seuil "range étroit" pour accumulation/distribution (ratio body/spread)
    "doji_threshold": 0.25,         # body < 0.25× spread → quasi-doji
    # Volume "sec" pour no_demand/no_supply : volume < mult * SMA(volume)
    "dry_volume_mult": 0.5,
    # Effort/résultat ratio : si (close-open)/spread < → effort faible
    "test_effort_max": 0.3,         # effort < 30% du spread = "test"
    # P5 AUDIT VSA : close_location seuils (Tom Williams p.47)
    # 0.6 = continuation haute (close dans tiers haut) → valide MARKUP
    # 0.4 = continuation basse (close dans tiers bas) → valide MARKDOWN
    # Entre 0.4 et 0.6 = midrange = NEUTRAL (pas de conviction directionnelle)
    "close_location_markup_min": 0.6,
    "close_location_markdown_max": 0.4,
    # P15 AUDIT VSA : gap detection (open vs close précédent).
    # Un gap haussier > seuil = continuation attendue ; gap baissier = rejet.
    # Seuil = ratio |open - prev_close| / avg_spread_lookback.
    "gap_threshold_ratio": 0.5,
    # Pénurie → neutral
    "min_bars_required": 21,        # EMA standard + sma volume + un peu
    # TF supportés
    "supported_timeframes": ("M1", "M5", "M15", "M30", "H1", "H4", "D1"),
}


# ─────────────────────────────────────────────────────────────────────
# Dataclass sortie — résultat VSA d'une bougie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class VSAEngineState:
    """Résultat VSA pour un (pair × TF × timestamp)."""

    symbol: str
    timestamp: str
    timeframe: str

    state: VSAState = VSAState.NEUTRAL
    """État Wyckoff principal."""

    # Mesures brutes (R9 audit / debug)
    spread: float = 0.0
    spread_relative: float = 0.0       # ratio spread / SMA(spread_lookback)
    volume: float = 0.0
    volume_relative: float = 0.0       # ratio vol / SMA(volume_lookback)
    effort_vs_result: float = 0.0      # |close-open| / spread ∈ [0, 1]
    body_ratio: float = 0.0            # idem
    close_location: float = 0.0         # (close-low)/(high-low) ∈ [0, 1] — VSA p.47 Tom Williams
    direction: int = 0                 # +1 hausse / -1 baisse / 0 doji

    # Flags complémentaires
    no_demand: bool = False
    no_supply: bool = False
    climax: bool = False
    test: bool = False                 # test de Wyckoff (spring / UTAD)
    stopping_volume: bool = False      # absorption contre-tendance
    upthrust: bool = False             # wide+high_vol+direction=+1 mais close bas (piège haussier)
    has_gap: bool = False               # P15 — gap entre open et close précédent (session asiatique)
    gap_bullish: bool = False           # P15 — gap haussier (open > prev_close + seuil)
    gap_bearish: bool = False           # P15 — gap baissier (open < prev_close - seuil)
    data_insufficient: bool = False

    # Chemin de décision (audit R9 — pourquoi cette classification)
    classification_path: List[str] = field(default_factory=list)

    # Métadonnées reproductibilité
    n_bars_used: int = 0
    period: int = 0
    seed: Optional[int] = None

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "state": self.state.value,
            "spread": round(self.spread, 6),
            "spread_relative": round(self.spread_relative, 4),
            "volume": round(self.volume, 2),
            "volume_relative": round(self.volume_relative, 4),
            "effort_vs_result": round(self.effort_vs_result, 4),
            "body_ratio": round(self.body_ratio, 4),
            "close_location": round(self.close_location, 4),
            "direction": self.direction,
            "flags": {
                "no_demand": self.no_demand,
                "no_supply": self.no_supply,
                "climax": self.climax,
                "test": self.test,
                "stopping_volume": self.stopping_volume,
                "upthrust": self.upthrust,
                "has_gap": self.has_gap,
                "gap_bullish": self.gap_bullish,
                "gap_bearish": self.gap_bearish,
                "data_insufficient": self.data_insufficient,
            },
            "classification_path": list(self.classification_path),
            "audit": {
                "n_bars_used": self.n_bars_used,
                "period": self.period,
                "seed": self.seed,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers calcul pur (testables sans dépendance externe)
# ─────────────────────────────────────────────────────────────────────
def _sma(values: List[float], period: int) -> float:
    """Moyenne simple sur les `period` dernières valeurs (0 si insuffisant)."""
    if not values or period <= 0:
        return 0.0
    sample = values[-period:]
    if not sample:
        return 0.0
    return sum(sample) / len(sample)


def _pstdev(values: List[float]) -> float:
    """Écart-type population (n diviseur). Retourne 0.0 si < 2 valeurs.

    P3 AUDIT VSA : helper pour σ-bands sur spread. Stdlib pure, pas de scipy.
    """
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(max(0.0, var))


def _spread(b: dict) -> float:
    """Spread d'une bougie (high - low). Borné à ≥ 0."""
    h, l = float(b["high"]), float(b["low"])
    return max(0.0, h - l)


def _body(b: dict) -> Tuple[float, int]:
    """(|close-open|, direction): direction = +1 si close>open, -1 si close<open, 0 sinon."""
    o, c = float(b["open"]), float(b["close"])
    body = abs(c - o)
    direction = (c > o) - (c < o)
    return body, direction


# ─────────────────────────────────────────────────────────────────────
# Classification pure d'une bougie (input = 1 bar + historique)
# ─────────────────────────────────────────────────────────────────────
def _classify_bar(
    cur: dict,
    prev_bars: List[dict],
    cfg: Dict[str, object],
) -> Tuple[VSAEngineState, List[str]]:
    """Classifie la bougie `cur` selon l'historique `prev_bars`.

    Renvoie (etat, classification_path). Path contient la liste d'étapes
    (utile pour debug et audit R9 — pourquoi ce verdict ?).

    Règles :
      1. Mesure spread / volume / body / direction
      2. Calcule spread_relative (vs SMA spread), volume_relative (vs SMA volume)
      3. Calcule effort_vs_result = body / spread
      4. Détermine flags complémentaires (no_demand/no_supply/climax/test)
      5. Choix état :
         - si climax_volume + wide_spread + direction=+1 → MARKDOWN (selling climax)
           et si direction=-1 + climax → MARKUP (buying climax rare)
         - si wide_spread + high_volume + direction=+1 → MARKUP
         - si wide_spread + high_volume + direction=-1 → MARKDOWN
         - si narrow_spread + high_volume + doji → ACCUMULATION ou DISTRIBUTION
           (direction sign + lookback de support/resistance)
         - sinon → NEUTRAL
      6. Stopping_volume = climax_volume mais contre la direction des 5 précédents
      7. Test = effort_vs_result faible + retest support/résistance récent
    """
    path: List[str] = []
    state = VSAEngineState(
        symbol="", timestamp="", timeframe="",
    )

    cfg_spread_lb = int(cfg.get("spread_lookback", 5))
    cfg_vol_lb = int(cfg.get("volume_lookback", 20))
    cfg_vol_high = float(cfg.get("volume_high_mult", 1.5))
    cfg_climax = float(cfg.get("climax_mult", 3.0))
    cfg_narrow = float(cfg.get("narrow_threshold", 0.5))
    cfg_wide = float(cfg.get("wide_threshold", 1.5))
    cfg_doji = float(cfg.get("doji_threshold", 0.25))
    cfg_dry = float(cfg.get("dry_volume_mult", 0.5))
    cfg_test_eff = float(cfg.get("test_effort_max", 0.3))

    # -- 1. Mesure de la bougie courante
    spread = _spread(cur)
    body, direction = _body(cur)
    volume = float(cur.get("tick_volume", 0.0) or 0.0)
    path.append(f"spread={spread:.6f} body={body:.6f} direction={direction:+d} volume={volume:.0f}")

    if spread <= 0:
        # Bougie plate / doji parfait : classement différé
        path.append("spread=0 → NEUTRAL par défaut (bougie plate)")
        state.state = VSAState.NEUTRAL
        state.data_insufficient = True
        state.classification_path = path
        return state, path

    # -- 2. Mesures relatives (vs SMA lookback)
    if not prev_bars or len(prev_bars) < cfg_spread_lb:
        path.append("prev_bars insuffisant → NEUTRAL fail-open")
        state.state = VSAState.NEUTRAL
        state.data_insufficient = True
        state.spread = spread
        state.body_ratio = body / spread
        state.direction = direction
        state.volume = volume
        state.classification_path = path
        return state, path

    spreads_prev = [_spread(b) for b in prev_bars[-cfg_spread_lb:]]
    avg_spread = _sma(spreads_prev, cfg_spread_lb)
    spread_relative = spread / avg_spread if avg_spread > 0 else 1.0
    # P3 AUDIT VSA : σ-bands sur le spread (ATR/20 doctrine réf).
    # σ-bands sont moins sensibles aux outliers que les ratios vs SMA :
    # -0.4σ = narrow, 0.7σ = wide, 1.0σ = very_wide.
    # On garde le ratio en fallback (R6 backward compat) si std=0 (cas dégénéré).
    std_spread = _pstdev(spreads_prev) if len(spreads_prev) > 1 else 0.0
    spread_sigma = (spread - avg_spread) / std_spread if std_spread > 1e-12 else 0.0
    sigma_narrow_th = float(cfg.get("sigma_narrow", -0.4))
    sigma_wide_th = float(cfg.get("sigma_wide", 0.7))
    sigma_very_wide_th = float(cfg.get("sigma_very_wide", 1.0))
    path.append(
        f"avg_spread[{cfg_spread_lb}]={avg_spread:.6f} std={std_spread:.6f} → "
        f"spread_relative={spread_relative:.3f} spread_sigma={spread_sigma:+.3f}"
    )

    vols_prev = [float(b.get("tick_volume", 0.0) or 0.0) for b in prev_bars[-cfg_vol_lb:]]
    avg_volume = _sma(vols_prev, cfg_vol_lb)
    volume_relative = volume / avg_volume if avg_volume > 0 else 1.0
    path.append(f"avg_volume[{cfg_vol_lb}]={avg_volume:.0f} → volume_relative={volume_relative:.3f}")

    body_ratio = body / spread if spread > 0 else 0.0
    effort_vs_result = body_ratio
    # VSA p.47 Tom Williams : close_location = (close-low)/(high-low) ∈ [0,1]
    # Combine effort (body_ratio) + résultat (close_location) pour Effort/Résultat.
    # 0.0 = close au low, 0.5 = mid, 1.0 = close au high.
    close_location = (float(cur["close"]) - float(cur["low"])) / spread if spread > 0 else 0.0
    # Bornage [0,1] (sécurité)
    close_location = max(0.0, min(1.0, close_location))

    # -- 3. Flags globaux (calculés une fois, dépendants de la combinaison)
    # P3 AUDIT VSA : σ-bands PRIMAIRE, ratio FALLBACK (si std=0 → dégénéré).
    # σ-bands sont moins sensibles aux outliers et conformes à la doctrine.
    if std_spread > 1e-12:
        is_wide = spread_sigma >= sigma_wide_th
        is_narrow = spread_sigma <= sigma_narrow_th
        is_very_wide = spread_sigma >= sigma_very_wide_th
    else:
        # Fallback ratio (R6 backward compat, séries sans variance)
        is_wide = spread_relative >= cfg_wide
        is_narrow = spread_relative <= cfg_narrow
        is_very_wide = spread_relative >= cfg_wide * 1.5
    is_high_volume = volume_relative >= cfg_vol_high
    is_climax = volume_relative >= cfg_climax
    is_dry = volume_relative <= cfg_dry
    is_doji = body_ratio <= cfg_doji

    path.append(
        f"flags: wide={is_wide} narrow={is_narrow} high_vol={is_high_volume} "
        f"climax={is_climax} dry={is_dry} doji={is_doji} "
        f"(σ={'%.2f' % spread_sigma if std_spread > 1e-12 else 'n/a'})"
    )

    # -- 4. Effort vs result
    if effort_vs_result <= cfg_test_eff and not is_climax:
        # effort faible mais pas en climax → potentiel test
        if len(prev_bars) >= 2:
            recent_closes = [float(b["close"]) for b in prev_bars[-6:]]
            if recent_closes:
                last_close = float(cur["close"])
                local_hi = max(recent_closes)
                local_lo = min(recent_closes)
                if abs(last_close - local_hi) / max(local_hi, 1e-9) < 0.001:
                    state.test = True
                    path.append("test=high : retest résistance")
                elif abs(last_close - local_lo) / max(local_lo, 1e-9) < 0.001:
                    state.test = True
                    path.append("test=low : retest support")

    # -- 5. État principal — décision
    # P1 AUDIT VSA : close_location (Effort/Résultat) DOIT être validé
    # pour classer MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION. Sans cela, on
    # risque des faux signaux UPTHRUST (large+vol+dir haussière mais close bas).
    # Seuils Tom Williams : 0.6 (continuation haute) / 0.4 (continuation basse).
    cfg_close_loc_high = float(cfg.get("close_location_markup_min", 0.6))
    cfg_close_loc_low = float(cfg.get("close_location_markdown_max", 0.4))
    is_close_high = close_location >= cfg_close_loc_high
    is_close_low = close_location <= cfg_close_loc_low

    final_state: VSAState = VSAState.NEUTRAL

    if is_climax and direction != 0 and avg_volume > 0:
        # Climax = potentiel exhaustion → inversion de polarité
        # Buying climax (direction=-1, volume énorme, wide spread) → MARKDOWN imminent
        # Selling climax (direction=+1, volume énorme, wide spread) → MARKUP imminent
        if direction > 0:
            final_state = VSAState.MARKUP
            path.append(f"CLIMAX + direction=+1 → state={final_state.value}")
        else:
            final_state = VSAState.MARKDOWN
            path.append(f"CLIMAX + direction=-1 → state={final_state.value}")
    elif is_wide and is_high_volume and direction > 0 and is_close_high:
        # P1 : gate close_location >= 0.6 obligatoire pour MARKUP
        final_state = VSAState.MARKUP
        path.append(
            f"wide+high_vol+dir=+1+close_loc={close_location:.2f}>=0.6 → MARKUP "
            f"(spread_rel={spread_relative:.2f}, vol_rel={volume_relative:.2f})"
        )
    elif is_wide and is_high_volume and direction > 0 and not is_close_high:
        # P1 : wide+high_vol+dir haussière mais close bas = UPTHRUST (piège)
        state.upthrust = True
        final_state = VSAState.NEUTRAL
        path.append(
            f"UPTHRUST DETECTED: wide+high_vol+dir=+1 mais close_loc={close_location:.2f}<0.6 → NEUTRAL (piège haussier)"
        )
    elif is_wide and is_high_volume and direction < 0 and is_close_low:
        # P1 : gate close_location <= 0.4 obligatoire pour MARKDOWN
        final_state = VSAState.MARKDOWN
        path.append(
            f"wide+high_vol+dir=-1+close_loc={close_location:.2f}<=0.4 → MARKDOWN "
            f"(spread_rel={spread_relative:.2f}, vol_rel={volume_relative:.2f})"
        )
    elif is_narrow and is_high_volume and is_doji:
        # Range étroit + volume élevé + doji : décision = support/résistance proximité
        if direction >= 0:
            # Prix ne tombe pas malgré volume : absorption haussière
            final_state = VSAState.ACCUMULATION
            path.append(
                f"narrow+high_vol+doji → ACCUMULATION "
                f"(dir={direction:+d}, le prix tient)"
            )
        else:
            final_state = VSAState.DISTRIBUTION
            path.append(
                f"narrow+high_vol+doji → DISTRIBUTION "
                f"(dir={direction:+d}, le prix ne monte pas)"
            )
    elif is_narrow and is_high_volume:
        # P1 AUDIT : narrow+high_vol NON-doji — reclassifier selon close_location.
        # Doctrine réf : close haut + narrow+high_vol = ACCUMULATION (pas MARKUP),
        # close bas = DISTRIBUTION (pas MARKDOWN). Si close midrange → NEUTRAL
        # (pas assez de conviction, on évite le faux signal).
        if is_close_high and direction > 0:
            final_state = VSAState.ACCUMULATION
            path.append(
                f"narrow+high_vol+close_loc={close_location:.2f}>=0.6 → ACCUMULATION "
                f"(pas MARKUP car narrow range = absorption, pas continuation)"
            )
        elif is_close_low and direction < 0:
            final_state = VSAState.DISTRIBUTION
            path.append(
                f"narrow+high_vol+close_loc={close_location:.2f}<=0.4 → DISTRIBUTION"
            )
        else:
            final_state = VSAState.NEUTRAL
            path.append(
                f"narrow+high_vol+close_loc={close_location:.2f} midrange → NEUTRAL "
                f"(pas assez de conviction directionnelle)"
            )
    else:
        final_state = VSAState.NEUTRAL
        path.append("pas de combo decisive → NEUTRAL")

    # -- 6. Flags complémentaires
    if is_dry and direction > 0 and not is_wide:
        state.no_demand = True
        path.append("NO_DEMAND : volume sec + direction haussière sans conviction")
    if is_dry and direction < 0 and not is_wide:
        state.no_supply = True
        path.append("NO_SUPPLY : volume sec + direction baissière sans conviction")

    # P15 AUDIT VSA — gap detection (open vs close précédent).
    # Doctrine réf (Tom Williams) : un gap entre sessions = signal d'inégalité
    # offre/demande. Si open >> prev_close + seuil → continuation haussière attendue
    # (gap_bullish). Si open << prev_close - seuil → gap baissier (rejet probable).
    # Seuil : ratio = |open - prev_close| / avg_spread_lookback > gap_threshold_ratio.
    if len(prev_bars) >= 1:
        prev_close = float(prev_bars[-1].get("close", 0.0) or 0.0)
        cur_open = float(cur.get("open", 0.0) or 0.0)
        gap_threshold_ratio = float(cfg.get("gap_threshold_ratio", 0.5))
        if avg_spread > 0 and prev_close > 0:
            gap_size = cur_open - prev_close
            gap_ratio = abs(gap_size) / avg_spread
            if gap_ratio >= gap_threshold_ratio:
                state.has_gap = True
                if gap_size > 0:
                    state.gap_bullish = True
                    path.append(
                        f"GAP BULLISH : open={cur_open:.5f} > prev_close={prev_close:.5f} "
                        f"ratio={gap_ratio:.2f} (seuil {gap_threshold_ratio})"
                    )
                else:
                    state.gap_bearish = True
                    path.append(
                        f"GAP BEARISH : open={cur_open:.5f} < prev_close={prev_close:.5f} "
                        f"ratio={gap_ratio:.2f} (seuil {gap_threshold_ratio})"
                    )

    if is_climax:
        state.climax = True

    # Stopping volume : climax_volume MAIS contre-tendance des 5 bougies précédentes
    if is_climax and len(prev_bars) >= 5:
        prior_directions = [(_body(b)[1]) for b in prev_bars[-5:]]
        prior_bias = sum(prior_directions)
        if prior_bias > 0 and direction < 0:
            state.stopping_volume = True
            path.append("STOPPING_VOLUME : climax baissier après trend haussier")
        elif prior_bias < 0 and direction > 0:
            state.stopping_volume = True
            path.append("STOPPING_VOLUME : climax haussier après trend baissier")

    # -- 7. Remplissage dataclass
    state.state = final_state
    state.spread = spread
    state.spread_relative = spread_relative
    state.volume = volume
    state.volume_relative = volume_relative
    state.effort_vs_result = effort_vs_result
    state.body_ratio = body_ratio
    state.close_location = close_location
    state.direction = direction
    state.classification_path = path
    return state, path


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def compute_vsa(
    symbol: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
    real_volume: Optional[List[float]] = None,
    spreads: Optional[List[float]] = None,
) -> VSAEngineState:
    """Calcule le VSAState pour la bougie la plus récente.

    Parameters
    ----------
    symbol : ex "EURUSD"
    timestamp : ISO 8601 UTC string de la bougie de référence (R9 audit).
    timeframe : M1/M5/M15/M30/H1/H4/D1.
    bars : liste croissante de bougies OHLCV. La dernière est la bougie
           courante. Format : {open, high, low, close, tick_volume?}.
    overrides : dict optionnel fusionné avec DEFAULTS (overrides ponctuels).
    seed : graine de reproductibilité (R9 — métadonnée).
    real_volume : optionnel — liste des volumes réels (MT5 real_volume).
                   Si fourni, sur-écrit tick_volume pour les computations.
                   Permet une précision ×2 si MT5 dispo (Phase 7 directive).
    spreads : optionnel — liste des spreads réels (MT5 spread points/barre).
                Si fourni, le spread courant est recalculé via spread moyen.

    Returns
    -------
    VSAEngineState dataclass, sérialisable via as_dict().

    Doctrine R6 fail-open : si data insuffisante (< min_bars_required),
    on retourne VSAState.NEUTRAL + flag data_insufficient=True, et on
    logge un warning debug (pas d'erreur — calcul seulement).

    Doctrine R2 additif : ce module n'importe RIEN depuis core/v9/.
    """
    cfg: Dict[str, object] = dict(DEFAULTS)
    if overrides:
        for k, v in overrides.items():
            if k in DEFAULTS:
                cfg[k] = v

    # Real volume (MT5 precision ×2) si fourni
    if real_volume and len(real_volume) == len(bars):
        for b, rv in zip(bars, real_volume):
            b["tick_volume"] = rv  # sur-écrit avec volume réel
    # Spreads réels (info R9 — pas consommé dans le verdict VSA)

    state = VSAEngineState(
        symbol=symbol,
        timestamp=timestamp,
        timeframe=timeframe,
        seed=seed,
        period=int(cfg.get("volume_lookback", 20)),
    )

    if timeframe not in cfg["supported_timeframes"]:
        log.debug(
            "v10_vsa: timeframe=%s non supporté (attendu %s) — NEUTRAL forcé",
            timeframe, cfg["supported_timeframes"],
        )
        state.data_insufficient = True
        state.classification_path.append(
            f"timeframe={timeframe} non supporté → NEUTRAL forcé"
        )
        return state

    min_required = int(cfg.get("min_bars_required", 21))
    if not bars or len(bars) < min_required:
        state.data_insufficient = True
        state.classification_path.append(
            f"bars={len(bars) if bars else 0} < min_required={min_required} → NEUTRAL fail-open"
        )
        log.debug("v10_vsa: bars=%d < min=%d", len(bars) if bars else 0, min_required)
        return state

    # P5 AUDIT VSA : end-of-bar gate (bougie fermée uniquement)
    # Doctrine : tout calcul VSA = bougie fermée. Intra-barre = interdit
    # (sinon, faux signaux sur Bougie en formation). On vérifie is_closed_bar
    # sur la fenêtre de calcul. Défaut 1 = OK si absent (DB V10 garantit is_closed_bar=1).
    cur_bar = bars[-1]
    is_closed_last = cur_bar.get("is_closed_bar", 1)
    if not is_closed_last:
        state.data_insufficient = True
        state.classification_path.append(
            "P5 end-of-bar gate: dernière bougie is_closed_bar=False → NEUTRAL fail-open (intra-barre interdit)"
        )
        log.debug("v10_vsa: intra-barre détecté (is_closed_bar=False) — NEUTRAL")
        return state
    # Vérifier que la fenêtre de calcul (min_required dernières) ne contient pas
    # de bougie non fermée (sécurité supplémentaire contre snapshot mixte).
    for j, b in enumerate(bars[-min_required:]):
        if not b.get("is_closed_bar", 1):
            state.data_insufficient = True
            state.classification_path.append(
                f"P5 end-of-bar gate: bougie[{j}] de la fenêtre is_closed_bar=False → NEUTRAL"
            )
            return state

    cur = bars[-1]
    prev_bars = bars[:-1]
    classified_state, _ = _classify_bar(cur, prev_bars, cfg)

    # Re-stamp metadata (the helper returned a blank state to avoid duplication)
    classified_state.symbol = symbol
    classified_state.timestamp = timestamp
    classified_state.timeframe = timeframe
    classified_state.seed = seed
    classified_state.period = int(cfg.get("volume_lookback", 20))
    classified_state.n_bars_used = len(bars)
    return classified_state


# ─────────────────────────────────────────────────────────────────────
# API multi-barres : classifie toute la série (utile pour backtest Phase 5)
# ─────────────────────────────────────────────────────────────────────
def compute_vsa_series(
    symbol: str,
    timeframe: str,
    bars: List[dict],
    *,
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> List[VSAEngineState]:
    """Classifie chaque bougie sur l'ensemble de la série (backtest-ready).

    Pour chaque bougie i (avec assez d'historique avant), retourne le VSAState.
    Renvoie une liste d'états alignée avec `bars` (longueur identique).
    Les bougies i < min_bars_required retournent VSAState.NEUTRAL.
    """
    cfg: Dict[str, object] = dict(DEFAULTS)
    if overrides:
        for k, v in overrides.items():
            if k in DEFAULTS:
                cfg[k] = v

    min_required = int(cfg.get("min_bars_required", 21))
    out: List[VSAEngineState] = []
    for i in range(len(bars)):
        if i < min_required - 1:
            out.append(VSAEngineState(
                symbol=symbol,
                timestamp=str(bars[i].get("timestamp", "")),
                timeframe=timeframe,
                seed=seed,
                data_insufficient=True,
                classification_path=[f"i={i} < min_required-1 → NEUTRAL"],
            ))
            continue
        cur = bars[i]
        prev = bars[:i]
        ts = str(cur.get("timestamp", ""))
        s, _ = _classify_bar(cur, prev, cfg)
        s.symbol = symbol
        s.timestamp = ts
        s.timeframe = timeframe
        s.seed = seed
        s.period = int(cfg.get("volume_lookback", 20))
        s.n_bars_used = i + 1
        out.append(s)
    return out


# R2 additif (Mission 3) : structure vide detect_behavioral_sequence
# NE PAS CODER LES PATTERNS -- en attente validation Son.
# Doctrine Son (SON_INTERPRETATION.md §6 backlog elicitation) :
# "Si les sequences exactes ne sont pas claires, ne PAS inventer."
# Cette structure : API stable, implementations stubees R6 fail-open.
from dataclasses import dataclass as _dc_m3, field as _field_m3
from enum import Enum as _Enum_m3


class BehavioralPattern(str, _Enum_m3):
    """Patterns comportementaux canoniques -- enum stable pour API.

    Valeurs definies par SON_INTERPRETATION.md §2.2 :
      - ACCUMULATION_x2_to_MARKUP : entree longue valide
      - MARKUP_x3plus_to_DISTRIBUTION : sortie / short setup
      - NEUTRAL_x3plus_to_MARKUP_strong : breakout institutionnel
      - UPTHRUST_to_MARKDOWN : piege confirme
      - UNKNOWN : pas de pattern detecte (R6 fail-open)
    """
    ACCUMULATION_x2_to_MARKUP = "accumulation_x2_to_markup"
    MARKUP_x3plus_to_DISTRIBUTION = "markup_x3plus_to_distribution"
    NEUTRAL_x3plus_to_MARKUP_strong = "neutral_x3plus_to_markup_strong"
    UPTHRUST_to_MARKDOWN = "upthrust_to_markdown"
    UNKNOWN = "unknown"


@_dc_m3
class BehavioralSequenceResult:
    """Resultat de detect_behavioral_sequence().

    Attributes :
      pattern : BehavioralPattern detecte (UNKNOWN si aucun match)
      confidence : float [0, 1] (HAUTE = 0.7+, MOYENNE = 0.5-0.7, FAIBLE < 0.5)
      state_history : list[str] -- les N derniers etats VSA observes
      n_bars_analyzed : int -- nombre de bougies dans la fenetre
      audit : dict -- metadata R9 (methode, raison, etc.)
    """
    pattern: BehavioralPattern = BehavioralPattern.UNKNOWN
    confidence: float = 0.0
    state_history: list = _field_m3(default_factory=list)
    n_bars_analyzed: int = 0
    audit: dict = _field_m3(default_factory=dict)


def detect_behavioral_sequence(states_history, window: int = 5) -> BehavioralSequenceResult:
    """Detecte les patterns comportementaux canoniques sur une fenetre d'etats VSA.

    Son-interprete -- STRUCTURE VIDE (Mission 3 brief) :
    "Si les sequences exactes ne sont pas claires, ne PAS inventer.
    Creer la structure vide avec les tests unitaires correspondants,
    documenter les patterns attendus, et attendre validation Son."

    Implementation actuelle : R6 fail-open -- renvoie UNKNOWN avec confidence 0.
    Code reel : en attente validation Son des patterns §2.2 de SON_INTERPRETATION.md.

    Args :
        states_history : list[str ou VSAState] -- etats VSA des dernieres N bougies
                         (du plus recent au plus ancien, ou inverse -- convention doc)
        window : int -- nombre de bougies a considerer (defaut 5)

    Returns :
        BehavioralSequenceResult (pattern=UNKNOWN, confidence=0 par defaut).
    """
    res = BehavioralSequenceResult(
        n_bars_analyzed=min(len(states_history), window) if states_history else 0,
        state_history=list(states_history)[-window:] if states_history else [],
        audit={
            "method": "stub_R6_failopen",
            "reason": "Mission 3 structure vide -- patterns en attente validation Son",
            "doc_ref": "docs/V10/SON_INTERPRETATION.md §2.2 + §6 backlog",
        },
    )
    return res


__all__ = [
    "VSAState",
    "VSAEngineState",
    "compute_vsa",
    "compute_vsa_series",
    "_classify_bar",
    "_sma",
    "_spread",
    "_body",
    "DEFAULTS",
    # Mission 3
    "BehavioralPattern",
    "BehavioralSequenceResult",
    "detect_behavioral_sequence",
]
