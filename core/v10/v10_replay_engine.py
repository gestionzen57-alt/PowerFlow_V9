"""
V10 ReplayEngine — CYCLE 8 MAX PERF (09/08/2026)

Fixes C8 (sur base C5) :

  BLOCK1 — Bayes ctx_score_min : 60 → 45
    A3 sans H4 donne ctx=50 → était rejeté à 100% (50<60)
    Nouveau barrage : 45 (A3 alone passe, A2 alone passe confortablement)

  BLOCK2 — H4 gate désactivé si h4_bias=0.0 (pas de données H4 en replay)
    Évitait 100% des scalps sans données H4 dans la DB

  BLOCK3 — signal_level NONE → HOLD direct (plus de A2 hardcodé en fallback)
    Le fallback écrasait le signal propre du SGL

  BLOCK4 — STRICT_SCALP_TFS vidé (frozenset vide)
    M1/M5 ne sont plus systématiquement bloqués quand fractal KO

  BLOCK5 — bridge_decide C7 câblé dans _decide_one()
    Pipeline SGL→FC(boost)→RS(fail-open)→DP(bug1/2/3 fix) maintenant actif

  BLOCK6 — baseline C7 ajoutée pour delta reporting

Doctrine :
  R2 — additif pur : zéro import core/v9/
  R6 — fail-open   : toute exception sous-module → warn + continue
  R9 — audit       : chaque décision porte vsa/fractal/bridge trace
  R10— compute only: zéro ordre réel
"""
from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══ IMPORTS V10 (tous fail-open R6) ═══════════════════════════════════

try:
    from .v10_signal_generator_live import SignalGeneratorLive
    _SGL_OK = True
except Exception as _e:
    log.warning("[C8] SignalGeneratorLive KO: %s", _e)
    SignalGeneratorLive = None
    _SGL_OK = False

try:
    from .v10_decision_pipeline import decide_entry, PipelineDecision
    _DECIDE_OK = True
except Exception as _e:
    log.warning("[C8] decide_entry KO: %s", _e)
    decide_entry = None
    PipelineDecision = None
    _DECIDE_OK = False

try:
    from .v10_replay_bridge import bridge_decide
    _BRIDGE_OK = True
except Exception as _e:
    log.warning("[C8] bridge_decide KO: %s", _e)
    bridge_decide = None
    _BRIDGE_OK = False

try:
    from .v10_vsa import compute_vsa
    _VSA_OK = True
except Exception as _e:
    log.warning("[C8] VSA KO: %s", _e)
    compute_vsa = None
    _VSA_OK = False

try:
    from .v10_fractal_context import (
        compute_fractal_confluence,
        compute_fast_cinematics,
        fractal_signal,
    )
    _FRACTAL_OK = True
except Exception as _e:
    log.warning("[C8] FractalContext KO: %s", _e)
    compute_fractal_confluence = None
    compute_fast_cinematics    = None
    fractal_signal             = None
    _FRACTAL_OK = False

try:
    from .v10_fatman_bible_signals import get_fatman_signal
    _FATMAN_OK = True
except Exception as _e:
    log.warning("[C8] FatmanBibleSignals KO: %s", _e)
    get_fatman_signal = None
    _FATMAN_OK = False

try:
    from .v10_bayesian_recalibrator import (
        compute_recalibration,
        DEFAULT_THRESHOLDS,
        apply_thresholds,
    )
    _BAYES_OK = True
except Exception as _e:
    log.warning("[C8] BayesianRecalibrator KO: %s", _e)
    compute_recalibration = None
    DEFAULT_THRESHOLDS    = {}
    apply_thresholds      = None
    _BAYES_OK = False

try:
    from .v10_rl_adapter import RLAdapter
    _RL_OK = True
except Exception as _e:
    log.warning("[C8] RLAdapter KO: %s", _e)
    RLAdapter = None
    _RL_OK = False

try:
    from .v10_risk_shield import evaluate_risk_shield
    _RISK_OK = True
except Exception as _e:
    log.warning("[C8] RiskShield KO: %s", _e)
    evaluate_risk_shield = None
    _RISK_OK = False


# ══ CONSTANTES ══════════════════════════════════════════════════════

TF_ROLE: Dict[str, str] = {
    "M1":  "SCALP_TRIGGER",
    "M5":  "SCALP_TRIGGER",
    "M15": "ENTRY_TRIGGER",
    "M30": "ENTRY_STRUCTURE",
    "H1":  "ENTRY_STRUCTURE",
    "H4":  "CONTEXT_BIAS",
    "D1":  "CONTEXT_BIAS",
}

TRADE_TFS  = frozenset({"M1", "M5", "M15", "M30", "H1"})
SCALP_TFS  = frozenset({"M1", "M5", "M15"})

# BLOCK4 FIX : STRICT_SCALP_TFS vidé (trop restrictif sans fractal module actif)
STRICT_SCALP_TFS = frozenset()

