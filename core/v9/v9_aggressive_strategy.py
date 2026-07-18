"""v9_aggressive_strategy — TP/SL dynamique calibré sur la magnitude RÉELLE.

Chantier 1 du « saut quantique agressif » (2026-07-18), **recadré** par motion
CEO le même jour :

  - Le prompt initial demandait d'extraire la magnitude depuis
    ``decisions.resolution_pips`` — mais cette colonne est CAPÉE (P50=P75=P90
    = 9.50 pips, max 15.5) : elle reflète la stratégie de résolution, pas
    l'excursion réelle du marché. Ce module reconstruit donc la magnitude à
    partir des chandeliers OHLC forward de ``forces_snapshots`` (MFE/MAE).
  - Couche **backtest lecture-seule** : aucun câblage dans ``trade_engine``,
    aucune exécution live (Phase 12 gelée). Consommé par
    ``scripts/v9_aggressive_paper_trade.py``.
  - **Garde-fou short régime-dépendant** : la direction baissière n'est
    autorisée qu'en régime CASSURE/EXTENSION (motion CEO — les shorts NEUTRE
    du live perdent, cf. paper_trades). Sinon ``short_gated=True`` et le
    sizing en aval force la taille à 0.

Doctrine : R2 (additif, clés ``*_aggressive``), R6 (try/except + fallback
conservateur), R18 (stdlib pure : sqlite3 + math), R30 (bornes dures).
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ constantes

AGGRESSIVE_STRATEGY_VERSION = "1.0"

# Bornes TP/SL (motion : TP ∈ [10,30], SL serré ∈ [8,18]).
AGGR_TP_MIN = 10.0
AGGR_TP_MAX = 30.0
AGGR_SL_MIN = 8.0
AGGR_SL_MAX = 18.0

# TP dynamique = max(percentile magnitude, k_vol · vol_atr, TP_MIN) borné.
AGGR_K_VOL = 1.5
# Percentile de MFE utilisé comme cible réaliste atteignable.
AGGR_TP_PERCENTILE = "p75"
# SL = ratio · TP · facteur_phase, borné [SL_MIN, SL_MAX].
AGGR_SL_TP_RATIO = 0.8

# Facteur SL par phase : climax (culmination) → SL large (bruit), trend serré.
PHASE_SL_FACTOR: dict[str, float] = {
    "culmination": 1.0,     # climax : laisser respirer
    "resolution": 0.9,
    "developpement": 0.8,
    "initiation": 0.75,     # trend naissant : SL serré
}

# Shorts autorisés uniquement dans ces régimes (motion CEO 2026-07-18).
BEARISH_ALLOWED_REGIMES = ("CASSURE", "EXTENSION")

# Nombre minimal d'observations pour faire confiance à une cellule magnitude.
MIN_N_MAGNITUDE = 20

VALID_PHASES = ("culmination", "developpement", "initiation", "resolution")
VALID_REGIMES = ("NEUTRE", "RETOUR_EQUILIBRE", "EXTENSION", "PALIER", "CASSURE", "REJET")


# ------------------------------------------------------------------ utilitaires

def _bucket_vol_atr(vol_atr_pips: float | None) -> str:
    """Bucket volatilité aligné sur v9_bayesian_predictor / v9_cycle_memory."""
    if vol_atr_pips is None:
        return "UNKNOWN"
    try:
        v = float(vol_atr_pips)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if v < 0:
        return "UNKNOWN"
    if v <= 2.0:
        return "LOW"
    if v <= 6.0:
        return "MEDIUM"
    return "HIGH"


def _pip_size(symbol: str) -> float:
    """Taille d'un pip : 0.01 pour les paires JPY, 0.0001 sinon."""
    return 0.01 if symbol and symbol.upper().endswith("JPY") else 0.0001


def magnitude_cell_key(symbol: str, timeframe: str, vol_atr_pips: float | None) -> str:
    """Clé de cellule contextuelle pour les stats de magnitude."""
    return f"{symbol}|{timeframe}|{_bucket_vol_atr(vol_atr_pips)}"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Percentile (p ∈ [0,1]) sur une liste DÉJÀ triée. Interpolation linéaire."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = p * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# ------------------------------------------------------------------ dataclasses

@dataclass(frozen=True)
class AggressiveDecision:
    """Décision de stratégie agressive pour un contexte (lecture seule)."""

    symbol: str
    timeframe: str
    regime: str
    phase: str
    direction: str
    vol_atr_bucket: str
    tp: float
    sl: float
    rr_ratio: float                 # TP / SL
    p_win: float                    # proba calibrée fournie (0-1)
    edge: float                     # p·TP - (1-p)·SL (en pips espérés)
    magnitude_source: str           # "cell_p75" | "vol_atr" | "floor_min"
    magnitude_n: int                # n observations de la cellule (0 si fallback)
    short_gated: bool               # True → short interdit hors régime autorisé
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ cœur : TP/SL

