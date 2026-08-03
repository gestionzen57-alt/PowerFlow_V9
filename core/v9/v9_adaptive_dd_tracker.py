"""v9_adaptive_dd_tracker.py — Phase 137 : Adaptive Drawdown Tracker.

Affine le seuil DD portfolio (uniforme dans v9_drawdown_protector) par
contexte : vol × regime × session. En haute volatilite, un DD plus large
est tolere (bruit normal) ; en basse volatilite, un DD -50p est plus
suspect et declenche plus tot le HALT.

Logique adaptative :
    dd_threshold = DD_BASE × vol_mult × regime_mult × session_mult

Multiplicateurs par defaut (hypothese) :
  - vol_ratio >= 2.0 (spike) : ×1.5   | < 0.7 (calme) : ×0.7  | sinon ×1.0
  - regime CASSURE             : ×1.2   | RETOUR_EQUILIBRE : ×0.8  | sinon ×1.0
  - session asie (0-7 UTC)     : ×0.5   | overlap (13-16)  : ×1.0  | sinon ×1.0

Audit SQL live 03/08/2026 (n=9469 decisions resolues, distribution
regime × session) confirme la dispersion :
  - CASSURE × london     : n=5,  WR=0.0%,  -70.8p,  -14.16p/trade (DRAIN)
  - EXTENSION × asie     : n=79, WR=32.9%, -272.7p, -3.45p/trade
  - RETOUR_EQUILIBRE × overlap : n=60, WR=31.7%, -181.0p, -3.02p/trade
  - REJET × asie         : n=7,  WR=28.6%,  -29.0p, -4.14p/trade

Gain projete : 80-150 pips (reduction faux positifs HALT).
Doctrine : R2 additif, R6 fail-open, R25' motion CEO.
"""
from __future__ import annotations

from core.v9.kill_switches import get

VERSION = "1.0"

# ── Configuration ───────────────────────────────────────────────────
# Vol ratio
VOL_SPIKE_THRESHOLD = 2.0
VOL_CALME_THRESHOLD = 0.7
VOL_SPIKE_MULT = 1.5
VOL_CALME_MULT = 0.7

# Regime
REGIME_CASSURE_MULT = 1.2
REGIME_RETOUR_EQUILIBRE_MULT = 0.8

# Session (en UTC)
SESSION_ASIE_HOURS = (0, 7)        # inclusif 0-7
SESSION_OVERLAP_HOURS = (13, 16)   # inclusif 13-16
SESSION_ASIE_MULT = 0.5
SESSION_OVERLAP_MULT = 1.0

# Bornes finales (evite extremites absurdes)
DD_THRESHOLD_MIN = -300.0
DD_THRESHOLD_MAX = 0.0

ADAPTIVE_DD_ENV = "V9_ADAPTIVE_DD_TRACKER_ENABLED"


# ── Kill switch ─────────────────────────────────────────────────────
def adaptive_dd_tracker_enabled() -> bool:
    """Kill switch V9_ADAPTIVE_DD_TRACKER_ENABLED — Phase 137 (03/08/2026).

    Active le tracker DD adaptatif par contexte (vol × regime × session).
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2) — herite de v9_drawdown_protector sans modification.
    """
    return get(ADAPTIVE_DD_ENV, "0") == "1"


# ── Helpers : classification du contexte ────────────────────────────
def _session_from_utc_hour(utc_hour: int) -> str:
    """Classifie l'heure UTC en session (asie/london/overlap/ny_close)."""
    try:
        h = int(utc_hour)
    except (TypeError, ValueError):
        return "unknown"
    if SESSION_ASIE_HOURS[0] <= h <= SESSION_ASIE_HOURS[1]:
        return "asie"
    if 8 <= h <= 12:
        return "london"
    if SESSION_OVERLAP_HOURS[0] <= h <= SESSION_OVERLAP_HOURS[1]:
        return "overlap"
    if 17 <= h <= 23:
        return "ny_close"
    return "unknown"


def _vol_multiplier(vol_ratio: float) -> tuple[float, str]:
    """Multiplicateur vol selon vol_ratio (=atr_pips / atr_pips_moyen)."""
    try:
        v = float(vol_ratio)
    except (TypeError, ValueError):
        return 1.0, "vol_unknown"
    if v >= VOL_SPIKE_THRESHOLD:
        return VOL_SPIKE_MULT, f"vol_spike_x{VOL_SPIKE_MULT}"
    if v <= VOL_CALME_THRESHOLD:
        return VOL_CALME_MULT, f"vol_calme_x{VOL_CALME_MULT}"
    return 1.0, "vol_normal_x1.0"


def _regime_multiplier(regime: str | None) -> tuple[float, str]:
    """Multiplicateur regime selon type (CASSURE/RETOUR_EQUILIBRE/autre)."""
    r = (regime or "").strip().upper()
    if r == "CASSURE":
        return REGIME_CASSURE_MULT, f"regime_cassure_x{REGIME_CASSURE_MULT}"
    if r == "RETOUR_EQUILIBRE":
        return REGIME_RETOUR_EQUILIBRE_MULT, f"regime_retour_x{REGIME_RETOUR_EQUILIBRE_MULT}"
    return 1.0, "regime_neutral_x1.0"