TP_SL_BY_TF: Dict[str, Tuple[float, float]] = {
    "M1":  (5.0,   3.0),
    "M5":  (10.0,  6.0),
    "M15": (20.0,  12.0),
    "M30": (30.0,  18.0),
    "H1":  (50.0,  30.0),
    "H4":  (80.0,  50.0),
    "D1":  (150.0, 90.0),
}

FRACTAL_VETO          = -0.20
H4_BIAS_THRESH_HARD   = 0.30
H4_BIAS_THRESH_SCALP  = 0.15
H4_BIAS_THRESH_STRICT = 0.20

# BLOCK1 FIX : ctx_score_min 60 → 45
BAYES_CTX_SCORE_MIN = 45.0

VSA_CONVICTION_MIN = 0.30

DEFAULT_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCHF", "USDCAD", "EURJPY",
]
DEFAULT_TFS = ["M1", "M5", "M15", "M30", "H1"]


# ══ DATACLASSES ═══════════════════════════════════════════════════

@dataclass
class DecisionRecord:
    pair:            str
    tf:              str
    tf_role:         str
    timestamp:       str
    direction:       str
    signal_level:    str
    action:          str
    pipeline:        str
    vsa_state:       str   = "N/A"
    vsa_effort:      float = 0.0
    vsa_conviction:  float = 0.0
    vsa_no_supply:   bool  = False
    vsa_no_demand:   bool  = False
    vsa_stopping:    bool  = False
    vsa_ok:          bool  = False
    fractal_boost:   float = 0.0
    fractal_direction: str = "NONE"
    fractal_aligned: bool  = False
    h4_bias:         float = 0.0
    mtf_aligned:     bool  = False
    fatman_signal:   str   = "N/A"
    fatman_pattern:  str   = "N/A"
    fatman_strength: float = 0.0
    bayes_source:    str   = "default"
    bayes_passed:    bool  = False
    held_reason:     str   = ""
    pnl_pips:        float = 0.0
    win:             Optional[bool] = None
    c5_scalp_gate:   str   = ""
    bridge_used:     bool  = False   # C8
    filtered_level:  str   = ""      # C8

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PairTFResult:
    pair:                  str
    tf:                    str
    tf_role:               str
    n_decisions:           int   = 0
    n_trades:              int   = 0
    n_wins:                int   = 0
    n_holds:               int   = 0
    pnl_pips:              float = 0.0
    wr:                    float = 0.0
    vsa_coverage_pct:      float = 0.0
    fractal_coverage_pct:  float = 0.0
    mtf_filter_count:      int   = 0
    decisions:             List[Dict] = field(default_factory=list)


@dataclass
class ReplayReport:
    run_id:             str
    generated_at:       str
    pairs:              List[str]
    timeframes:         List[str]
    n_total_decisions:  int   = 0
    n_total_trades:     int   = 0
    n_wins:             int   = 0
    global_wr:          float = 0.0
    global_pnl_pips:    float = 0.0
    avg_sharpe:         float = 0.0
    wr_delta_vs_c3:     float = 0.0
    pnl_delta_vs_c3:    float = 0.0
    wr_delta_vs_c4:     float = 0.0
    pnl_delta_vs_c4:    float = 0.0
    wr_delta_vs_c7:     float = 0.0   # C8 baseline
    pnl_delta_vs_c7:    float = 0.0
    pipeline_dominant:  str   = "N/A"
    vsa_coverage_pct:   float = 0.0
    fractal_coverage_pct: float = 0.0
    mtf_filter_count:   int   = 0
    modules_active:     Dict  = field(default_factory=dict)
    tf_role_map:        Dict  = field(default_factory=dict)
    by_pair_tf:         List[Dict] = field(default_factory=list)
    c5_features:        List[str]  = field(default_factory=list)
    summary:            Dict  = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ══ DB HELPERS ═════════════════════════════════════════════════════════

def _db_connect(db_path: str) -> Optional[sqlite3.Connection]:
    for uri_flag, uri in [
        (True,  f"file:{db_path}?mode=ro"),
        (False, db_path),
    ]:
        try:
            conn = sqlite3.connect(uri, uri=uri_flag)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            continue
    return None


def _load_bars(conn, symbol, tf, limit):
    queries = [
        (
            "SELECT bar_time AS timestamp, open, high, low, close, "
            "tick_volume, real_volume FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), limit),
        ),
        (
            "SELECT time AS timestamp, open, high, low, close, tick_volume "
            "FROM ohlcv WHERE symbol=? AND timeframe=? "
            "ORDER BY time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), limit),
        ),
    ]
    for sql, params in queries:
        try:
            rows = conn.execute(sql, params).fetchall()
            if rows:
                bars: List[Dict] = []
                for r in reversed(rows):
                    b = dict(r)
                    for k in ("open", "high", "low", "close"):
                        b[k] = float(b.get(k) or 0.0)
                    b["tick_volume"] = float(b.get("tick_volume") or 0.0)
                    bars.append(b)
                return bars
        except Exception:
            continue
    return []


