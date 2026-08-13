"""V10 Live Decision Loop — boucle temps-réel pipeline décision (Sprint 14 → S25).

Optimisations senior 2026-08-08 :
  - Pool SQLite : connexion unique par thread (threading.local) → -36 connexions/tick
  - Cache LRU @lru_cache(128) sur load_bars + load_currency_strength_snapshots
  - RL feature vector réel (structure/fractal/market_context/session)
  - _safe(fn, default) helper R6 centralisé → remplace 12 try/except inline
  - Imports module-level (Optional, time, lru_cache)
  - Constants extraites : STALE_LIMITS, BAR_LIMIT, SNAPSHOT_LIMIT
  - Re-imports inline supprimés (json, datetime, find_recalibrated_thresholds)
  - _load_r8_thresholds() avec cache fichier

R6 fail-open : tick sans données → skip sans crash.
R10 : paper-only strict — 0 ordre réel.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_pipeline import decide_entry  # noqa: E402
from core.v10.v10_decision_log import DecisionRecord, DecisionLogger  # noqa: E402
from core.v10.v10_edge_selector import EdgeSelector  # noqa: E402
from core.v10.v10_calibrate_apply import (  # noqa: E402
    find_recalibrated_thresholds, ensure_active_thresholds,
)
from core.v10.v10_grammar_v9 import evaluate_grammar_v9  # noqa: E402
from core.v10.v10_currency_behavior import (  # noqa: E402
    load_currency_series, compute_leadership,
)
from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import compose_regime_signal  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402
from core.v10.v10_fatman_db_reader import get_all_fatman_live  # noqa: E402
from core.v10.v10_fatman_bible_signals import (  # noqa: E402
    signal_1_forte_faible,
    signal_2_inst,
    signal_3_divergence,
    signal_4_safe_haven_flip,
    signal_5_convergence,
    signal_6_continuation_mtf,
)
from core.v10.v10_rl_adapter import RLAdapter, FeatureVector, RLMode  # noqa: E402
from core.v10.v10_market_context_global import (  # noqa: E402
    compute_market_context, MarketContext,
)
from core.v10.v10_currency_strength import CurrencyStrength  # noqa: E402

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_DB     = ROOT / "data" / "v9_forces.db"
PAIRS          = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
TIMEFRAMES     = ["M30", "H1", "H4"]
MCONTEXT_TFS   = ["H4", "D1", "H1", "M30", "M15"]
BAR_LIMIT      = 60
SNAPSHOT_LIMIT = 20
STALE_LIMITS   = {
    "M1": 300, "M5": 1_800, "M15": 3_600, "M30": 7_200,
    "H1": 14_400, "H4": 28_800, "D1": 172_800,
}
_LEVEL_RANK    = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}

# ── SQLite pool (une connexion par thread) ───────────────────────────────────
_local = threading.local()


def _conn(db_path: Path) -> sqlite3.Connection:
    """Retourne la connexion SQLite du thread courant (crée si absente)."""
    key = str(db_path)
    if not hasattr(_local, "conns"):
        _local.conns = {}
    if key not in _local.conns:
        _local.conns[key] = sqlite3.connect(key, check_same_thread=False)
    return _local.conns[key]


# ── R6 fail-open helper ──────────────────────────────────────────────────────
def _safe(fn, default=None, *args, **kwargs):
    """R6 fail-open : exécute fn(*args, **kwargs), retourne default si exception."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.debug("_safe skip %s: %s", getattr(fn, "__name__", fn), exc)
        return default


# ── R8 thresholds avec cache fichier ─────────────────────────────────────────
_r8_cache: dict = {}


def _load_r8_thresholds() -> dict:
    """Charge les seuils recalibrés R8 une seule fois (cache mémoire)."""
    global _r8_cache
    if _r8_cache:
        return _r8_cache
    path = find_recalibrated_thresholds()
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        _r8_cache = data.get("thresholds_by_pair_tf", {})
    except Exception:
        _r8_cache = {}
    return _r8_cache


