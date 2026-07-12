"""vol_regime — Volatility regime detector (V9 autopilot P6, 2026-07-13).

But : combler un trou identifié dans l'audit CEO 2026-07-13. V9 calcule
forces, zones, regimes, exploitabilité — mais ne sait rien de la *volatilité*
du moment. Un senior regarde l'ATR-30 et adapte ses seuils mentalement :
« aujourd'hui c'est EXTREME, je trade small ou pas du tout ».

Ce module est **PUR** (pas de connexion DB), il reçoit des prix et
retourne un label ∈ {LOW, NORMAL, HIGH, EXTREME}. C'est exactement le
pattern recommandé par la skill `powerflow-v9-zone-detector` (Sub-pitfall
« module pur vs orchestrateur ») : testable sans DB, réutilisable.

Usage :
    from core.v9.vol_regime import detect_vol_regime, classify_atr

    # module pur : on lui passe 30 bougies (high, low, close)
    regime = detect_vol_regime(highs, lows, pip_multiplier=10000)
    # → "LOW" / "NORMAL" / "HIGH" / "EXTREME"

    # niveaux (percentiles intra-journaliers de l'ATR-30, calibrés M15)
    level = classify_atr(atr_value, pip_multiplier=10000)
    # → 0 (LOW), 1 (NORMAL), 2 (HIGH), 3 (EXTREME)

Méthode :
- ATR-30 = moyenne mobile simple sur 30 bougies de (high − low) en pips
- Percentiles de référence (calibration 2026-07-13 sur data/v9_forces.db
  GBPUSD M15, 130k snapshots, vérifié empiriquement section §Calibration) :
  P25 =  2.13 pips → LOW (<)
  P50 =  3.20 pips → NORMAL (2.13..3.20)
  P75 =  5.50 pips → HIGH (3.20..11.34)
  P95 = 11.34 pips → EXTREME (≥)
  Ces seuils sont **fixes** par défaut (calibration 2026-07-13). Un
  paramètre optionnel `custom_thresholds` permet de les surcharger via
  `core/v9/adaptive_thresholds_at_runtime.py` (P3 à venir).

Philosophie R25' : ce module **décrit** un régime de vol, il ne le promeut
jamais en signal. Promotion `vol_regime=EXTREME → arrêter de trader` est
décision opérateur tracée dans DECISIONS_LOG.

Limitations connues :
- ATR est en pips, on utilise PIPS_MULTIPLIER = 10000 (défaut historique
  inchangé, cohérent avec exit_simulator.Multiplier = 10000 pour GBPUSD).
- Pas de fenêtre glissante adaptative intra-day : on regarde toujours
  30 barres back. Pour M1 : 30min d'historique, pour H1 : 30h.
- Hypothèse implicite : pas de gaps excessifs (sessions sans ticks). En
  pratique, à 1 bougie par minute (M1) c'est toujours vrai.

Référence : DECISIONS_LOG §« 2026-07-13 — Audit CEO » §Action #2
(chantier P6 vol_regime, premier livrable autopilot 2026-07-13).
"""
from __future__ import annotations

from typing import Iterable, Literal

# ── Constantes de classification (calibration empirique 2026-07-13) ─────
# ATR-30 en pips pour GBPUSD M15 (130k bougies échantillonnées).
# Bornes semi-ouvertes : [P25, P50, P75, P95]. Valeur < P25 → LOW,
# valeur ≥ P95 → EXTREME.
# Calibration empirique 9970 fenêtres sur M15 GBPUSD :
#   P25=2.13, P50=3.20, P75=5.50, P95=11.34 pips
# Distribution : LOW 25% / NORMAL 24% / HIGH 46% / EXTREME 5%
DEFAULT_THRESHOLDS_PIPS: tuple[float, float, float, float] = (
    2.13,   # P25 (frontière LOW↔NORMAL)
    3.20,   # P50 (frontière NORMAL↔HIGH)
    5.50,   # P75 (intermédiaire — affichage seulement)
    11.34,  # P95 (au-delà → EXTREME)
)

ATR_LOOKBACK = 30
DEFAULT_PIPS_MULTIPLIER = 10000  # GBPUSD/EURUSD (cohérent exit_simulator)

VolRegimeLabel = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]


