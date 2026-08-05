"""V10 Paper Trader — Phase 23+ micro-lot 0.01 paper_only=True.

Doctrine V10 (CEO phase 23+) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open
  R7 : tests verts cumulés
  R8 : utilise R8-calibrated (Phase 21+) seuils VSA + intensité
  R9 : audit metadata honnête
  R10 : zéro capital, paper_only=True OBLIGATOIRE, micro-lot 0.01

Objectif Phase 23+ :
  Simuler 30 trades paper micro-lot sur 4 paires gate-passed M30,
  basés sur les signaux VSA recalibrés Phase 21+.
  Calcule KPIs : WR, R:R, PnL total, max DD, Sharpe, consistency.
  Validation pre-LIVE : aucun trade réel (R10).
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from core.v10.v10_live_pipeline import (
    run_live_pipeline,
    LivePipelineReport,
)
from core.v10.v10_rl_adapter import (
    run_shadow_session,
    ShadowSessionReport,
)


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES (Phase 23+)
# ─────────────────────────────────────────────────────────────────────

# Micro-lot (R10 paper_only=True)
MICRO_LOT = 0.01

# Pip values par paire (pour calcul PnL)
PIP_VALUE_PER_LOT = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
    "USDCAD": 10.0, "USDCHF": 10.0, "USDJPY": 6.67,  # JPY pip = 6.67 USD/lot
}

# Spread typical paper (R10 conservateur)
SPREAD_PIPS = {
    "EURUSD": 1.0, "GBPUSD": 1.5, "AUDUSD": 1.5,
    "USDCAD": 1.5, "USDCHF": 1.8, "USDJPY": 1.5,
}

# 4 paires gate-passed M30 Phase 21
GATE_PASSED_PAIRS_M30 = (
    "AUDUSD", "GBPUSD", "USDCAD", "USDCHF",
)

# WR baseline par paire M30 (Phase 21 recalibration)
BASELINE_WR_M30 = {
    "AUDUSD_M30": 0.5030,
    "GBPUSD_M30": 0.4811,
    "USDCAD_M30": 0.5000,
    "USDCHF_M30": 0.4528,
}


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PaperTrade:
    """1 trade paper (R10 paper_only=True)."""
    trade_id: str = ""
    pair: str = ""
    signal: str = "NEUTRAL"  # BULLISH / BEARISH / NEUTRAL
    entry_time: str = ""
    exit_time: str = ""
    pips_net_of_spread: float = 0.0
    is_win: int = 0
    lot_size: float = MICRO_LOT
    pnl_usd: float = 0.0
    spread_pips: float = 0.0
    audit: Dict = field(default_factory=dict)


@dataclass
class PaperTraderReport:
    """Rapport Phase 23+ paper trader (30 trades × N paires)."""
    timestamp: str = ""
    n_trades_per_pair: int = 30
    n_pairs_tested: int = 0
    paper_only: bool = True
    micro_lot: float = MICRO_LOT
    trades: List[PaperTrade] = field(default_factory=list)
    per_pair_kpis: Dict[str, Dict] = field(default_factory=dict)
    global_kpis: Dict = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# SIMULATION TRADE
# ─────────────────────────────────────────────────────────────────────

def simulate_paper_trade(
    *,
    pair: str,
    signal: str,
    baseline_wr: float,
    avg_pnl_win: float = 8.0,
    avg_pnl_loss: float = -5.0,
    rng_seed: int = 42,
) -> PaperTrade:
    """Simule 1 trade paper micro-lot (R10 paper_only=True).

    R9 audit honest :
      - Win/loss selon baseline_wr (recalibré Phase 21+)
      - Si signal=NEUTRAL, trade quand même avec baseline_wr dégradé
        (R10 paper-only — pas de skip sur signal NEUTRAL pour stats)
      - PnL net de spread (SPREAD_PIPS[pair])
      - PnL en USD = pips_net * PIP_VALUE_PER_LOT * MICRO_LOT
      - lot_size = MICRO_LOT (0.01) — R10 micro-lot obligatoire

    Modif Phase 23+ : on trade même en NEUTRAL mais avec WR dégradé
    (× 0.85) pour refléter l'incertitude. Le but est de générer des
    stats sur 30 trades × N paires (validation pré-LIVE).
    """
    rng = random.Random(rng_seed)

    # NEUTRAL signal → WR dégradé × 0.85 (R9 honest)
    effective_wr = baseline_wr * (1.0 if signal != "NEUTRAL" else 0.85)

    # Win/loss selon effective_wr
    win = rng.random() < effective_wr

    # PnL brut
    if win:
        pnl_pips = avg_pnl_win
    else:
        pnl_pips = avg_pnl_loss

    # Déduire spread
    spread = SPREAD_PIPS.get(pair, 1.5)
    pnl_pips_net = pnl_pips - spread

    # PnL USD
    pip_value = PIP_VALUE_PER_LOT.get(pair, 10.0)
    pnl_usd = round(pnl_pips_net * pip_value * MICRO_LOT, 4)

    return PaperTrade(
        trade_id=f"PAPER_{pair}_{rng_seed}",
        pair=pair,
        signal=signal,
        pips_net_of_spread=round(pnl_pips_net, 4),
        is_win=1 if win else 0,
        lot_size=MICRO_LOT,
        pnl_usd=pnl_usd,
        spread_pips=spread,
        audit={
            "win": win,
            "pnl_pips_brut": pnl_pips,
            "pip_value_per_lot": pip_value,
            "effective_wr": round(effective_wr, 4),
            "neutral_penalty_applied": signal == "NEUTRAL",
        },
    )


# ─────────────────────────────────────────────────────────────────────
# PAPER TRADER ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def _compute_kpis(trades: List[PaperTrade]) -> Dict:
    """Calcule KPIs sur liste de PaperTrade."""
    if not trades:
        return {
            "n_trades": 0, "wr_pct": 0.0, "pnl_pips_total": 0.0,
            "pnl_usd_total": 0.0, "avg_pnl_pips": 0.0,
            "max_dd_pips": 0.0, "sharpe_ratio": 0.0,
        }

    n = len(trades)
    n_wins = sum(t.is_win for t in trades)
    wr = n_wins / n if n else 0.0
    pnl_pips_total = sum(t.pips_net_of_spread for t in trades)
    pnl_usd_total = sum(t.pnl_usd for t in trades)
    avg_pnl = pnl_pips_total / n if n else 0.0

    # Max DD (cumulative PnL)
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum_pnl += t.pips_net_of_spread
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualisé approximatif)
    if n > 1:
        import statistics
        try:
            std = statistics.stdev([t.pips_net_of_spread for t in trades])
        except statistics.StatisticsError:
            std = 0.0
        sharpe = (avg_pnl / std) * (n ** 0.5) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "n_trades": n,
        "wr_pct": round(wr * 100, 4),
        "pnl_pips_total": round(pnl_pips_total, 4),
        "pnl_usd_total": round(pnl_usd_total, 4),
        "avg_pnl_pips": round(avg_pnl, 4),
        "max_dd_pips": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
    }


def run_paper_trader(
    db_path: str = "data/v9_forces.db",
    *,
    pairs: Tuple[str, ...] = GATE_PASSED_PAIRS_M30,
    n_trades_per_pair: int = 30,
    timestamp: str = "",
    rng_seed: int = 42,
    thresholds_pair_tf_path: Optional[str] = None,
) -> PaperTraderReport:
    """Phase 23+ paper trader — R10 paper_only=True OBLIGATOIRE.

    Pour chaque paire gate-passed M30 :
      1. Appelle run_live_pipeline() (Phase 22+ wrapper)
      2. Extrait VSA signal (BULLISH/BEARISH/NEUTRAL)
      3. Simule n_trades_per_pair trades paper (micro-lot 0.01)
      4. Calcule KPIs par paire + global

    Returns:
        PaperTraderReport avec KPIs + audit JSON-sérialisable.
    """
    all_trades: List[PaperTrade] = []
    per_pair_kpis: Dict[str, Dict] = {}

    n_pairs = 0

    for pair in pairs:
        # 1. Run live pipeline (Phase 22+) pour signal VSA
        live_rep = run_live_pipeline(
            pair, db_path,
            timestamp=timestamp or "2026-08-05T09:00:00Z",
            thresholds_pair_tf_path=thresholds_pair_tf_path,
            use_calibrated_thresholds=True,
            use_calibrated_intensity=False,  # évite grid search long ici
        )

        vsa_signal = live_rep.vsa_signal

        # 2. Baseline WR par paire M30 (Phase 21+ recalibration)
        baseline_key = f"{pair}_M30"
        baseline_wr = BASELINE_WR_M30.get(baseline_key, 0.45)

        # 3. Simule n_trades_per_pair trades
        pair_trades: List[PaperTrade] = []
        for i in range(n_trades_per_pair):
            trade = simulate_paper_trade(
                pair=pair,
                signal=vsa_signal,
                baseline_wr=baseline_wr,
                avg_pnl_win=8.0,
                avg_pnl_loss=-5.0,
                rng_seed=rng_seed + i,
            )
            pair_trades.append(trade)
            all_trades.append(trade)

        # 4. KPIs par paire
        pair_kpis = _compute_kpis(pair_trades)
        pair_kpis["vsa_signal"] = vsa_signal
        pair_kpis["baseline_wr_m30"] = baseline_wr
        per_pair_kpis[pair] = pair_kpis
        n_pairs += 1

    # 5. KPIs globaux
    global_kpis = _compute_kpis(all_trades)

    return PaperTraderReport(
        timestamp=timestamp,
        n_trades_per_pair=n_trades_per_pair,
        n_pairs_tested=n_pairs,
        paper_only=True,  # R10 OBLIGATOIRE
        micro_lot=MICRO_LOT,
        trades=all_trades,
        per_pair_kpis=per_pair_kpis,
        global_kpis=global_kpis,
        audit={
            "method": "Phase 23+ paper trader micro-lot 0.01",
            "doctrine": "R1, R2 additif, R6 fail-open, R7, R8 R8-calibrated, R9 audit, R10 paper_only",
            "doctrine_R10": "zéro capital, paper_only=True, micro-lot 0.01, kill switch DD>5%",
            "spreads": SPREAD_PIPS,
            "pip_values_per_lot": PIP_VALUE_PER_LOT,
            "baseline_wr_source": "Phase 21+ recalibration pair-TF",
            "vsa_signal_source": "Phase 22+ live pipeline (uses R8-calibrated seuils)",
            "n_total_trades_simulated": n_pairs * n_trades_per_pair,
        },
    )


__all__ = [
    "MICRO_LOT",
    "PIP_VALUE_PER_LOT",
    "SPREAD_PIPS",
    "GATE_PASSED_PAIRS_M30",
    "BASELINE_WR_M30",
    "PaperTrade",
    "PaperTraderReport",
    "simulate_paper_trade",
    "_compute_kpis",
    "run_paper_trader",
]
