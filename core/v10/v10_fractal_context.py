"""v10_fractal_context — Lecture fractale multi-TF + cinématique rapide (CEO 06/08).

Constat (audit lecture 06/08) :
  - La boucle live (v10_live_decision.tick_decision) itère M30/H1/H4
    INDÉPENDAMMENT sans confluence fractale. Chaque TF décide seul.
  - La cinématique rapide (M1/M5 : spikes baissiers ~3x plus rapides que
    la lecture lissée M15/H1) est INVISIBLE dans les TF lents → biais de
    perception (cf. v9_speed_bias_analyzer, v9_bear_perception).
  - `decide_entry` ne reçoit QUE session/ote/smc/regime (pitfall 50 :
    lecture riche non connectée au live).

Ce module fournit une lecture fractale ADDITIVE (R2, 0 import core/v9/) :
  1. `compute_fractal_confluence` — agrège les 7 TF (M1/M5/M15/M30/H1/H4/D1)
     pondérés par poids (HTF = biais, LTF = entrée). Retourne direction
     dominante + score de confluence [0,1] + alignment par TF.
  2. `compute_fast_cinematics` — vitesse réelle sur M1/M5 (pips/min) + ratio
     de divergence vs la vitesse lissée du TF de décision. Détecte le
     "mouvement invisible" : la cinétique que les TF lents lissent.
  3. `fractal_signal` — compose (confluence × cinématique) en un boost
     [0..+1] ou un veto [..-1] pour la décision.

R6 : toute lecture SQL défaillante → fail-open (score 0, direction NONE).
R9 : chaque chiffre est sourcé (audit JSON).
R10 : compute only, zéro ordre réel.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Pondération par TF (fractale : les lents = biais, les rapides = entrée)
DEFAULT_TF_WEIGHTS: Dict[str, float] = {
    "D1": 0.22,
    "H4": 0.20,
    "H1": 0.16,
    "M30": 0.14,
    "M15": 0.10,
    "M5": 0.10,
    "M1": 0.08,
}

# TF rapides pour la cinématique (où vit la vélocité réelle)
FAST_TFS = ("M1", "M5")
# TF de biais (direction longue portée)
BIAS_TFS = ("H4", "D1")
# TF d'entrée (déclencheur)
ENTRY_TFS = ("M15", "M30")

# Seuil de divergence cinématique : M1/M5 beaucoup plus rapide que le TF
# de décision → mouvement invisible (le biais de perception du CEO).
DIVERGENCE_RATIO_FAST = 2.0

# Confluence minimale pour considérer un alignement exploitable
CONFLUENCE_MIN = 0.45


# ── Dataclasses ──────────────────────────────────────────────────────────
@dataclass
class TFAction:
    """Direction d'un TF individuel (dérivée de la pente des closes)."""
    tf: str
    direction: str            # BULLISH / BEARISH / FLAT
    slope: float              # pente normalisée
    weight: float             # poids effectif

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FractalConfluence:
    """Confluence multi-TF pondérée."""
    dominant_bias: str        # BULLISH / BEARISH / NONE
    score: float              # [0,1] magnitude de l'alignement
    n_tfs: int                # nb de TF analysés
    tfs: List[Dict] = field(default_factory=list)
    alignment: Dict = field(default_factory=dict)  # {tf: direction}

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FastCinematics:
    """Cinématique rapide : vitesse réelle vs vitesse lissée."""
    fast_speed_pips_per_min: float = 0.0     # signée (négatif = baissier)
    fast_direction: str = "NONE"
    decision_tf_speed_pips_per_min: float = 0.0
    divergence_ratio: float = 0.0            # |fast| / |tf_lent| (>2 = invisible)
    has_fast_divergence: bool = False
    m5_speed_pips_per_min: float = 0.0
    m1_speed_pips_per_min: float = 0.0

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FractalSignal:
    """Signal fractal composé (confluence × cinématique)."""
    confluence: Dict = field(default_factory=dict)
    cinematics: Dict = field(default_factory=dict)
    direction: str = "NONE"        # BULLISH / BEARISH / NONE
    boost: float = 0.0             # [-1..+1] : -1 = fort veto baissier, +1 = fort boost
    aligned: bool = False          # confluence et cinématique dans le même sens
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return asdict(self)


# ── Utilitaires DB ───────────────────────────────────────────────────────
def _connect(db_path: str) -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _load_closes(conn: sqlite3.Connection, symbol: str, tf: str,
                 limit: int) -> List[float]:
    """Charge les closes chronologiques (plus ancien → plus récent)."""
    try:
        rows = conn.execute(
            "SELECT close FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), int(limit)),
        ).fetchall()
    except Exception:
        return []
    return [float(r["close"]) for r in reversed(rows)]


