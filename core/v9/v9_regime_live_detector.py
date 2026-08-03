"""v9_regime_live_detector.py — Phase 138 : Regime Live Detector (DOW × regime × vol).

Detecteur live de regime qui combine 3 signaux pour predire le regime
probable de la prochaine heure (H+1) en vue d'une pre-decision adaptative
du pipeline (sizing, hedge, hold).

Logique de prediction :
1. DOW (Day Of Week) influence le regime de la paire
   - Mardi GBPUSD = baissier (audit SQL live 03/08, n=20 WR=5% PNL=-136.9p)
   - Mercredi GBPUSD = haussier (audit SQL live 03/08, n=111 WR=79.3% +423.1p)
2. Vol spike (>2.0) -> regime EXTENSION probable (momentum continue)
3. Vol calme (<0.7) -> regime RETOUR_EQUILIBRE probable (mean reversion)
4. Par defaut, le regime reste stable (heritage de current_regime)

Combinaison par score (somme ponderee) :
  - Si une majorite de signaux convergent vers un regime, confidence haute.
  - Si signaux contradictoires, confidence basse, prediction = current_regime.

Audit SQL live 03/08/2026 :
  - GBPUSD mardi   : n=20, WR=5.0%,  PNL=-136.9p (CASSURE baissiere rare)
  - GBPUSD mercredi: n=111, WR=79.3%, PNL=+423.1p (EDGE haussier fort)
  - EXTENSION x vol spike (logique)  : confirmation structurelle
  - RETOUR_EQUILIBRE x vol calme     : retour a la moyenne

Gain projete : 40-80 pips (pre-decision adaptative sur la prochaine heure).
Doctrine : R2 additif, R6 fail-open, R25' motion CEO.
"""
from __future__ import annotations

from core.v9.kill_switches import get

VERSION = "1.0"

# ── Configuration ───────────────────────────────────────────────────
# Vol
VOL_SPIKE_THRESHOLD = 2.0
VOL_CALME_THRESHOLD = 0.7

# Regimes canoniques
REGIMES = ("EXTENSION", "RETOUR_EQUILIBRE", "CASSURE", "REJET", "NEUTRE")

# DOW x symbol -> regime predit (heuristique basee sur audit SQL live)
# Format : { dow: { symbol: regime } }
# dow : 0=lundi, 1=mardi, 2=mercredi, 3=jeudi, 4=vendredi, 5=samedi, 6=dimanche
DOW_REGIME_BIAS: dict[int, dict[str, str]] = {
    1: {  # mardi
        "GBPUSD": "CASSURE",  # baissier / structurel
    },
    2: {  # mercredi
        "GBPUSD": "EXTENSION",  # haussier / momentum
    },
}

# Scores pour combiner les signaux
SCORE_DOW = 0.5
SCORE_VOL = 0.3
SCORE_PERSIST = 0.2  # legere preference pour conserver le regime actuel

REGIME_LIVE_ENV = "V9_REGIME_LIVE_DETECTOR_ENABLED"


# ── Kill switch ─────────────────────────────────────────────────────
def regime_live_detector_enabled() -> bool:
    """Kill switch V9_REGIME_LIVE_DETECTOR_ENABLED — Phase 138 (03/08/2026).

    Active le detecteur live de regime (DOW × regime × vol) pour
    pre-decision adaptative de la prochaine heure.
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2).
    """
    return get(REGIME_LIVE_ENV, "0") == "1"


# ── Helpers ─────────────────────────────────────────────────────────
def _dow_signal(utc_dow: int, symbol: str) -> tuple[str | None, str]:
    """Signal DOW : retourne (regime_préféré, raison). None si pas de biais connu."""
    try:
        d = int(utc_dow)
    except (TypeError, ValueError):
        return None, "dow_unknown"
    sym = (symbol or "").strip().upper()
    if d not in DOW_REGIME_BIAS:
        return None, f"dow_{d}_no_bias"
    sym_map = DOW_REGIME_BIAS[d]
    if sym not in sym_map:
        return None, f"dow_{d}_{sym}_no_bias"
    regime = sym_map[sym]
    return regime, f"dow_{d}_{sym}_{regime}"