def _load_h4_bias(conn, symbol: str) -> float:
    try:
        rows = conn.execute(
            "SELECT force_base, force_quote FROM forces_snapshots "
            "WHERE symbol=? AND timeframe='H4' AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT 10",
            (symbol.upper(),),
        ).fetchall()
        deltas = [
            float(r["force_base"] or 0) - float(r["force_quote"] or 0)
            for r in rows
            if r["force_base"] is not None and r["force_quote"] is not None
        ]
        if deltas:
            return round(max(-1.0, min(1.0, sum(deltas) / len(deltas))), 4)
    except Exception:
        pass
    try:
        rows = conn.execute(
            "SELECT close FROM forces_snapshots "
            "WHERE symbol=? AND timeframe='H4' AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT 30",
            (symbol.upper(),),
        ).fetchall()
        closes = [float(r["close"]) for r in reversed(rows)]
        n = len(closes)
        if n >= 5:
            xs  = list(range(n))
            mx  = sum(xs) / n
            my  = sum(closes) / n
            num = sum((x - mx) * (c - my) for x, c in zip(xs, closes))
            den = sum((x - mx) ** 2 for x in xs) or 1e-9
            slope = (num / den) / (my or 1.0)
            return round(max(-1.0, min(1.0, slope * 200)), 4)
    except Exception:
        pass
    return 0.0


# ══ COUCHE VSA ════════════════════════════════════════════════════════════

def _build_vsa_grammar_proxy(bars, symbol, tf, direction):
    neutral_raw = {
        "ok": False, "state": "NEUTRAL", "effort": 0.0,
        "conviction": 0.0, "no_supply": False, "no_demand": False,
        "stopping": False, "climax": False,
    }
    neutral_grammar = {"n_detected": 0, "best": None}
    if not _VSA_OK or compute_vsa is None or len(bars) < 10:
        return neutral_grammar, neutral_raw
    try:
        ts     = str(bars[-1].get("timestamp", ""))
        result = compute_vsa(symbol=symbol, timestamp=ts, timeframe=tf, bars=bars)
        if result.data_insufficient:
            return neutral_grammar, neutral_raw
        state_val  = result.state.value if hasattr(result.state, "value") else str(result.state)
        conviction = min(1.0, result.effort_vs_result + result.volume_relative * 0.10)
        if conviction < VSA_CONVICTION_MIN:
            return neutral_grammar, {
                "ok": False, "state": state_val,
                "effort": round(result.effort_vs_result, 4),
                "conviction": round(conviction, 4),
                "no_supply": result.no_supply, "no_demand": result.no_demand,
                "stopping": result.stopping_volume, "climax": result.climax,
            }
        vsa_bull = {"MARKUP", "ACCUMULATION"}
        vsa_bear = {"MARKDOWN", "DISTRIBUTION"}
        g_dir    = "BULLISH" if state_val in vsa_bull else ("BEARISH" if state_val in vsa_bear else "NEUTRAL")
        grammar  = (
            {"n_detected": 1, "best": {"concept": "VSA_STOPPING", "direction": "NEUTRAL", "confidence": 0.9}}
            if result.stopping_volume
            else {"n_detected": 1, "best": {"concept": f"VSA_{state_val}", "direction": g_dir, "confidence": round(conviction, 4)}}
        )
        raw = {
            "ok": True, "state": state_val,
            "effort": round(result.effort_vs_result, 4),
            "conviction": round(conviction, 4),
            "no_supply": result.no_supply, "no_demand": result.no_demand,
            "stopping": result.stopping_volume, "climax": result.climax,
        }
        return grammar, raw
    except Exception as exc:
        log.debug("[VSA] %s/%s fail-open: %s", symbol, tf, exc)
        return neutral_grammar, neutral_raw


# ══ COUCHE FRACTAL ══════════════════════════════════════════════════════════

def _build_fractal_dict(fractal_conf, pair, tf, direction, db_path):
    if not _FRACTAL_OK or fractal_signal is None:
        return {}, 0.0, "NONE", False
    try:
        cine = None
        if compute_fast_cinematics is not None:
            try:
                cine = compute_fast_cinematics(symbol=pair, decision_timeframe=tf, db_path=db_path)
            except Exception as exc_c:
                log.debug("[FRACTAL_CINE] %s/%s fail-open: %s", pair, tf, exc_c)
        fsig = fractal_signal(confluence=fractal_conf, cinematics=cine, decision_direction=direction)
        if fsig is None:
            return {}, 0.0, "NONE", False
        fd = {
            "boost":      fsig.boost,
            "direction":  fsig.direction,
            "aligned":    fsig.aligned,
            "confluence": fsig.confluence if isinstance(fsig.confluence, dict) else (
                fsig.confluence.as_dict() if hasattr(fsig.confluence, "as_dict") else {}
            ),
            "cinematics": fsig.cinematics if isinstance(fsig.cinematics, dict) else (
                fsig.cinematics.as_dict() if hasattr(fsig.cinematics, "as_dict") else {}
            ),
        }
        return fd, fsig.boost, fsig.direction, fsig.aligned
    except Exception as exc:
        log.debug("[FRACTAL] %s/%s fail-open: %s", pair, tf, exc)
        return {}, 0.0, "NONE", False