def compute_dynamic_tp_sl(
    symbol: str,
    timeframe: str,
    regime: str,
    phase: str,
    vol_atr_pips: float | None,
    magnitude_stats: dict[str, dict[str, float]] | None = None,
) -> tuple[float, float, str, int]:
    """Calcule (tp, sl, source, n) dynamiques calibrés sur la magnitude réelle.

    Args:
        symbol, timeframe, regime, phase : contexte.
        vol_atr_pips : volatilité ATR en pips (proxy taille de mouvement).
        magnitude_stats : dict cellule → {p50,p75,p90,p95,n} issu de
            ``reconstruct_magnitude_stats``. None → fallback vol_atr/floor.

    Returns:
        (tp, sl, magnitude_source, magnitude_n). Bornes dures [10,30]/[8,18].

    R6 : jamais d'exception propagée — fallback conservateur (tp=10, sl=8).
    """
    try:
        cell = magnitude_cell_key(symbol, timeframe, vol_atr_pips)
        stats = (magnitude_stats or {}).get(cell)
        source = "floor_min"
        n = 0

        # Cible TP : percentile de MFE si cellule fiable, sinon k_vol·vol_atr.
        tp_candidates: list[float] = [AGGR_TP_MIN]
        if stats and int(stats.get("n", 0)) >= MIN_N_MAGNITUDE:
            pctl = float(stats.get(AGGR_TP_PERCENTILE, 0.0))
            if pctl > 0:
                tp_candidates.append(pctl)
                source = "cell_" + AGGR_TP_PERCENTILE
                n = int(stats["n"])
        if vol_atr_pips is not None:
            try:
                v = float(vol_atr_pips)
                if v > 0:
                    vol_tp = AGGR_K_VOL * v
                    tp_candidates.append(vol_tp)
                    if source == "floor_min":
                        source = "vol_atr"
            except (TypeError, ValueError):
                pass

        tp = _clamp(max(tp_candidates), AGGR_TP_MIN, AGGR_TP_MAX)

        # SL serré modulé par la phase (climax large, trend serré).
        phase_factor = PHASE_SL_FACTOR.get(phase, 0.85)
        sl = _clamp(AGGR_SL_TP_RATIO * tp * phase_factor, AGGR_SL_MIN, AGGR_SL_MAX)

        return round(tp, 2), round(sl, 2), source, n
    except Exception:
        # Fallback conservateur strict.
        return AGGR_TP_MIN, AGGR_SL_MIN, "fallback_error", 0


def is_short_gated(direction: str, regime: str) -> bool:
    """True si un short doit être bloqué (hors régime autorisé)."""
    if direction not in ("baissiere", "short", "sell", "bear"):
        return False
    return regime not in BEARISH_ALLOWED_REGIMES


def evaluate_aggressive(
    *,
    symbol: str,
    timeframe: str,
    regime: str,
    phase: str,
    direction: str,
    vol_atr_pips: float | None,
    p_win: float,
    magnitude_stats: dict[str, dict[str, float]] | None = None,
) -> AggressiveDecision:
    """Produit une AggressiveDecision complète pour un contexte donné.

    ``p_win`` = proba calibrée (issue de v9_bayesian_predictor.predict). L'edge
    est calculé en pips espérés ; le garde-fou short marque ``short_gated``.
    """
    tp, sl, source, n = compute_dynamic_tp_sl(
        symbol, timeframe, regime, phase, vol_atr_pips, magnitude_stats,
    )
    try:
        p = _clamp(float(p_win), 0.0, 1.0)
    except (TypeError, ValueError):
        p = 0.5
    rr = round(tp / sl, 3) if sl > 0 else 0.0
    edge = round(p * tp - (1.0 - p) * sl, 3)
    gated = is_short_gated(direction, regime)

    bits = [f"tp={tp}", f"sl={sl}", f"rr={rr}", f"p={round(p,3)}", f"edge={edge}", f"src={source}"]
    if gated:
        bits.append("short_gated(regime=%s)" % regime)
    rationale = " ".join(bits)

    return AggressiveDecision(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime if regime in VALID_REGIMES else "NEUTRE",
        phase=phase if phase in VALID_PHASES else "initiation",
        direction=direction,
        vol_atr_bucket=_bucket_vol_atr(vol_atr_pips),
        tp=tp,
        sl=sl,
        rr_ratio=rr,
        p_win=round(p, 4),
        edge=edge,
        magnitude_source=source,
        magnitude_n=n,
        short_gated=gated,
        rationale=rationale,
    )


# ------------------------------------------------------------------ reconstruction OHLC

@dataclass
class MagnitudeCell:
    """Accumulateur de MFE (favorable) pour une cellule contextuelle."""

    mfe_pips: list[float] = field(default_factory=list)
    mae_pips: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float]:
        s = sorted(self.mfe_pips)
        a = sorted(self.mae_pips)
        return {
            "n": float(len(s)),
            "p50": round(_percentile(s, 0.50), 3),
            "p75": round(_percentile(s, 0.75), 3),
            "p90": round(_percentile(s, 0.90), 3),
            "p95": round(_percentile(s, 0.95), 3),
            "mae_p75": round(_percentile(a, 0.75), 3),
            "mae_p90": round(_percentile(a, 0.90), 3),
        }