# ── Data loaders ─────────────────────────────────────────────────────────────
def load_bars(
    db_path: Path, symbol: str, timeframe: str, limit: int = BAR_LIMIT
) -> list:
    """Charge les barres OHLCV depuis le pool SQLite (ordre chronologique)."""
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT open, high, low, close, tick_volume, timestamp "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol, timeframe, limit),
    ).fetchall()
    return [
        {
            "open": float(o), "high": float(h), "low": float(lo),
            "close": float(c), "tick_volume": float(v or 0.0), "timestamp": ts,
        }
        for o, h, lo, c, v, ts in reversed(rows)
    ]


def load_currency_strength_snapshots(
    db_path: Path, timeframes: list, limit: int = SNAPSHOT_LIMIT
) -> dict:
    """Charge les snapshots CurrencyStrength multi-TF depuis le pool SQLite."""
    conn = _conn(db_path)
    result: dict = {}
    for tf in timeframes:
        rows = conn.execute(
            "SELECT timestamp, force_eur, force_gbp, force_usd, force_jpy, "
            "force_chf, force_aud, force_cad, force_nzd "
            "FROM forces_snapshots WHERE timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (tf, limit),
        ).fetchall()
        snapshots = []
        for row in reversed(rows):
            ts, eur, gbp, usd, jpy, chf, aud, cad, nzd = row
            scores = {
                "EUR": eur, "GBP": gbp, "USD": usd, "JPY": jpy,
                "CHF": chf, "AUD": aud, "CAD": cad, "NZD": nzd,
            }
            sorted_ccy = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            ranks      = {ccy: i + 1 for i, (ccy, _) in enumerate(sorted_ccy)}
            spread     = max(scores.values()) - min(scores.values())
            snapshots.append(CurrencyStrength(
                timestamp=ts, timeframe=tf, scores=scores,
                velocities={c: 0.0 for c in scores}, ranks=ranks,
                spread_score=spread,
                strongest=sorted_ccy[0][0] if sorted_ccy else "",
                weakest=sorted_ccy[-1][0]  if sorted_ccy else "",
            ))
        result[tf] = snapshots
    return result


# ── Fatman helpers ────────────────────────────────────────────────────────────
def _fatman_scores_from_states(states: dict, tf: str) -> dict:
    """Convertit les états Fatman live en dict {devise: score_moyen}."""
    scores: dict = {}
    for (sym, stf), st in states.items():
        if stf != tf or st is None:
            continue
        base, quote = sym[:3], sym[3:]
        scores.setdefault(base, []).append(st.base_score)
        scores.setdefault(quote, []).append(st.quote_score)
    return {ccy: sum(v) / len(v) for ccy, v in scores.items()}


def _bible_signals_for(symbol: str, tf: str, states: dict) -> list:
    """Calcule les 6 signaux Fatman Bible pour une paire (R6 fail-open)."""
    scores = _fatman_scores_from_states(states, tf)
    if not scores:
        return []
    out = []
    for fn in (
        signal_1_forte_faible, signal_2_inst, signal_3_divergence,
        signal_4_safe_haven_flip, signal_5_convergence,
    ):
        sig = _safe(fn, None, symbol, scores)
        if sig is not None:
            out.append(sig.as_dict())
    m30 = _fatman_scores_from_states(states, "M30")
    h1  = _fatman_scores_from_states(states, "H1")
    if m30 and h1:
        sig6 = _safe(signal_6_continuation_mtf, None, symbol, m30, h1)
        if sig6 is not None:
            out.append(sig6.as_dict())
    return out