def _slope(closes: List[float]) -> float:
    """Pente linéaire normalisée des closes → direction + force."""
    if len(closes) < 3:
        return 0.0
    n = len(closes)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(closes) / n
    num = sum((x - mx) * (c - my) for x, c in zip(xs, closes))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    slope = num / den
    # Normaliser par le prix moyen pour obtenir un taux relatif
    scale = (sum(closes) / n) or 1.0
    return slope / scale


def _dir_from_slope(slope: float, thr: float = 1e-6) -> str:
    if slope > thr:
        return "BULLISH"
    if slope < -thr:
        return "BEARISH"
    return "FLAT"


# ── API publique ─────────────────────────────────────────────────────────
def compute_fractal_confluence(
    *,
    symbol: str,
    timeframes: Tuple[str, ...] = ("M1", "M5", "M15", "M30", "H1", "H4", "D1"),
    weights: Optional[Dict[str, float]] = None,
    lookback_by_tf: Optional[Dict[str, int]] = None,
    db_path: str = "data/v9_forces.db",
) -> FractalConfluence:
    """Agrège la direction de chaque TF pondérée → biais dominant.

    R6 : un TF sans données → poids effectif 0 (redistribution). Si aucun
    TF n'a de données → FractalConfluence(NONE, 0).
    """
    conn = _connect(db_path)
    if conn is None:
        return FractalConfluence(dominant_bias="NONE", score=0.0, n_tfs=0)
    w_map = dict(weights) if weights else dict(DEFAULT_TF_WEIGHTS)
    lb = lookback_by_tf or {"M1": 30, "M5": 20, "M15": 20, "M30": 20,
                            "H1": 30, "H4": 30, "D1": 20}
    tf_actions: List[TFAction] = []
    total_weight = 0.0
    bias_score = 0.0
    try:
        for tf in timeframes:
            wt = w_map.get(tf, 0.0)
            if wt <= 0:
                continue
            closes = _load_closes(conn, symbol, tf, lb.get(tf, 20))
            if len(closes) < 3:
                continue
            sl = _slope(closes)
            direction = _dir_from_slope(sl)
            tf_actions.append(TFAction(tf=tf, direction=direction,
                                       slope=sl, weight=wt))
            total_weight += wt
            if direction == "BULLISH":
                bias_score += wt
            elif direction == "BEARISH":
                bias_score -= wt
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if total_weight == 0 or not tf_actions:
        return FractalConfluence(dominant_bias="NONE", score=0.0, n_tfs=0)
    # score ∈ [-1, +1] → magnitude d'alignement [0,1]
    norm_score = bias_score / total_weight
    dominant = "BULLISH" if norm_score > 0.15 else ("BEARISH" if norm_score < -0.15 else "NONE")
    score = min(1.0, abs(norm_score))
    return FractalConfluence(
        dominant_bias=dominant,
        score=round(score, 4),
        n_tfs=len(tf_actions),
        tfs=[t.as_dict() for t in tf_actions],
        alignment={t.tf: t.direction for t in tf_actions},
    )