# ══ COUCHE FATMAN ═══════════════════════════════════════════════════════════

def _build_fatman_structure(bars, pair, tf):
    neutral = {"ok": False, "signal": "NEUTRAL", "pattern": "N/A", "strength": 0.0}
    if not _FATMAN_OK or get_fatman_signal is None or len(bars) < 10:
        return None, neutral
    try:
        result   = get_fatman_signal(bars=bars, pair=pair, tf=tf)
        if result is None:
            return None, neutral
        sig      = result.get("signal", "NEUTRAL") if isinstance(result, dict) else getattr(result, "signal", "NEUTRAL")
        pattern  = result.get("pattern", "N/A")    if isinstance(result, dict) else getattr(result, "pattern", "N/A")
        strength = float(result.get("strength", 0.0) if isinstance(result, dict) else getattr(result, "strength", 0.0))
        bos      = result.get("bos", None) if isinstance(result, dict) else getattr(result, "bos", None)
        s8_break = "BOS_BULL" if (bos == "bull" or (sig == "BUY"  and strength > 0.6)) else (
                   "BOS_BEAR" if (bos == "bear" or (sig == "SELL" and strength > 0.6)) else "NONE")
        structure = {
            "s7_market_structure": "TREND" if strength > 0.4 else "RANGE",
            "s8_break":            s8_break,
            "fatman_signal":       sig,
            "fatman_pattern":      str(pattern),
            "fatman_strength":     round(strength, 4),
        }
        return structure, {"ok": True, "signal": sig, "pattern": str(pattern), "strength": round(strength, 4)}
    except Exception as exc:
        log.debug("[FATMAN] %s/%s fail-open: %s", pair, tf, exc)
        return None, neutral


# ══ SIMULATION PnL ══════════════════════════════════════════════════════════

def _simulate_pnl(bars, entry_idx, action, pair, tf):
    tp_p, sl_p = TP_SL_BY_TF.get(tf, (20.0, 12.0))
    pip        = 0.01 if pair.upper().endswith("JPY") else 0.0001
    entry_close = float(bars[entry_idx].get("close") or 0.0)
    if entry_close == 0:
        return 0.0
    sign     = 1 if action == "BUY" else -1
    tp_price = entry_close + tp_p * pip * sign
    sl_price = entry_close - sl_p * pip * sign
    max_hold = max(3, min(10, int(tp_p / 5)))
    for j in range(entry_idx + 1, min(entry_idx + 1 + max_hold, len(bars))):
        high = float(bars[j].get("high") or entry_close)
        low  = float(bars[j].get("low")  or entry_close)
        if action == "BUY":
            if high >= tp_price: return  tp_p
            if low  <= sl_price: return -sl_p
        else:
            if low  <= tp_price: return  tp_p
            if high >= sl_price: return -sl_p
    exit_close = float(bars[min(entry_idx + max_hold, len(bars) - 1)].get("close") or entry_close)
    return round((exit_close - entry_close) * sign / pip, 2)


# ══ DÉCISION PAR BARRE ════════════════════════════════════════════════════════

