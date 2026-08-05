"""V10 Compression-Extension VSA — Phase 11+ multi-TF M30/H1/H4.

Doctrine V10 (CEO étape 9.3) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open (état absent → NEUTRE, intensité absente → MOYEN)
  R7 : tests verts cumulés
  R9 : audit metadata honnête (JSON sérialisable)
  R10 : zéro capital (calcul seul)

Objectif Phase 11+ :
  Exploiter les colonnes natives `forces_snapshots.compression_extension_etat`
  et `compression_extension_intensite` pour calculer un signal VSA
  directionnel multi-TF (M30/H1/H4) :
    - COMPRESSION : potentiel directionnel HAUT
    - EXTENSION : épuisement, signal potentiel BAS
    - NEUTRE : indéterminé
  + bonus M30 si aligné H1 (cohérence CEO Étape 7)
  + bonus H4 si intensité EXTREME (signal fort)

API :
  - `compute_vsa_signal(snapshots_m30, snapshots_h1, snapshots_h4, pair)` → VSAState
  - `VSASignalReport` dataclass avec audit + JSON sérialisable
"""
from __future__ import annotations

import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# CONSTANTES (alignées v10_force_native.py)
# ─────────────────────────────────────────────────────────────────────

COMP_EXT_STATES = ("COMPRESSION", "EXTENSION", "NEUTRE")

# États → score directionnel signé (-1 = bearish, 0 = neutre, +1 = bullish)
STATE_DIRECTION = {
    "COMPRESSION": +1.0,   # potentiel expansion (continuation)
    "EXTENSION": -0.5,     # épuisement (réversal possible)
    "NEUTRE": 0.0,
}

# Intensité → poids du signal
INTENSITY_WEIGHT = {
    "FAIBLE": 0.25,
    "MOYEN": 0.50,
    "FORT": 0.75,
    "EXTREME": 1.00,
}

# Bonus M30 alignment avec H1 (cohérence Phase 22)
M30_ALIGN_H1_BONUS = 0.15

# Bonus H4 intensité EXTREME
H4_EXTREME_BONUS = 0.10

# Force delta threshold (cohérence avec v10_force_native)
FORCE_DELTA_THRESHOLD = 15.0


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