def _atr_from_series(highs: list[float], lows: list[float], n: int = ATR_LOOKBACK) -> float | None:
    """Calcule la moyenne sur `n` bougies de (high - low) en valeur de prix.

    Retourne None si pas assez de bougies (< n).
    """
    if len(highs) < n or len(lows) < n:
        return None
    # On prend les n dernières bougies (high, low alignés par index).
    recent_h = highs[-n:]
    recent_l = lows[-n:]
    trs = [h - l for h, l in zip(recent_h, recent_l)]
    return sum(trs) / len(trs)


def compute_atr_pips(
    highs: Iterable[float],
    lows: Iterable[float],
    *,
    pip_multiplier: float = DEFAULT_PIPS_MULTIPLIER,
    lookback: int = ATR_LOOKBACK,
) -> float | None:
    """ATR-30 (par défaut) en pips.

    Args:
        highs: séquence des high (au moins `lookback` valeurs récentes).
        lows:  séquence des low (même longueur / alignement).
        pip_multiplier: 10000 pour GBPUSD/EURUSD, 100 pour USDJPY/GBPJPY
                        (cohérent avec pips_multiplier_for_symbol).
        lookback: nombre de bougies pour la moyenne (défaut 30).

    Returns:
        ATR en pips (float), ou None si pas assez de bougies.
    """
    h_list = list(highs)
    l_list = list(lows)
    atr_price = _atr_from_series(h_list, l_list, n=lookback)
    if atr_price is None:
        return None
    return atr_price * pip_multiplier


def classify_atr(
    atr_pips: float | None,
    *,
    thresholds: tuple[float, float, float, float] | None = None,
) -> int:
    """Classe un ATR en entier 0/1/2/3.

    Returns:
        0 (LOW) si atr < P25
        1 (NORMAL) si P25 <= atr < P50
        2 (HIGH) si P50 <= atr < P95
        3 (EXTREME) si atr >= P95
        -1 si atr_pips est None (données insuffisantes → conservateur EXTREME)
    """
    if atr_pips is None:
        return -1
    p25, p50, p75, p95 = thresholds or DEFAULT_THRESHOLDS_PIPS
    if atr_pips < p25:
        return 0
    if atr_pips < p50:
        return 1
    if atr_pips < p95:
        # p95 borne supérieure — entre P50 et P95 = HIGH
        return 2
    return 3


def detect_vol_regime(
    highs: Iterable[float],
    lows: Iterable[float],
    *,
    pip_multiplier: float = DEFAULT_PIPS_MULTIPLIER,
    thresholds: tuple[float, float, float, float] | None = None,
) -> VolRegimeLabel:
    """Calcule l'ATR-30 et classifie le régime de volatilité.

    Args:
        highs: séquence des high (au moins 30 bougies).
        lows:  séquence des low.
        pip_multiplier: 10000 ou 100 (cf. pips_multiplier_for_symbol).
        thresholds: 4-tuple (P25, P50, P75, P95) en pips. None = défaut.

    Returns:
        Label ∈ {"LOW", "NORMAL", "HIGH", "EXTREME"}.
        "EXTREME" est le défaut conservateur si données insuffisantes.
    """
    atr_pips = compute_atr_pips(highs, lows, pip_multiplier=pip_multiplier)
    level = classify_atr(atr_pips, thresholds=thresholds)
    return _LEVEL_TO_LABEL.get(level, "EXTREME")


_LEVEL_TO_LABEL: dict[int, VolRegimeLabel] = {
    0: "LOW",
    1: "NORMAL",
    2: "HIGH",
    3: "EXTREME",
    -1: "EXTREME",  # conservateur quand pas de données
}


def compute_atr_and_regime(
    highs: Iterable[float],
    lows: Iterable[float],
    *,
    pip_multiplier: float = DEFAULT_PIPS_MULTIPLIER,
    thresholds: tuple[float, float, float, float] | None = None,
) -> dict[str, float | int | str | None]:
    """Calcule ATR + label + level en une seule passe (utilisé par l'orchestrateur).

    Returns:
        dict avec clés:
          - atr_pips  (float | None)
          - level     (int ∈ {-1, 0, 1, 2, 3})
          - regime    ("LOW" / "NORMAL" / "HIGH" / "EXTREME")
    """
    atr_pips = compute_atr_pips(highs, lows, pip_multiplier=pip_multiplier)
    level = classify_atr(atr_pips, thresholds=thresholds)
    return {
        "atr_pips": atr_pips,
        "level": level,
        "regime": _LEVEL_TO_LABEL.get(level, "EXTREME"),
    }