def _decide_one(
    pair, tf, tf_role, bars, h4_bias, fractal_conf, db_path,
    session="LONDON", bayes_thresholds=None,
) -> Optional[DecisionRecord]:
    """Pipeline complet C8 pour 1 barre sur 1 paire×TF."""
    if len(bars) < 30:
        return None

    cur = bars[-1]
    ts  = str(cur.get("timestamp") or datetime.now(timezone.utc).isoformat())

    # ══ 1. SignalGeneratorLive → direction + signal_level ══════════════════
    direction    = "long"
    signal_level = "A3"        # C8 : défaut A3 (plus conservateur que A2 hardcodé)
    pipeline_used = "fallback"

    if _SGL_OK and SignalGeneratorLive is not None:
        try:
            sig_out      = SignalGeneratorLive().generate(symbol=pair, timeframe=tf, bars=bars)
            if sig_out is not None:
                direction    = sig_out.get("direction", "long") if isinstance(sig_out, dict) else getattr(sig_out, "direction", "long")
                signal_level = sig_out.get("signal_level", "A3") if isinstance(sig_out, dict) else getattr(sig_out, "signal_level", "A3")
                pipeline_used = "signal_generator_live"
        except Exception as exc:
            log.debug("[SGL] %s/%s fail-open: %s", pair, tf, exc)

    # BLOCK3 FIX : signal NONE → HOLD direct
    if signal_level == "NONE":
        return DecisionRecord(
            pair=pair, tf=tf, tf_role=tf_role, timestamp=ts,
            direction=direction, signal_level=signal_level,
            action="HOLD", pipeline="sgl_none",
            held_reason="signal_NONE",
        )

    dir_up = direction in ("long", "buy", "BUY", "LONG", "BULLISH")

    # ══ 2. Filtres durs pré-décision ═══════════════════════════════════
    held_reason   = ""
    c5_scalp_gate = ""

    # BLOCK2 FIX : H4 gate désactivé si h4_bias=0.0 (pas de données H4)
    if h4_bias != 0.0:
        if (dir_up and h4_bias < -H4_BIAS_THRESH_HARD) or \
           (not dir_up and h4_bias > H4_BIAS_THRESH_HARD):
            held_reason = f"H4_OPPOSE(h4={h4_bias:.3f})"

        if not held_reason and tf_role == "SCALP_TRIGGER":
            if (dir_up and h4_bias < H4_BIAS_THRESH_SCALP) or \
               (not dir_up and h4_bias > -H4_BIAS_THRESH_SCALP):
                held_reason   = f"SCALP_NO_H4(h4={h4_bias:.3f})"
                c5_scalp_gate = "H4_WEAK"

    # ══ 3. VSA + 4. Fractal ═════════════════════════════════════════
    grammar_proxy, vsa_raw = _build_vsa_grammar_proxy(bars, pair, tf, direction)
    if not held_reason and vsa_raw.get("stopping"):
        held_reason = "VSA_STOPPING_VOLUME"

    fractal_dict, fractal_boost, fractal_dir, fractal_aligned = _build_fractal_dict(
        fractal_conf, pair, tf, direction, db_path,
    )

    # BLOCK4 : STRICT_SCALP_TFS = {} — plus de gate M1/M5 ici
    # Fractal veto seul (seuil -0.20)
    if not held_reason and fractal_boost < FRACTAL_VETO:
        held_reason = f"FRACTAL_VETO(boost={fractal_boost:.3f})"

    # ══ 5. Fatman ════════════════════════════════════════════════════
    structure_dict, fatman_raw = _build_fatman_structure(bars, pair, tf)

    # ══ 6. Bayesian gate (BLOCK1 : seuil 45) ═══════════════════════════
    bayes_passed = True
    bayes_source = "default"
    if not held_reason and _BAYES_OK and apply_thresholds is not None:
        try:
            sl_map    = {"A1": 80.0, "A2": 65.0, "A3": 50.0, "NONE": 30.0}
            ctx_score = sl_map.get(signal_level, 50.0) + abs(h4_bias) * 20.0 + fractal_boost * 10.0
            anta_score    = abs(h4_bias) * 25.0 + vsa_raw.get("conviction", 0.0) * 20.0
            aligned_count = sum([
                1 if fractal_aligned else 0,
                1 if vsa_raw.get("ok") else 0,
                1 if abs(h4_bias) > 0.1 else 0,
            ])
            eff_thresholds = bayes_thresholds or {
                "_global": {
                    "context_score_min":  BAYES_CTX_SCORE_MIN,
                    "anta_score_min":     20.0,
                    "aligned_count_min":  1,   # C8 : assoupli de 2 à 1
                }
            }
            bayes_passed = apply_thresholds(
                pair=pair, context_score=ctx_score,
                anta_score=anta_score, aligned_count=aligned_count,
                thresholds=eff_thresholds,
            )
            bayes_source = "recalibrated" if bayes_thresholds and pair in (bayes_thresholds or {}) else "default_c8"
            if not bayes_passed:
                held_reason = f"BAYES_GATE_C8(ctx={ctx_score:.1f}<{BAYES_CTX_SCORE_MIN})"
        except Exception as exc:
            log.debug("[BAYES] %s/%s fail-open: %s", pair, tf, exc)
            sl_map_fb = {"A1": 80.0, "A2": 65.0, "A3": 50.0, "NONE": 30.0}
            ctx_fb    = sl_map_fb.get(signal_level, 50.0) + abs(h4_bias) * 20.0 + fractal_boost * 10.0
            bayes_passed = ctx_fb >= BAYES_CTX_SCORE_MIN
            if not bayes_passed:
                held_reason = f"BAYES_CTX_FB(ctx={ctx_fb:.1f}<{BAYES_CTX_SCORE_MIN})"

    # ══ 7. Action finale ═══════════════════════════════════════════════════
    action         = "HOLD"
    filtered_level = ""
    bridge_used    = False

    if not held_reason:
        # BLOCK5 : bridge_decide C7 en priorité
        if _BRIDGE_OK and bridge_decide is not None:
            try:
                br = bridge_decide(
                    symbol=pair,
                    timeframe=tf,
                    bars=bars,
                    timestamp=ts,
                    fractal=fractal_dict if fractal_dict else None,
                    grammar=grammar_proxy if grammar_proxy.get("n_detected", 0) > 0 else None,
                    structure=structure_dict,
                    positions=[],
                )
                action         = br.get("action", "WAIT")
                filtered_level = br.get("filtered_level", "")
                pipeline_used  = f"bridge_c8+{br.get('source','?')}"
                bridge_used    = True
            except Exception as exc:
                log.debug("[BRIDGE] %s/%s fail-open: %s", pair, tf, exc)
                # fallback decide_entry
                if _DECIDE_OK and decide_entry is not None:
                    try:
                        dp = decide_entry(
                            pair=pair, timeframe=tf, timestamp=ts,
                            direction=direction, signal_level=signal_level,
                            grammar=grammar_proxy if grammar_proxy.get("n_detected", 0) > 0 else None,
                            fractal=fractal_dict if fractal_dict else None,
                            structure=structure_dict,
                        )
                        action         = dp.action if dp else "WAIT"
                        filtered_level = dp.filtered_level if dp else ""
                        pipeline_used  = "decide_entry_fallback"
                    except Exception as exc2:
                        log.debug("[DECIDE] fallback fail-open: %s", exc2)
                        action = "BUY" if dir_up else "SELL"
                        pipeline_used = "sgl_direct_fallback"
        elif _DECIDE_OK and decide_entry is not None:
            try:
                dp = decide_entry(
                    pair=pair, timeframe=tf, timestamp=ts,
                    direction=direction, signal_level=signal_level,
                    grammar=grammar_proxy if grammar_proxy.get("n_detected", 0) > 0 else None,
                    fractal=fractal_dict if fractal_dict else None,
                    structure=structure_dict,
                )
                action         = dp.action if dp else "WAIT"
                filtered_level = dp.filtered_level if dp else ""
                pipeline_used  = "decide_entry_c8"
            except Exception as exc:
                log.debug("[DECIDE] %s/%s fail-open: %s", pair, tf, exc)
                action = "BUY" if dir_up else "SELL"
                pipeline_used = "sgl_direct_fallback"
        else:
            action        = "BUY" if dir_up else "SELL"
            pipeline_used = "sgl_direct_fallback"

    # Normalisation
    if action in ("WAIT", "NONE"):
        action = "HOLD"

    mtf_aligned = fractal_aligned and (abs(h4_bias) > 0.1)

    return DecisionRecord(
        pair=pair, tf=tf, tf_role=tf_role, timestamp=ts,
        direction=direction, signal_level=signal_level,
        action=action, pipeline=pipeline_used,
        vsa_state=vsa_raw["state"], vsa_effort=vsa_raw["effort"],
        vsa_conviction=vsa_raw["conviction"],
        vsa_no_supply=vsa_raw["no_supply"], vsa_no_demand=vsa_raw["no_demand"],
        vsa_stopping=vsa_raw["stopping"], vsa_ok=vsa_raw["ok"],
        fractal_boost=fractal_boost, fractal_direction=fractal_dir,
        fractal_aligned=fractal_aligned, h4_bias=h4_bias,
        mtf_aligned=mtf_aligned,
        fatman_signal=fatman_raw["signal"], fatman_pattern=fatman_raw["pattern"],
        fatman_strength=fatman_raw["strength"],
        bayes_source=bayes_source, bayes_passed=bayes_passed,
        held_reason=held_reason,
        c5_scalp_gate=c5_scalp_gate,
        bridge_used=bridge_used,
        filtered_level=filtered_level,
    )