class VSAState(str):
    """Signal VSA final directionnel."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class TFVSAState:
    """État VSA par timeframe."""
    timeframe: str = ""
    last_bar_time: int = 0
    last_state: str = "NEUTRE"
    last_intensite: str = "MOYEN"
    n_compression: int = 0
    n_extension: int = 0
    n_neutre: int = 0
    score_directionnel: float = 0.0  # [-1, +1]

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VSASignalReport:
    """Rapport signal VSA multi-TF (Phase 11+ CEO Étape 9.3)."""
    pair: str = ""
    timestamp: str = ""
    state_m30: TFVSAState = field(default_factory=TFVSAState)
    state_h1: TFVSAState = field(default_factory=TFVSAState)
    state_h4: TFVSAState = field(default_factory=TFVSAState)
    score_global: float = 0.0  # [-1, +1]
    signal: str = VSAState.NEUTRAL
    m30_aligns_h1: bool = False
    h4_extreme_detected: bool = False
    bonus_applied: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _safe_str(x, default: str = "NEUTRE") -> str:
    """Convertir en str uppercase, fallback default si None."""
    if x is None:
        return default
    s = str(x).upper().strip()
    if s not in COMP_EXT_STATES:
        return default
    return s


def _safe_intensite(x, default: str = "MOYEN") -> str:
    """Convertir en str uppercase, fallback default si None ou inconnu."""
    if x is None:
        return default
    s = str(x).upper().strip()
    if s not in INTENSITY_WEIGHT:
        return default
    return s


# ─────────────────────────────────────────────────────────────────────
# CALCUL VSA PAR TF
# ─────────────────────────────────────────────────────────────────────

def compute_tf_vsa_state(
    snapshots: List[Dict],
    timeframe: str,
    *,
    window_size: int = 20,
) -> TFVSAState:
    """Calcule état VSA directionnel pour 1 timeframe.

    Args:
        snapshots: rows de `forces_snapshots` (triées par bar_time ASC)
        timeframe: "M30" / "H1" / "H4"
        window_size: nb candles récentes à analyser (default 20)

    Returns:
        TFVSAState avec score_directionnel ∈ [-1, +1]
    """
    if not snapshots:
        return TFVSAState(timeframe=timeframe)

    # Fenêtre : N dernières candles
    window = snapshots[-window_size:] if len(snapshots) > window_size else snapshots

    n_compression = 0
    n_extension = 0
    n_neutre = 0
    score_sum = 0.0
    weight_sum = 0.0

    for snap in window:
        state = _safe_str(snap.get("compression_extension_etat"), "NEUTRE")
        intensite = _safe_intensite(snap.get("compression_extension_intensite"), "MOYEN")

        # Compteurs
        if state == "COMPRESSION":
            n_compression += 1
        elif state == "EXTENSION":
            n_extension += 1
        else:
            n_neutre += 1

        # Score directionnel pondéré
        dir_sign = STATE_DIRECTION.get(state, 0.0)
        weight = INTENSITY_WEIGHT.get(intensite, 0.5)
        score_sum += dir_sign * weight
        weight_sum += weight

    # Score normalisé
    score_directionnel = (score_sum / weight_sum) if weight_sum > 0 else 0.0

    last = window[-1]
    last_bar_time = int(last.get("bar_time", 0) or 0)
    last_state = _safe_str(last.get("compression_extension_etat"), "NEUTRE")
    last_intensite = _safe_intensite(last.get("compression_extension_intensite"), "MOYEN")

    return TFVSAState(
        timeframe=timeframe,
        last_bar_time=last_bar_time,
        last_state=last_state,
        last_intensite=last_intensite,
        n_compression=n_compression,
        n_extension=n_extension,
        n_neutre=n_neutre,
        score_directionnel=round(score_directionnel, 4),
    )


# ─────────────────────────────────────────────────────────────────────
# SIGNAL MULTI-TF
# ─────────────────────────────────────────────────────────────────────

def compute_vsa_signal(
    snapshots_m30: List[Dict],
    snapshots_h1: List[Dict],
    snapshots_h4: List[Dict],
    pair: str,
    *,
    timestamp: str = "",
    window_size: int = 20,
) -> VSASignalReport:
    """Calcule signal VSA multi-TF (M30/H1/H4).

    Pondération :
      H4 = 50% (tendance long-terme)
      H1 = 30% (structure)
      M30 = 20% (timing court-terme)

    Bonus :
      + M30_ALIGN_H1_BONUS si M30+H1 alignés (même direction)
      + H4_EXTREME_BONUS si H4 intensité EXTREME

    Returns:
        VSASignalReport avec signal final ∈ {BULLISH, BEARISH, NEUTRAL}
    """
    state_m30 = compute_tf_vsa_state(snapshots_m30, "M30", window_size=window_size)
    state_h1 = compute_tf_vsa_state(snapshots_h1, "H1", window_size=window_size)
    state_h4 = compute_tf_vsa_state(snapshots_h4, "H4", window_size=window_size)

    # Score global pondéré (H4=0.50, H1=0.30, M30=0.20)
    score_global = (
        0.50 * state_h4.score_directionnel
        + 0.30 * state_h1.score_directionnel
        + 0.20 * state_m30.score_directionnel
    )

    # Détection bonus
    m30_aligns_h1 = (
        (state_m30.score_directionnel > 0 and state_h1.score_directionnel > 0)
        or (state_m30.score_directionnel < 0 and state_h1.score_directionnel < 0)
    )
    h4_extreme_detected = (state_h4.last_intensite == "EXTREME")

    bonus_applied = 0.0
    if m30_aligns_h1:
        bonus_applied += M30_ALIGN_H1_BONUS
        # Renforce le signe du score
        if score_global > 0:
            score_global += M30_ALIGN_H1_BONUS
        elif score_global < 0:
            score_global -= M30_ALIGN_H1_BONUS

    if h4_extreme_detected:
        bonus_applied += H4_EXTREME_BONUS
        # Renforce encore
        if score_global > 0:
            score_global += H4_EXTREME_BONUS
        elif score_global < 0:
            score_global -= H4_EXTREME_BONUS

    # Signal final
    if score_global > 0.30:
        signal = VSAState.BULLISH
    elif score_global < -0.30:
        signal = VSAState.BEARISH
    else:
        signal = VSAState.NEUTRAL

    score_global = max(-1.0, min(1.0, score_global))

    return VSASignalReport(
        pair=pair,
        timestamp=timestamp,
        state_m30=state_m30,
        state_h1=state_h1,
        state_h4=state_h4,
        score_global=round(score_global, 4),
        signal=signal,
        m30_aligns_h1=m30_aligns_h1,
        h4_extreme_detected=h4_extreme_detected,
        bonus_applied=round(bonus_applied, 4),
        audit={
            "window_size": window_size,
            "weights": {"H4": 0.50, "H1": 0.30, "M30": 0.20},
            "bonus_m30_align_h1": M30_ALIGN_H1_BONUS,
            "bonus_h4_extreme": H4_EXTREME_BONUS,
            "signal_thresholds": {"bullish": ">0.30", "bearish": "<-0.30"},
            "method": "V10 VSA multi-TF compression/extension (Phase 11+)",
            "doctrine": "R1, R2 (additif pur), R6, R7, R9, R10",
        },
    )


# ─────────────────────────────────────────────────────────────────────
# LOAD MULTI-TF FROM DB
# ─────────────────────────────────────────────────────────────────────

def load_multi_tf_from_db(
    db_path: str,
    pair: str,
    *,
    tfs: Tuple[str, ...] = ("M30", "H1", "H4"),
    limit: Optional[int] = None,
) -> Dict[str, List[Dict]]:
    """Charge snapshots multi-TF depuis DB (R6 fail-open si absent)."""
    out: Dict[str, List[Dict]] = {}
    try:
        con = sqlite3.connect(db_path, timeout=10)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Vérifier table existe
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'")
        if not cur.fetchone():
            con.close()
            return {tf: [] for tf in tfs}

        sql = """
            SELECT * FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
            ORDER BY bar_time ASC
        """
        if limit:
            sql += f" LIMIT {int(limit)}"

        for tf in tfs:
            cur.execute(sql, (pair, tf))
            out[tf] = [dict(row) for row in cur.fetchall()]

        con.close()
    except Exception:
        out = {tf: [] for tf in tfs}

    return out


# ─────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────

def demo_run(db_path: str = "data/v9_forces.db") -> List[VSASignalReport]:
    """Run demo sur 6 paires, calcule signal VSA multi-TF."""
    pairs = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]
    reports = []

    for pair in pairs:
        mtf = load_multi_tf_from_db(db_path, pair, limit=200)
        if not all(len(mtf.get(tf, [])) > 5 for tf in ("M30", "H1", "H4")):
            continue

        rep = compute_vsa_signal(
            mtf.get("M30", []),
            mtf.get("H1", []),
            mtf.get("H4", []),
            pair,
            timestamp="2026-08-05T08:00:00Z",
        )
        reports.append(rep)

    return reports


__all__ = [
    "COMP_EXT_STATES",
    "STATE_DIRECTION",
    "INTENSITY_WEIGHT",
    "M30_ALIGN_H1_BONUS",
    "H4_EXTREME_BONUS",
    "FORCE_DELTA_THRESHOLD",
    "VSAState",
    "TFVSAState",
    "VSASignalReport",
    "_safe_str",
    "_safe_intensite",
    "compute_tf_vsa_state",
    "compute_vsa_signal",
    "load_multi_tf_from_db",
    "demo_run",
]