def compute_atr_pips(bars: list[dict], pip: float, lookback: int = 14) -> float | None:
    """ATR simplifié (moyenne des ranges high-low) en pips sur ``lookback`` bars."""
    if not bars:
        return None
    window = bars[-lookback:] if len(bars) > lookback else bars
    ranges = []
    for b in window:
        try:
            hi = float(b["high"]); lo = float(b["low"])
            if hi >= lo:
                ranges.append((hi - lo) / pip)
        except (KeyError, TypeError, ValueError):
            continue
    if not ranges:
        return None
    return sum(ranges) / len(ranges)


def _forward_excursion(
    entry_close: float, direction: str, forward_bars: list[dict], pip: float,
) -> tuple[float, float]:
    """(MFE, MAE) en pips sur les bars forward, selon la direction."""
    is_long = direction in ("haussiere", "long", "buy", "bull")
    mfe = 0.0
    mae = 0.0
    for b in forward_bars:
        try:
            hi = float(b["high"]); lo = float(b["low"])
        except (KeyError, TypeError, ValueError):
            continue
        if is_long:
            mfe = max(mfe, (hi - entry_close) / pip)
            mae = max(mae, (entry_close - lo) / pip)
        else:
            mfe = max(mfe, (entry_close - lo) / pip)
            mae = max(mae, (hi - entry_close) / pip)
    return max(mfe, 0.0), max(mae, 0.0)


def reconstruct_magnitude_stats(
    db_path: Path | str,
    *,
    horizon_bars: int = 12,
    atr_lookback: int = 14,
) -> dict[str, dict[str, float]]:
    """Reconstruit les stats de magnitude RÉELLE par cellule depuis l'OHLC.

    Pour chaque décision résolue, on récupère la barre d'entrée (bar_time du
    snapshot) puis les ``horizon_bars`` barres closes suivantes du même
    (symbol, timeframe) ; on calcule MFE/MAE forward, et on bucket par
    volatilité ATR estimée sur les barres précédentes.

    Returns:
        dict cellule → {n, p50, p75, p90, p95, mae_p75, mae_p90}. En cas
        d'erreur DB, renvoie {} (R6 — le module aval retombe sur vol_atr).
    """
    cells: dict[str, MagnitudeCell] = {}
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Décisions résolues + leur barre d'entrée.
        decisions = cur.execute(
            """
            SELECT d.symbol, d.timeframe, d.direction, f.bar_time AS entry_bt,
                   f.close AS entry_close
            FROM decisions d
            JOIN forces_snapshots f ON d.snapshot_id = f.snapshot_id
            WHERE d.is_win IS NOT NULL
              AND f.close IS NOT NULL AND f.bar_time IS NOT NULL
            """
        ).fetchall()

        # Cache des barres closes par (symbol, timeframe), triées par bar_time.
        bars_cache: dict[tuple[str, str], list[dict]] = {}

        def _load_bars(sym: str, tf: str) -> list[dict]:
            key = (sym, tf)
            if key not in bars_cache:
                rows = cur.execute(
                    """
                    SELECT DISTINCT bar_time, open, high, low, close
                    FROM forces_snapshots
                    WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
                      AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
                    ORDER BY bar_time
                    """,
                    (sym, tf),
                ).fetchall()
                bars_cache[key] = [dict(r) for r in rows]
            return bars_cache[key]

        # Index bar_time → position, par (symbol, tf).
        index_cache: dict[tuple[str, str], dict[int, int]] = {}

        def _index(sym: str, tf: str) -> dict[int, int]:
            key = (sym, tf)
            if key not in index_cache:
                bars = _load_bars(sym, tf)
                index_cache[key] = {int(b["bar_time"]): i for i, b in enumerate(bars)}
            return index_cache[key]

        for d in decisions:
            sym = d["symbol"]; tf = d["timeframe"]; direction = d["direction"]
            entry_bt = int(d["entry_bt"]); entry_close = float(d["entry_close"])
            pip = _pip_size(sym)
            bars = _load_bars(sym, tf)
            idx = _index(sym, tf).get(entry_bt)
            if idx is None:
                continue
            prior = bars[:idx + 1]
            forward = bars[idx + 1: idx + 1 + horizon_bars]
            if not forward:
                continue
            vol_atr = compute_atr_pips(prior, pip, atr_lookback)
            mfe, mae = _forward_excursion(entry_close, direction, forward, pip)
            cell = magnitude_cell_key(sym, tf, vol_atr)
            cells.setdefault(cell, MagnitudeCell()).mfe_pips.append(mfe)
            cells[cell].mae_pips.append(mae)

        con.close()
    except Exception:
        return {}

    return {k: v.summary() for k, v in cells.items() if v.mfe_pips}