# ══ REPLAY PAR PAIRE×TF ══════════════════════════════════════════════════════

def _replay_pair_tf(pair, tf, db_path, limit, session="LONDON", bayes_thresholds=None):
    tf_role = TF_ROLE.get(tf, "ENTRY_STRUCTURE")
    result  = PairTFResult(pair=pair, tf=tf, tf_role=tf_role)
    if tf not in TRADE_TFS:
        return result
    conn = _db_connect(db_path)
    if conn is None:
        log.warning("[REPLAY] DB inaccessible: %s", db_path)
        return result
    try:
        h4_bias     = _load_h4_bias(conn, pair)
        fractal_conf = None
        if _FRACTAL_OK and compute_fractal_confluence is not None:
            try:
                fractal_conf = compute_fractal_confluence(
                    symbol=pair,
                    timeframes=("M1", "M5", "M15", "M30", "H1", "H4", "D1"),
                    db_path=db_path,
                )
            except Exception as exc:
                log.debug("[FRACTAL_CONF] %s fail-open: %s", pair, exc)

        all_bars = _load_bars(conn, pair, tf, limit)
        if not all_bars:
            log.warning("[REPLAY] 0 barres %s/%s", pair, tf)
            return result

        n_vsa_ok = n_fractal_ok = n_mtf = 0
        decisions: List[DecisionRecord] = []

        for i in range(30, len(all_bars)):
            window = all_bars[max(0, i - 200): i + 1]
            rec = _decide_one(
                pair, tf, tf_role, window, h4_bias,
                fractal_conf, db_path, session, bayes_thresholds,
            )
            if rec is None:
                continue
            decisions.append(rec)
            result.n_decisions += 1
            if rec.vsa_ok:              n_vsa_ok    += 1
            if rec.fractal_boost != 0.: n_fractal_ok += 1
            if rec.held_reason and any(
                x in rec.held_reason for x in (
                    "H4_", "SCALP_", "FRACTAL_", "BAYES_", "VSA_", "STRICT_",
                )
            ):
                n_mtf += 1

            if rec.action in ("BUY", "SELL"):
                result.n_trades += 1
                pnl = _simulate_pnl(all_bars, i, rec.action, pair, tf)
                rec.pnl_pips = pnl
                rec.win      = pnl > 0
                result.pnl_pips += pnl
                if pnl > 0:
                    result.n_wins += 1
            else:
                result.n_holds += 1

        if result.n_trades > 0:
            result.wr = round(result.n_wins / result.n_trades, 4)
        if result.n_decisions > 0:
            result.vsa_coverage_pct     = round(n_vsa_ok     / result.n_decisions, 4)
            result.fractal_coverage_pct = round(n_fractal_ok / result.n_decisions, 4)
        result.mtf_filter_count = n_mtf
        result.decisions        = [d.as_dict() for d in decisions]
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return result