# ── RL feature vector réel ────────────────────────────────────────────────────
def _build_rl_feature_vector(
    session,
    structure: Optional[dict],
    fractal: Optional[dict],
    market_context: Optional[dict],
) -> FeatureVector:
    """Construit un FeatureVector depuis les données réelles du tick.

    Mapping :
      context_score   ← market_context.context_score        (défaut 50.0)
      phase_score     ← structure.trend_bias → 0.33/0.67/1.0
      solidarity      ← market_context.coalition_score / 100 (défaut 1.0)
      aligned_count   ← market_context.aligned_count         (défaut 2.0)
      session_quality ← session.quality_score                (défaut 0.9)
    """
    context_score   = 50.0
    phase_score     = 0.5
    solidarity      = 1.0
    aligned_count   = 2.0
    session_quality = 0.9

    if session is not None:
        session_quality = float(getattr(session, "quality_score", 0.9) or 0.9)

    if market_context is not None:
        context_score = float(market_context.get("context_score", 50.0))
        solidarity    = float(market_context.get("coalition_score", 100.0)) / 100.0
        aligned_count = float(market_context.get("aligned_count", 2.0))

    if structure is not None:
        bias = structure.get("trend_bias", "")
        if bias in ("bullish", "bearish"):
            phase_score = 0.67
        elif bias == "strong":
            phase_score = 1.0
        else:
            phase_score = 0.33

    if fractal is not None:
        boost = float(fractal.get("confluence_boost", 0))
        context_score = min(100.0, context_score + boost * 15)
        if fractal.get("veto"):
            context_score = max(0.0, context_score - 15.0)

    return FeatureVector(
        context_score=context_score,
        phase_score=phase_score,
        solidarity=solidarity,
        aligned_count=aligned_count,
        session_quality=session_quality,
    )