def _session_multiplier(session: str | None, utc_hour: int | None = None) -> tuple[float, str]:
    """Multiplicateur session. Si session fourni, utilise ; sinon déduit de utc_hour."""
    s = (session or "").strip().lower()
    if not s and utc_hour is not None:
        s = _session_from_utc_hour(utc_hour)
    if s == "asie":
        return SESSION_ASIE_MULT, f"session_asie_x{SESSION_ASIE_MULT}"
    if s == "overlap":
        return SESSION_OVERLAP_MULT, f"session_overlap_x{SESSION_OVERLAP_MULT}"
    if s == "london":
        return 1.0, "session_london_x1.0"
    if s == "ny_close":
        return 1.0, "session_ny_close_x1.0"
    return 1.0, "session_unknown_x1.0"


# ── Calcul du seuil DD adaptatif ────────────────────────────────────
def compute_adaptive_dd_threshold(
    dd_base: float = -100.0,
    vol_ratio: float = 1.0,
    regime: str = "RETOUR_EQUILIBRE",
    session: str = "overlap",
) -> dict:
    """Retourne le seuil DD adaptatif selon contexte (vol × regime × session).

    Args:
        dd_base : seuil DD de base (defaut -100 pips, negatif).
        vol_ratio : ratio vol actuelle / vol moyenne (1.0 = normal).
        regime : type de regime (CASSURE/RETOUR_EQUILIBRE/EXTENSION/REJET/NEUTRE).
        session : session (asie/london/overlap/ny_close).

    Returns:
        dict avec :
          - dd_threshold : float (pips, negatif, adapte)
          - dd_base : float
          - vol_mult : float
          - regime_mult : float
          - session_mult : float
          - context_combo : str
          - leviers : list[str]
          - reason : str
    """
    v_mult, v_label = _vol_multiplier(vol_ratio)
    r_mult, r_label = _regime_multiplier(regime)
    s_mult, s_label = _session_multiplier(session)

    raw_threshold = float(dd_base) * v_mult * r_mult * s_mult
    # Bornes finales
    clamped = max(DD_THRESHOLD_MIN, min(DD_THRESHOLD_MAX, raw_threshold))

    leviers = []
    if v_mult != 1.0:
        leviers.append(f"L19_dd_{v_label}")
    if r_mult != 1.0:
        leviers.append(f"L19_dd_{r_label}")
    if s_mult != 1.0:
        leviers.append(f"L19_dd_{s_label}")

    return {
        "dd_threshold": round(clamped, 2),
        "dd_base": float(dd_base),
        "vol_mult": v_mult,
        "regime_mult": r_mult,
        "session_mult": s_mult,
        "vol_label": v_label,
        "regime_label": r_label,
        "session_label": s_label,
        "context_combo": (
            f"vol={v_label} reg={r_label} ses={s_label}"
        ),
        "leviers": leviers,
        "reason": "adaptive_threshold_calculated",
    }


# ── Verification HALT ───────────────────────────────────────────────
def track_drawdown(
    dd_current: float,
    vol_ratio: float,
    regime: str,
    session: str,
    dd_base: float = -100.0,
) -> dict:
    """Verifie si le DD actuel depasse le seuil adaptatif.

    Args:
        dd_current : DD actuel (negatif ou nul).
        vol_ratio : ratio vol (>=2 spike, <=0.7 calme).
        regime : type de regime.
        session : session ou 'auto' si derive d'utc_hour.
        dd_base : seuil de base (defaut -100).

    Returns:
        dict avec :
          - halt : bool (True si dd_current < dd_threshold)
          - threshold : float (seuil adaptatif)
          - current : float (dd_current)
          - margin : float (dd_current - threshold, > 0 = sain)
          - threshold_info : dict (sortie de compute_adaptive_dd_threshold)
          - leviers : list[str]
          - kill_switch_active : bool
    """
    threshold_info = compute_adaptive_dd_threshold(
        dd_base=dd_base,
        vol_ratio=vol_ratio,
        regime=regime,
        session=session,
    )
    threshold = threshold_info["dd_threshold"]
    kill_on = adaptive_dd_tracker_enabled()

    # R6 fail-open : si kill switch OFF, on calcule mais on ne HALTe jamais
    # (laisser le Drawdown Protector standard decider).
    if not kill_on:
        halt = False
        reason = "kill_switch_off_pass_through"
    else:
        # dd_current et threshold sont negatifs ; HALT si current < threshold
        # (DD actuel plus grave que le seuil tolere)
        try:
            current = float(dd_current)
        except (TypeError, ValueError):
            current = 0.0
        halt = current < threshold
        reason = "adaptive_threshold_check"

    margin = round(float(dd_current) - threshold, 2) if dd_current is not None else 0.0

    return {
        "halt": halt,
        "threshold": threshold,
        "current": float(dd_current) if dd_current is not None else 0.0,
        "margin": margin,
        "threshold_info": threshold_info,
        "leviers": threshold_info["leviers"],
        "kill_switch_active": kill_on,
        "reason": reason,
    }