def compute_fast_cinematics(
    *,
    symbol: str,
    decision_timeframe: str = "H1",
    db_path: str = "data/v9_forces.db",
    fast_lookback: int = 15,
    tf_speed_lookback: int = 30,
) -> FastCinematics:
    """Vitesse réelle (M1/M5) vs vitesse lissée du TF de décision.

    La divergence > DIVERGENCE_RATIO_FAST signale un mouvement rapide
    invisible dans le TF lent (le biais de perception du CEO : le baissier
    est plus rapide que ce que lisent les TF lissés).
    """
    conn = _connect(db_path)
    if conn is None:
        return FastCinematics()
    def _speed(tf: str) -> float:
        closes = _load_closes(conn, symbol, tf, tf_speed_lookback if tf != "M1" else fast_lookback)
        if len(closes) < 2:
            return 0.0
        pip = 100.0 if tf in ("M1",) and symbol.upper().endswith("JPY") else 10000.0
        if symbol.upper().endswith("JPY"):
            pip = 100.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        total = sum(deltas) * pip
        minutes = len(deltas) * {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
                                 "H1": 60, "H4": 240}.get(tf, 1)
        return total / minutes if minutes else 0.0
    try:
        m1 = _speed("M1")
        m5 = _speed("M5")
        dec_tf = _speed(decision_timeframe)
        # Vitesse rapide = max magnitude entre M1 et M5, signée
        fast = m1 if abs(m1) >= abs(m5) else m5
        if fast == 0:
            direction = "NONE"
        else:
            direction = "BEARISH" if fast < 0 else "BULLISH"
        divergence = 0.0
        if dec_tf != 0.0:
            if (fast >= 0) == (dec_tf >= 0):
                divergence = abs(fast) / max(abs(dec_tf), 1e-6)
            else:
                divergence = 99.0  # signes opposés = divergence extrême
        has_fast = divergence >= DIVERGENCE_RATIO_FAST
        return FastCinematics(
            fast_speed_pips_per_min=round(fast, 4),
            fast_direction=direction,
            decision_tf_speed_pips_per_min=round(dec_tf, 4),
            divergence_ratio=round(divergence, 3),
            has_fast_divergence=has_fast,
            m5_speed_pips_per_min=round(m5, 4),
            m1_speed_pips_per_min=round(m1, 4),
        )
    except Exception as exc:
        log.warning("compute_fast_cinematics échoué (R6): %s", exc)
        return FastCinematics()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def fractal_signal(
    *,
    confluence: FractalConfluence,
    cinematics: FastCinematics,
    decision_direction: str,   # "long" / "short" / ""
) -> FractalSignal:
    """Compose confluence + cinématique en un boost/veto directionnel.

    Règles (heuristique conservative R10) :
      - Si la confluence a un biais NET (score ≥ CONFLUENCE_MIN) ET la
        cinématique rapide est dans le MÊME sens → aligned, boost +score.
      - Si la confluence est alignée avec la décision mais la cinématique
        rapide est OPPOSÉE → veto (friction) : -0.5 (le move rapide va contre).
      - Sinon → boost faible selon confluence seule.

    Returns FractalSignal avec boost ∈ [-1, +1].
    """
    reasons: List[str] = []
    c_dir = confluence.dominant_bias
    k_dir = cinematics.fast_direction

    # Direction voulue → signe
    dec_sign = 1.0 if decision_direction in ("long", "BUY", "BULLISH") else \
        (-1.0 if decision_direction in ("short", "SELL", "BEARISH") else 0.0)

    boost = 0.0
    aligned = False

    # Signe de la confluence (défini dès qu'il y a un biais)
    c_sign = 0.0
    if c_dir != "NONE":
        c_sign = 1.0 if c_dir == "BULLISH" else -1.0

    if c_dir != "NONE" and confluence.score >= CONFLUENCE_MIN:
        # Confluence seule : boost directionnel signé (BULLISH +, BEARISH -)
        boost += c_sign * confluence.score * 0.6
        reasons.append(f"confluence_{c_dir}_score_{confluence.score}")

    if k_dir != "NONE":
        k_sign = 1.0 if k_dir == "BULLISH" else -1.0
        # Cinématique rapide confirme ou contredit la confluence
        if c_dir != "NONE" and k_sign == c_sign:
            aligned = True
            boost += 0.3 * min(1.0, cinematics.divergence_ratio / DIVERGENCE_RATIO_FAST) if cinematics.divergence_ratio else 0.15
            reasons.append(f"cinematics_confirm_{k_dir}")
        elif c_dir != "NONE" and k_sign != c_sign:
            boost -= 0.5
            reasons.append(f"cinematics_veto_opposite_{k_dir}")
        elif c_dir == "NONE":
            # Pas de biais de confluence mais la cinématique rapide est forte
            # (fractale : le move rapide M1/M5 est le signal d'entrée). On
            # l'utilise comme signal directionnel faible si la divergence est
            # marquée (move invisible dans les TF lents).
            if cinematics.divergence_ratio >= DIVERGENCE_RATIO_FAST:
                boost += k_sign * 0.3
                aligned = True
                reasons.append(f"cinematics_only_{k_dir}_fast_move")

    # La décision elle-même doit être cohérente avec le signal fractal
    if dec_sign != 0.0 and boost != 0.0:
        if (boost > 0) != (dec_sign > 0):
            # Le fractal va contre la décision → réduire l'élan (friction)
            boost -= 0.4
            reasons.append("fractal_opposes_decision")

    boost = max(-1.0, min(1.0, round(boost, 3)))
    final_dir = "BULLISH" if boost > 0.05 else ("BEARISH" if boost < -0.05 else "NONE")
    return FractalSignal(
        confluence=confluence.as_dict(),
        cinematics=cinematics.as_dict(),
        direction=final_dir,
        boost=boost,
        aligned=aligned,
        reasons=reasons,
    )


__all__ = [
    "DEFAULT_TF_WEIGHTS", "FAST_TFS", "BIAS_TFS", "ENTRY_TFS",
    "DIVERGENCE_RATIO_FAST", "CONFLUENCE_MIN",
    "FractalConfluence", "FastCinematics", "FractalSignal",
    "compute_fractal_confluence", "compute_fast_cinematics", "fractal_signal",
]