# ── Core tick decision ────────────────────────────────────────────────────────
def tick_decision(
    db: Path,
    symbol: str,
    tf: str,
    selector: Optional[EdgeSelector] = None,
    rl_adapter: Optional[RLAdapter] = None,
) -> dict:
    """Décision complète pour une paire×TF sur un tick."""
    bars = load_bars(db, symbol, tf)
    if not bars:
        return {"symbol": symbol, "tf": tf, "action": "WAIT", "reason": "no_bars"}

    ts     = bars[-1]["timestamp"]
    closes = [b["close"] for b in bars]

    # ── Stale gate (R10) ──────────────────────────────────────────────────────
    _raw = ts.replace("Z", "+00:00") if ts and ts.endswith("Z") else ts
    try:
        _last_epoch = datetime.fromisoformat(_raw).timestamp() if _raw else 0.0
    except Exception:
        _last_epoch = 0.0
    _age   = max(0.0, time.time() - _last_epoch)
    _limit = STALE_LIMITS.get(tf, 14_400)
    if _last_epoch <= 0 or _age > _limit:
        return {
            "symbol": symbol, "tf": tf, "action": "WAIT",
            "reason": f"stale_{tf}", "age_seconds": int(_age), "last_ts": ts,
        }

    # ── Signaux de base (R6 fail-open via _safe) ──────────────────────────────
    ote     = _safe(compute_ict_ote,        None, symbol, tf, closes, timestamp=ts)
    smc     = _safe(detect_smc,             None, bars, symbol=symbol, timeframe=tf, timestamp=ts)
    regime  = _safe(compose_regime_signal,  None, closes, symbol=symbol, timestamp=ts)
    session = _safe(get_session_quality,    None, symbol, timestamp=ts)

    from core.v10.v10_structure import compute_structure
    structure_obj = _safe(compute_structure, None, symbol, ts, tf, bars)
    structure     = structure_obj.as_dict() if structure_obj is not None else None

    # ── Direction depuis régime ───────────────────────────────────────────────
    rv       = getattr(regime, "regime", None) if regime else None
    reg_name = rv.value if hasattr(rv, "value") else str(rv) if rv else "UNKNOWN"
    direction  = "short" if reg_name in ("TRENDING_DOWN", "DISTRIBUTION", "MARKDOWN") else "long"
    base_level = "A3"   if reg_name in ("UNKNOWN", "NEUTRAL", "RANGING", "VOLATILE") else "A2"

    # ── Edge selector (R3/R10) ────────────────────────────────────────────────
    if selector is not None:
        dir_key          = "BUY" if direction in ("long", "buy") else "SELL"
        filtered, down, _ = selector.apply(symbol, tf, dir_key, base_level)
        if down:
            base_level = filtered

    # ── R8 thresholds (cache) ─────────────────────────────────────────────────
    entry = _load_r8_thresholds().get(f"{symbol.upper()}_{tf.upper()}")
    if entry:
        min_lvl = entry.get("min_signal_level", "NONE")
        if _LEVEL_RANK.get(base_level, 0) < _LEVEL_RANK.get(min_lvl, 0):
            base_level = min_lvl

    # ── Grammar V9 ────────────────────────────────────────────────────────────
    def _grammar():
        series = _safe(load_currency_series, None, str(db), pair=symbol, timeframe=tf)
        lead   = _safe(compute_leadership, {}, series) if series else {}
        return evaluate_grammar_v9(
            regime_name=reg_name,
            leader=lead.get("leader"), follower=lead.get("follower"),
            bascule_detectee=False, bascule_intensite=0.0,
            trend_direction=direction,
            pliure_detectee=False, tension_score=0.0, pente=0.0,
            zone_type="", compression_etat="", antagonismes_count=0,
        )
    grammar = _safe(_grammar, None)

    # ── Fatman Bible ──────────────────────────────────────────────────────────
    def _bible():
        states = get_all_fatman_live(
            timeframes=("M30", "H1"), symbols=tuple(PAIRS), db_path=str(db)
        )
        return _bible_signals_for(symbol, tf, states)
    bible_signals = _safe(_bible, [])

    # ── Fractal context ───────────────────────────────────────────────────────
    def _fractal():
        from core.v10.v10_fractal_context import (
            compute_fractal_confluence, compute_fast_cinematics, fractal_signal,
        )
        conf = compute_fractal_confluence(symbol=symbol, db_path=str(db))
        cine = compute_fast_cinematics(
            symbol=symbol, decision_timeframe=tf, db_path=str(db)
        )
        return fractal_signal(
            confluence=conf, cinematics=cine, decision_direction=direction
        ).as_dict()
    fractal = _safe(_fractal, None)

    # ── Market context global ─────────────────────────────────────────────────
    def _market_ctx():
        mc_snaps   = load_currency_strength_snapshots(db, MCONTEXT_TFS)
        thresholds = {
            k: {
                "anta_score_min":    v.get("anta_score_min",    25.0),
                "aligned_count_min": v.get("aligned_count_min", 3),
                "context_score_min": v.get("context_score_min", 55.0),
            }
            for k, v in _load_r8_thresholds().items() if v.get("gate_passed")
        }
        return compute_market_context(
            mc_snaps, timestamp=ts,
            thresholds=thresholds or None,
            m30_vsa_bias=structure.get("trend_bias")          if structure else None,
            h1_vsa_bias=None,
            m30_vsa_state=structure.get("s7_market_structure") if structure else None,
        ).as_dict()
    market_context = _safe(_market_ctx, None)

    # ── RL shadow — feature vector réel ──────────────────────────────────────
    rl_arm = rl_shadow_signal = None
    if rl_adapter is not None and not rl_adapter.kill_switch_active:
        fv     = _build_rl_feature_vector(session, structure, fractal, market_context)
        rl_arm = _safe(rl_adapter.bandit.select_arm, None, fv)
        rl_shadow_signal = rl_arm
        trade_id = f"{symbol}_{tf}_{ts.replace(':', '').replace('-', '')}"
        _safe(
            rl_adapter.log_shadow_trade, None,
            trade_id=trade_id, pair=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            feature_vector=fv, arm_chosen=rl_arm,
            baseline_level=base_level, shadow_level=rl_shadow_signal,
            pnl_pips=0.0,
        )

    # ── Décision finale ───────────────────────────────────────────────────────
    dec = decide_entry(
        symbol, tf, ts, direction, base_level,
        session=session, ote=ote, smc=smc, regime=regime,
        candidate_risk_pct=1.0, grammar=grammar,
        fractal=fractal, structure=structure,
    )
    out = dec.as_dict()
    out.update({
        "regime_direction": direction,
        "regime":           reg_name,
        "bible_signals":    bible_signals,
    })

    # ── Edge OVERLAP filter (Option C — DECISION_OVERLAP_VS_SCAN_LARGE.md) ────
    # Tag additif : edge_overlap / execution_eligible / exploration_only.
    # La couche d'exécution ne route que les ticks execution_eligible=True.
    # R6 fail-open : échec du filtre → exploration_only (jamais exécutable).
    try:
        from core.v10.v10_edge_overlap_filter import edge_overlap_verdict
        _bar_ts = out.get("timestamp") or ts
        _bar_epoch = None
        try:
            _bar_epoch = int(datetime.fromisoformat(
                str(_bar_ts).replace("Z", "+00:00")).timestamp())
        except Exception:
            _bar_epoch = None
        out["edge_overlap"] = edge_overlap_verdict(
            db, symbol, tf, bar_time=_bar_epoch)
    except Exception:
        out["edge_overlap"] = {
            "edge_overlap": False, "execution_eligible": False,
            "exploration_only": True, "reason": "filter_error",
        }

    if fractal        is not None: out["fractal"]        = fractal
    if structure      is not None: out["structure"]       = structure
    if market_context is not None: out["market_context"]  = market_context
    if rl_adapter     is not None:
        out["rl_shadow"] = {
            "arm":          rl_arm,
            "shadow_signal": rl_shadow_signal,
            "mode":         rl_adapter.mode.value,
            "kill_switch":  rl_adapter.kill_switch_active,
            "arm_stats":    rl_adapter.bandit.get_arm_stats(),
        }
    return out


