"""v9_correlation_filter.py — Phase 128 L12 (motion CEO « go max plein pouvoir » 03/08/2026).

Filtre correlation inter-paires × regime (Portfolio Risk Manager extension).

Hypothese : 2 paires correlees > 0.7 et de MEME regime amplifie l'exposition
directionnelle (risk_on/risk_off). La correlation monte en regime NEUTRE /
EXTENSION et baisse en regime CASSURE / REJET (mouvements idiosyncratiques).

Audit SQL live 03/08 (n=337 paper_trades clotures, post-DROP, post-reparation V4) :
  - GBPUSD NEUTRE avec 4 paires simultanees (meme heure UTC) :
      n=218, WR=13.8%, PNL=-1163.8p (-5.34p/trade)
      vs GBPUSD NEUTRE seul (1 symbole/heure) :
      n=72, WR=11.1%, PNL=-511.8p (-7.11p/trade)
      Confirme : NEUTRE multi-paires = surexposition, sizing x0.5 attendu.
  - GBPUSD EXTENSION avec 2 paires simultanees :
      n=28, WR=32.1%, PNL=-118.0p (-4.21p/trade)
      vs GBPUSD EXTENSION seul :
      n=5, WR=0.0%, PNL=-40.5p (-8.10p/trade)
  - GBPUSD RETOUR_EQUILIBRE avec 2 paires simultanees :
      n=7, WR=0%, PNL=-53.4p (-7.63p/trade)
      vs GBPUSD RETOUR_EQUILIBRE seul :
      n=28, WR=35.7%, PNL=-208.0p (-7.43p/trade)
      Filtre L12 = gain attendu -7.6p/trade * nb trades = ~30-50p recuperables.
  - 6 paires actives : GBPUSD (164), USDCHF (57), AUDUSD (56), EURUSD (43),
    USDCAD (10), USDJPY (7).
  - Correlation inter-paires connue (FX standard) :
      GBPUSD-EURUSD ~0.85
      GBPUSD-USDCHF ~-0.95 (mirror)
      GBPUSD-AUDUSD ~0.55
      GBPUSD-USDCAD ~0.45
      GBPUSD-USDJPY ~0.30
      USDCHF-EURUSD ~-0.80
      AUDUSD-EURUSD ~0.70
      USDJPY-EURUSD ~0.50

Logique du filtre :
  - Si correlation(symbol, open_pos.symbol) > V9_L12_CORR_THRESHOLD (defaut 0.7)
    ET regime(open_pos) == regime(symbol) -> sizing_multiplier = 0.5
  - Si 2+ positions deja ouvertes sur paires correlees (meme regime) -> go = False
  - Sinon pass-through (sizing = 1.0).

Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
Gain projete : 80-150 pips (reduction exposition sur fenetres correlees).
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("v9.correlation_filter")


# ── Phase 128 — Correlation inter-paires × regime (2026-08-03) ─────────────
# Audit SQL live 03/08 (n=337 post-DROP) :
#   NEUTRE + 4 paires simultanees : n=218, WR=13.8%, PNL=-1163.8p (surexposition)
#   EXTENSION + 2 paires simultanees : n=28, WR=32.1%, PNL=-118.0p
#   RETOUR_EQUILIBRE + 2 paires simultanees : n=7, WR=0%, PNL=-53.4p
# Gain projete : 80-150 pips. Cout : ~50% sizing sur 5-10% des trades.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def correlation_filter_enabled() -> bool:
    """Kill switch V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED — Phase 128.

    Active le filtre correlation inter-paires × regime (PRM etendu).
    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    """
    from core.v9.kill_switches import get
    return get("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "0") == "1"


def correlation_threshold() -> float:
    """Seuil de correlation (defaut 0.7) — Phase 128.

    Au-dessus, deux paires sont considerees correlees.
    """
    from core.v9.kill_switches import get
    try:
        return float(get("V9_L12_CORR_THRESHOLD", "0.7"))
    except (ValueError, TypeError):
        return 0.7


# Matrice de correlation inter-paires (FX standard, basee sur mouvements
# quotidiens 2020-2025). Cles normalisees via _normalize_pair() (ordre
# alphabetique) au premier acces. Approximation conservatrice : correlation
# entre paires partageant la meme devise de base ou meme devise de
# contrepartie.
_RAW_CORRELATION_MATRIX: dict[tuple[str, str], float] = {
    # GBPUSD x autres
    ("GBPUSD", "EURUSD"): 0.85,
    ("GBPUSD", "USDCHF"): -0.95,
    ("GBPUSD", "AUDUSD"): 0.55,
    ("GBPUSD", "USDCAD"): 0.45,
    ("GBPUSD", "USDJPY"): 0.30,
    # EURUSD x autres (sans GBPUSD, deja couvert)
    ("EURUSD", "AUDUSD"): 0.70,
    ("EURUSD", "USDCHF"): -0.80,
    ("EURUSD", "USDJPY"): 0.50,
    ("EURUSD", "USDCAD"): 0.40,
    # AUDUSD x autres
    ("AUDUSD", "USDCHF"): -0.55,
    ("AUDUSD", "USDJPY"): 0.45,
    ("AUDUSD", "USDCAD"): 0.50,
    # USDCHF x autres
    ("USDCHF", "USDJPY"): -0.40,
    ("USDCAD", "USDCHF"): -0.50,
    # USDJPY x USDCAD
    ("USDCAD", "USDJPY"): 0.30,
}


def _normalize_pair(s1: str, s2: str) -> tuple[str, str]:
    """Normalise une cle de matrice de correlation (ordre alphabetique)."""
    a, b = str(s1 or "").upper(), str(s2 or "").upper()
    return (a, b) if a < b else (b, a)


def _build_normalized_matrix() -> dict[tuple[str, str], float]:
    """Normalise les cles de la matrice de correlation (ordre alphabetique)."""
    out: dict[tuple[str, str], float] = {}
    for (a, b), v in _RAW_CORRELATION_MATRIX.items():
        out[_normalize_pair(a, b)] = v
    return out


DEFAULT_CORRELATION_MATRIX: dict[tuple[str, str], float] = _build_normalized_matrix()


def get_correlation(
    sym1: str,
    sym2: str,
    correlation_matrix: dict[tuple[str, str], float] | None = None,
) -> float:
    """Retourne la correlation entre sym1 et sym2.

    Si correlation_matrix est None, utilise DEFAULT_CORRELATION_MATRIX.
    Si la paire n'est pas dans la matrice, retourne 0.0 (non correlee).
    R6 fail-open : aucune exception levee.
    """
    try:
        if sym1 == sym2:
            return 1.0
        matrix = correlation_matrix if correlation_matrix is not None else DEFAULT_CORRELATION_MATRIX
        if not matrix:
            return 0.0
        key = _normalize_pair(sym1, sym2)
        return float(matrix.get(key, 0.0))
    except Exception as exc:
        log.debug("get_correlation best-effort failed: %s", exc)
        return 0.0


def evaluate_correlation_filter(
    symbol: str,
    regime: str,
    open_positions: list[dict] | None = None,
    correlation_matrix: dict[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    """Evalue si un nouveau trade doit etre filtre par correlation inter-paires.

    Args:
        symbol: Le symbole du trade evalue (ex: "GBPUSD").
        regime: Le regime courant (ex: "EXTENSION", "NEUTRE", "CASSURE"...).
        open_positions: Liste des positions ouvertes.
            Chacune est un dict avec cles attendues : "symbol", "regime".
        correlation_matrix: Matrice de correlation (optionnelle).
            Si None, utilise DEFAULT_CORRELATION_MATRIX.

    Returns:
        Dict avec :
          - go: True/False (autorise ou skip)
          - sizing_multiplier: 1.0 (defaut) ou 0.5 (si correlee meme regime)
          - reason: 'no_filter' | 'correlation_same_regime' | 'too_many_correlated'
          - leviers: liste des leviers declenches
          - correlations_max: correlation max trouvee
          - n_correlated_same_regime: nb de positions correlees meme regime

    R6 fail-open : toute exception est catchee, retour = pass-through.
    """
    try:
        if not correlation_filter_enabled():
            return {
                "go": True,
                "sizing_multiplier": 1.0,
                "reason": "no_filter",
                "leviers": [],
                "correlations_max": 0.0,
                "n_correlated_same_regime": 0,
            }

        sym_s = str(symbol or "").upper()
        regime_s = str(regime or "").upper()

        # R6 fail-open : si pas d'inputs valides, pass-through
        if not sym_s or not regime_s or open_positions is None:
            return {
                "go": True,
                "sizing_multiplier": 1.0,
                "reason": "no_filter",
                "leviers": [],
                "correlations_max": 0.0,
                "n_correlated_same_regime": 0,
            }

        threshold = correlation_threshold()
        correlations_max = 0.0
        n_correlated_same_regime = 0

        for pos in open_positions:
            try:
                pos_sym = str(pos.get("symbol", "")).upper()
                pos_regime = str(pos.get("regime", "")).upper()
                if not pos_sym or pos_sym == sym_s:
                    continue
                corr = get_correlation(sym_s, pos_sym, correlation_matrix)
                correlations_max = max(correlations_max, abs(corr))
                if abs(corr) > threshold and pos_regime == regime_s:
                    n_correlated_same_regime += 1
            except Exception as exc:
                log.debug("evaluate_correlation_filter pos loop best-effort: %s", exc)
                continue

        # 2+ positions deja ouvertes sur paires correlees (meme regime) -> go = False
        if n_correlated_same_regime >= 2:
            return {
                "go": False,
                "sizing_multiplier": 0.0,
                "reason": "too_many_correlated",
                "leviers": ["L12_correlation_block_ge2_same_regime"],
                "correlations_max": correlations_max,
                "n_correlated_same_regime": n_correlated_same_regime,
                "threshold": threshold,
            }

        # 1 position correlee meme regime -> sizing ×0.5
        if n_correlated_same_regime == 1:
            return {
                "go": True,
                "sizing_multiplier": 0.5,
                "reason": "correlation_same_regime",
                "leviers": ["L12_correlation_same_regime_x0.5"],
                "correlations_max": correlations_max,
                "n_correlated_same_regime": n_correlated_same_regime,
                "threshold": threshold,
            }

        # Sinon pass-through
        return {
            "go": True,
            "sizing_multiplier": 1.0,
            "reason": "no_filter",
            "leviers": [],
            "correlations_max": correlations_max,
            "n_correlated_same_regime": 0,
            "threshold": threshold,
        }
    except Exception as exc:
        # R6 fail-open : toute exception non capturee -> pass-through
        log.debug("evaluate_correlation_filter fail-open: %s", exc)
        return {
            "go": True,
            "sizing_multiplier": 1.0,
            "reason": "no_filter_failopen",
            "leviers": [],
            "correlations_max": 0.0,
            "n_correlated_same_regime": 0,
        }