def _vol_signal(vol_ratio: float) -> tuple[str | None, str]:
    """Signal vol : EXTENSION si spike, RETOUR_EQUILIBRE si calme, None si normal.

    Convention :
      - None, "vol_normal_neutral"  : vol normal (0.7 < x < 2.0), pas de signal
      - "EXTENSION", "vol_spike_*"  : vol spike (>= 2.0)
      - "RETOUR_EQUILIBRE", "vol_calme_*" : vol calme (<= 0.7)
      - None, "vol_unknown"         : input invalide (None/non numerique)
    Note : vol normal = signal vide MAIS pas "unknown" au sens R6 fail-open
    (la mesure est valide, elle est juste neutre).
    """
    if vol_ratio is None:
        return None, "vol_unknown"
    try:
        v = float(vol_ratio)
    except (TypeError, ValueError):
        return None, "vol_unknown"
    if v >= VOL_SPIKE_THRESHOLD:
        return "EXTENSION", f"vol_spike_x{v}_extension"
    if v <= VOL_CALME_THRESHOLD:
        return "RETOUR_EQUILIBRE", f"vol_calme_x{v}_retour"
    return None, "vol_normal_neutral"


# ── API principale ─────────────────────────────────────────────────
def predict_next_regime(
    current_regime: str,
    utc_hour: int,
    utc_dow: int,
    vol_ratio: float,
    symbol: str = "GBPUSD",
) -> dict:
    """Predit le regime probable pour la prochaine heure (H+1).

    Combine 3 signaux : DOW (×0.5), vol (×0.3), persistance (×0.2).
    Le regime avec le score max est selectionne.

    Args:
        current_regime : regime actuel (EXTENSION/RETOUR_EQUILIBRE/CASSURE/REJET/NEUTRE).
        utc_hour : heure UTC de la bougie H+1.
        utc_dow : day-of-week UTC de la bougie H+1 (0=lundi, 6=dimanche).
        vol_ratio : ratio vol actuelle / vol moyenne (1.0 = normal).
        symbol : paire Forex (defaut GBPUSD).

    Returns:
        dict avec :
          - predicted_regime : str
          - confidence : float (0.0 a 1.0)
          - current_regime : str
          - factors : list[str] (signaux qui ont influence la prediction)
          - scores : dict[str, float] (scores par regime)
          - leviers : list[str]
          - reason : str
    """
    # Normaliser current_regime
    cur = (current_regime or "NEUTRE").strip().upper()
    if cur not in REGIMES:
        cur = "NEUTRE"

    # Collecter les signaux
    scores: dict[str, float] = {r: 0.0 for r in REGIMES}
    factors: list[str] = []
    leviers: list[str] = []

    # 1. Signal DOW
    dow_regime, dow_reason = _dow_signal(utc_dow, symbol)
    if dow_regime is not None and dow_regime in scores:
        scores[dow_regime] += SCORE_DOW
        factors.append(dow_reason)
        leviers.append(f"L20_regime_{dow_reason}_x{SCORE_DOW}")

    # 2. Signal vol
    vol_regime, vol_reason = _vol_signal(vol_ratio)
    if vol_regime is not None and vol_regime in scores:
        scores[vol_regime] += SCORE_VOL
        factors.append(vol_reason)
        leviers.append(f"L20_regime_{vol_reason}_x{SCORE_VOL}")

    # 3. Persistance (leger bonus pour conserver current_regime)
    scores[cur] += SCORE_PERSIST
    factors.append(f"persist_current_{cur}_x{SCORE_PERSIST}")

    # 4. Regime prédit = argmax(scores)
    predicted = max(scores, key=lambda r: scores[r])
    top_score = scores[predicted]
    # Normalisation : 3 signaux max = 1.0, on borne
    confidence = min(1.0, round(top_score, 3))

    # R6 fail-open : si les 2 signaux externes (DOW + vol) sont unknown
    # (input invalide, pas juste "neutre"), on retombe sur current_regime
    # avec confidence 0.0 (degraded). Le signal persist (current_regime)
    # reste valide par definition. Un signal "vol normal" ou "DOW hors table"
    # n'est PAS unknown : c'est un signal vide mais valide.
    dow_unknown = dow_reason == "dow_unknown" or (
        dow_regime is None and "no_bias" in dow_reason
    )
    vol_unknown = vol_reason == "vol_unknown"
    if dow_unknown and vol_unknown:
        predicted = cur
        confidence = 0.0
        reason = "all_signals_unknown_fallback_current"
    else:
        reason = "majority_weighted_vote"

    return {
        "predicted_regime": predicted,
        "confidence": confidence,
        "current_regime": cur,
        "factors": factors,
        "scores": {r: round(s, 3) for r, s in scores.items()},
        "leviers": leviers,
        "reason": reason,
        "kill_switch_active": regime_live_detector_enabled(),
    }