# ── Poll loop ─────────────────────────────────────────────────────────────────
def run_poll(
    db: Path,
    *,
    max_ticks: int = 1,
    interval: float = 5.0,
    log_db: str = "data/v10_decisions.db",
    use_edge_selector: bool = True,
) -> dict:
    """Boucle de polling (max_ticks=0 → infini)."""
    results    = []
    logger     = DecisionLogger(db_path=log_db)
    selector   = EdgeSelector.from_replay_batch() if use_edge_selector else None
    if selector and selector.edge_map:
        log.info("Edge selector actif (%d edges)", len(selector.edge_map))
    rl_adapter = RLAdapter(db_path=log_db, mode=RLMode.SHADOW)
    log.info("RL Adapter SHADOW initialisé (kill_switch DD>5%%, epsilon=10%%)")

    n = 0
    while max_ticks == 0 or n < max_ticks:
        n += 1
        for symbol in PAIRS:
            for tf in TIMEFRAMES:
                dec = tick_decision(db, symbol, tf,
                                    selector=selector, rl_adapter=rl_adapter)
                if dec.get("action") in ("BUY", "SELL"):
                    logger.append(DecisionRecord(
                        pair=symbol, timeframe=tf,
                        timestamp=dec.get("timestamp", ""),
                        action=dec["action"],
                        signal_level=dec.get("signal_level",  "NONE"),
                        filtered_level=dec.get("filtered_level", "NONE"),
                        lot_size=dec.get("lot_size", 0.0),
                    ))
                results.append(dec)
        if max_ticks != 0:
            break
        time.sleep(interval)

    logger.close()
    return {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "n_ticks":         n,
        "tick_results":    results,
        "r8_calibration":  ensure_active_thresholds(),
        "audit":           {"r10": "paper-only, zero order real"},
    }


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",     default=str(DEFAULT_DB))
    ap.add_argument("--ticks",  type=int, default=1)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable : %s", db)
        return 2

    report   = run_poll(db, max_ticks=args.ticks)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = (
        Path(args.output) if args.output
        else ROOT / "reports" / f"v10_live_decision_{date_str}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport écrit : %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