# ══ ReplayEngine (API publique) ════════════════════════════════════════════

class ReplayEngine:
    _C3_WR = 0.3647;  _C3_PNL = -1824.0;  _C3_DECISIONS = 1788
    _C4_WR = 0.2566;  _C4_PNL = -5660.0;  _C4_DECISIONS = 4470
    # BLOCK6 : baseline C7 (remplie après premier run C8)
    _C7_WR = 0.0;     _C7_PNL = 0.0;      _C7_DECISIONS = 0

    def __init__(self, db_path="data/powerflow.db", session="LONDON"):
        self.db_path = db_path
        self.session = session
        self._modules_active = {
            "signal_generator_live": _SGL_OK,
            "decide_entry":          _DECIDE_OK,
            "bridge_c8":             _BRIDGE_OK,
            "vsa":                   _VSA_OK,
            "fractal_context":       _FRACTAL_OK,
            "fatman_bible":          _FATMAN_OK,
            "bayesian_recalibrator": _BAYES_OK,
            "rl_adapter":            _RL_OK,
            "risk_shield":           _RISK_OK,
        }
        log.info("[ReplayEngine C8] modules: %s", self._modules_active)
        log.info(
            "[C8] Fixes: BRIDGE=%s | BAYES_CTX=%.0f | H4_GATE_SKIP_ZERO | "
            "STRICT_SCALP=OFF | SGL_NONE=HOLD | A3_DEFAULT",
            _BRIDGE_OK, BAYES_CTX_SCORE_MIN,
        )

    def _load_bayesian_thresholds(self):
        if not _BAYES_OK or compute_recalibration is None:
            return None
        try:
            report = compute_recalibration(self.db_path)
            if report and report.pair_thresholds:
                return report.pair_thresholds
        except Exception as exc:
            log.warning("[C8] Bayesian load fail-open: %s", exc)
        return None

    def run_all(
        self,
        pairs=None, timeframes=None,
        limit=200, workers=4,
    ) -> ReplayReport:
        if pairs      is None: pairs      = DEFAULT_PAIRS
        if timeframes is None: timeframes = DEFAULT_TFS

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report = ReplayReport(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            pairs=list(pairs), timeframes=list(timeframes),
            modules_active=dict(self._modules_active),
            tf_role_map=dict(TF_ROLE),
            c5_features=[
                "bridge_c8_wired",
                "bayes_ctx_min_45",
                "h4_gate_skip_if_zero",
                "strict_scalp_disabled",
                "sgl_none_early_hold",
                "fc_no_filter_boost_A3_to_A2",
                "rs_empty_positions_passthrough",
                "dp_bug1_2_3_fixed",
                "force_native_thresholds_recalibrated",
            ],
        )

        bayes_thresholds = self._load_bayesian_thresholds()
        combos = [
            (pair, tf)
            for pair in pairs
            for tf in timeframes
            if tf in TRADE_TFS
        ]
        log.info("[C8] %d combos", len(combos))

        all_results: List[PairTFResult] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _replay_pair_tf,
                    pair, tf, self.db_path, limit,
                    self.session, bayes_thresholds,
                ): (pair, tf)
                for pair, tf in combos
            }
            for fut in as_completed(futs):
                pair, tf = futs[fut]
                try:
                    res = fut.result(timeout=60)
                    all_results.append(res)
                except Exception as exc:
                    log.warning("[C8] %s/%s erreur: %s", pair, tf, exc)
                    all_results.append(PairTFResult(pair=pair, tf=tf, tf_role=TF_ROLE.get(tf, "?")))

        # ══ Agrégation ══════════════════════════════════════════════════════════
        total_dec    = sum(r.n_decisions for r in all_results)
        total_trades = sum(r.n_trades    for r in all_results)
        total_wins   = sum(r.n_wins      for r in all_results)
        total_pnl    = sum(r.pnl_pips    for r in all_results)
        total_vsa    = sum(r.n_decisions * r.vsa_coverage_pct     for r in all_results)
        total_frac   = sum(r.n_decisions * r.fractal_coverage_pct for r in all_results)
        total_mtf    = sum(r.mtf_filter_count for r in all_results)

        pip_counter: Counter = Counter()
        for r in all_results:
            for d in r.decisions:
                pip_counter[d.get("pipeline", "fallback")] += 1
        pipeline_dominant = pip_counter.most_common(1)[0][0] if pip_counter else "N/A"

        all_pnls = [
            d.get("pnl_pips", 0.0)
            for r in all_results
            for d in r.decisions
            if d.get("action") in ("BUY", "SELL")
        ]
        sharpe = 0.0
        if len(all_pnls) > 1:
            mu  = sum(all_pnls) / len(all_pnls)
            sig = (sum((x - mu) ** 2 for x in all_pnls) / len(all_pnls)) ** 0.5
            sharpe = round(mu / sig, 3) if sig > 0 else 0.0

        global_wr  = round(total_wins / total_trades, 4) if total_trades > 0 else 0.0
        global_pnl = round(total_pnl, 2)

        report.n_total_decisions  = total_dec
        report.n_total_trades     = total_trades
        report.n_wins             = total_wins
        report.global_wr          = global_wr
        report.global_pnl_pips    = global_pnl
        report.avg_sharpe         = sharpe
        report.wr_delta_vs_c3     = round(global_wr - self._C3_WR, 4)
        report.pnl_delta_vs_c3    = round(global_pnl - self._C3_PNL, 2)
        report.wr_delta_vs_c4     = round(global_wr - self._C4_WR, 4)
        report.pnl_delta_vs_c4    = round(global_pnl - self._C4_PNL, 2)
        report.wr_delta_vs_c7     = round(global_wr - self._C7_WR, 4)
        report.pnl_delta_vs_c7    = round(global_pnl - self._C7_PNL, 2)
        report.pipeline_dominant  = pipeline_dominant
        report.vsa_coverage_pct   = round(total_vsa  / total_dec, 4) if total_dec > 0 else 0.0
        report.fractal_coverage_pct = round(total_frac / total_dec, 4) if total_dec > 0 else 0.0
        report.mtf_filter_count   = total_mtf
        report.by_pair_tf = [
            {
                "pair": r.pair, "tf": r.tf, "role": r.tf_role,
                "n_decisions": r.n_decisions, "n_trades": r.n_trades,
                "n_wins":      r.n_wins,      "n_holds": r.n_holds,
                "wr":          r.wr,          "pnl_pips": round(r.pnl_pips, 2),
                "vsa_coverage":     r.vsa_coverage_pct,
                "fractal_coverage": r.fractal_coverage_pct,
                "mtf_filter_count": r.mtf_filter_count,
            }
            for r in all_results
        ]
        report.summary = {
            "cycle": 8, "version": "C8",
            "c8_features": report.c5_features,
            "baselines": {
                "c3": {"wr": self._C3_WR, "pnl": self._C3_PNL},
                "c4": {"wr": self._C4_WR, "pnl": self._C4_PNL},
                "c7": {"wr": self._C7_WR, "pnl": self._C7_PNL},
            },
            "deltas": {
                "vs_c3": {"wr": report.wr_delta_vs_c3, "pnl": report.pnl_delta_vs_c3},
                "vs_c4": {"wr": report.wr_delta_vs_c4, "pnl": report.pnl_delta_vs_c4},
                "vs_c7": {"wr": report.wr_delta_vs_c7, "pnl": report.pnl_delta_vs_c7},
            },
            "modules_active":        self._modules_active,
            "global_wr":             global_wr,
            "global_pnl":            global_pnl,
            "avg_sharpe":            sharpe,
            "bridge_used":           _BRIDGE_OK,
            "pipeline_dominant":     pipeline_dominant,
            "n_combos":              len(combos),
            "bayes_loaded":          bayes_thresholds is not None,
            "c8_gates": {
                "bayes_ctx_min":   BAYES_CTX_SCORE_MIN,
                "fractal_veto":    FRACTAL_VETO,
                "h4_hard":         H4_BIAS_THRESH_HARD,
                "h4_scalp":        H4_BIAS_THRESH_SCALP,
                "strict_scalp_disabled": True,
            },
        }
        log.info(
            "[C8] trades=%d WR=%.1f%%(ΔC4=%+.1f%% ΔC7=%+.1f%%) "
            "PnL=%.0f(ΔC4=%+.0f ΔC7=%+.0f) Sharpe=%.2f bridge=%s",
            total_trades,
            global_wr * 100, report.wr_delta_vs_c4 * 100, report.wr_delta_vs_c7 * 100,
            global_pnl, report.pnl_delta_vs_c4, report.pnl_delta_vs_c7,
            sharpe, _BRIDGE_OK,
        )
        return report


# ══ EXPORTS ══════════════════════════════════════════════════════════════
__all__ = [
    "ReplayEngine", "ReplayReport", "PairTFResult", "DecisionRecord",
    "TF_ROLE", "TRADE_TFS", "SCALP_TFS", "STRICT_SCALP_TFS",
    "TP_SL_BY_TF", "DEFAULT_PAIRS", "DEFAULT_TFS",
]
