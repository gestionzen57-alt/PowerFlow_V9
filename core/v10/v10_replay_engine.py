"""
V10 ReplayEngine — FULLSTACK v4 (CYCLE 4 — 09/08/2026)

Pipeline multifractal + VSA/Fatman branché.

Architecture 3 couches :
  COUCHE 1 — CONTEXTE  : H4/D1 → biais directionnel dominant (FractalContext)
  COUCHE 2 — STRUCTURE : H1/M30 → VSA (Effort/Continuation/NoSupply) + Fatman
  COUCHE 3 — TRIGGER   : M15/M5/M1 → SignalGeneratorLive.generate() + decide_entry()

Règles d'intégration (R2 additif pur, R6 fail-open) :
  • VSA CONTINUATION aligné  → signal_level upgrade  A3→A2
  • VSA NO_RESULT opposé     → signal_level downgrade A2→A3
  • VSA NO_SUPPLY / NO_DEMAND aligné → conviction +0.15
  • VSA STOPPING contre direction    → HOLD forcé
  • FractalBoost < -0.3              → HOLD forcé
  • Biais H4 opposé (|delta|>0.3)    → HOLD forcé
  • Tout module qui fail             → warn + continue (R6)

Doctrine :
  R2  — additif pur  : zéro import core/v9/
  R6  — fail-open    : exception dans un sous-module → signal quand même
  R9  — auditabilité : chaque décision porte son contexte fractal + VSA
  R10 — compute only : zéro ordre réel
"""
from __future__ import annotations

import logging
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Imports V10 (tous fail-open) ─────────────────────────────────────────────
try:
    from .v10_signal_generator_live import SignalGeneratorLive
    _SGL_OK = True
except Exception as _e:
    log.warning("[RE-C4] SignalGeneratorLive import KO: %s", _e)
    SignalGeneratorLive = None
    _SGL_OK = False

try:
    from .v10_decision_pipeline import decide_entry
    _DECIDE_OK = True
except Exception as _e:
    log.warning("[RE-C4] decide_entry import KO: %s", _e)
    decide_entry = None
    _DECIDE_OK = False

try:
    from .v10_vsa import compute_vsa, VSAState
    _VSA_OK = True
except Exception as _e:
    log.warning("[RE-C4] VSA import KO: %s", _e)
    compute_vsa = None
    VSAState = None
    _VSA_OK = False

try:
    from .v10_fractal_context import (
        compute_fractal_confluence,
        compute_fast_cinematics,
        fractal_signal,
        FractalConfluence,
        FastCinematics,
    )
    _FRACTAL_OK = True
except Exception as _e:
    log.warning("[RE-C4] FractalContext import KO: %s", _e)
    compute_fractal_confluence = None
    compute_fast_cinematics = None
    fractal_signal = None
    _FRACTAL_OK = False

try:
    from .v10_fatman_bible_signals import get_fatman_signal
    _FATMAN_OK = True
except Exception as _e:
    log.warning("[RE-C4] FatmanBibleSignals import KO: %s", _e)
    get_fatman_signal = None
    _FATMAN_OK = False

try:
    from .v10_rl_adapter import RLAdapter
    _RL_OK = True
except Exception as _e:
    log.warning("[RE-C4] RLAdapter import KO: %s", _e)
    RLAdapter = None
    _RL_OK = False

try:
    from .v10_meta_optimizer import MetaOptimizer
    _META_OK = True
except Exception as _e:
    log.warning("[RE-C4] MetaOptimizer import KO: %s", _e)
    MetaOptimizer = None
    _META_OK = False

try:
    from .v10_learning_persistence import LearningPersistence
    _PERSIST_OK = True
except Exception as _e:
    log.warning("[RE-C4] LearningPersistence import KO: %s", _e)
    LearningPersistence = None
    _PERSIST_OK = False

try:
    from .v10_risk_shield import RiskShield
    _RISK_OK = True
except Exception as _e:
    log.warning("[RE-C4] RiskShield import KO: %s", _e)
    RiskShield = None
    _RISK_OK = False

# ── Constantes ───────────────────────────────────────────────────────────────

# Rôle de chaque TF dans la décision
TF_ROLE: Dict[str, str] = {
    "M1":  "SCALP_TRIGGER",
    "M5":  "SCALP_TRIGGER",
    "M15": "ENTRY_TRIGGER",
    "M30": "ENTRY_STRUCTURE",
    "H1":  "ENTRY_STRUCTURE",
    "H4":  "CONTEXT_BIAS",
    "D1":  "CONTEXT_BIAS",
}

# TFs qui génèrent des trades directs (pas seulement du contexte)
TRADE_TFS = {"M1", "M5", "M15", "M30", "H1"}

# TFs scalp : trade uniquement si H4 et H1 sont alignés
SCALP_TFS = {"M1", "M5", "M15"}

# Barres chargées pour le replay selon le TF
BARS_BY_TF = {
    "M1": 200, "M5": 200, "M15": 200, "M30": 200,
    "H1": 200, "H4": 200, "D1": 100,
}

# Seuil du biais H4 pour filtre dur (cs_delta strength)
H4_BIAS_THRESHOLD = 0.3

# Seuil boost fractal pour veto dur
FRACTAL_VETO_THRESHOLD = -0.3

# Seuil VSA stopping_volume → HOLD forcé
VSA_STOP_THRESHOLD = True

DEFAULT_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCHF", "USDCAD", "EURJPY",
]
DEFAULT_TFS = ["M1", "M5", "M15", "M30", "H1"]


# ── Dataclasses ──────────────────────────────────────────────────────────────
@dataclass
class DecisionRecord:
    pair: str
    tf: str
    tf_role: str
    timestamp: str
    direction: str
    signal_level: str
    action: str          # BUY / SELL / HOLD
    pipeline: str        # "decide_entry" / "sgl_only" / "fallback"
    # Couche VSA
    vsa_state: str = "N/A"
    vsa_effort: float = 0.0
    vsa_conviction: float = 0.0
    vsa_no_supply: bool = False
    vsa_no_demand: bool = False
    vsa_stopping: bool = False
    vsa_climax: bool = False
    vsa_ok: bool = False
    # Couche Fractal
    fractal_boost: float = 0.0
    fractal_direction: str = "NONE"
    fractal_aligned: bool = False
    h4_bias: float = 0.0
    mtf_aligned: bool = False
    # Couche Fatman
    fatman_signal: str = "N/A"
    fatman_pattern: str = "N/A"
    fatman_strength: float = 0.0
    # Filtres appliqués
    held_reason: str = ""
    # Résultat PnL (rempli post-trade si disponible)
    pnl_pips: float = 0.0
    win: Optional[bool] = None

    def as_dict(self) -> Dict:
        d = asdict(self)
        return d


@dataclass
class PairTFResult:
    pair: str
    tf: str
    tf_role: str
    n_decisions: int = 0
    n_trades: int = 0
    n_wins: int = 0
    n_holds: int = 0
    pnl_pips: float = 0.0
    wr: float = 0.0
    vsa_coverage_pct: float = 0.0
    fractal_coverage_pct: float = 0.0
    mtf_filter_count: int = 0
    decisions: List[Dict] = field(default_factory=list)


@dataclass
class ReplayReport:
    run_id: str
    generated_at: str
    pairs: List[str]
    timeframes: List[str]
    n_total_decisions: int = 0
    n_total_trades: int = 0
    n_wins: int = 0
    global_wr: float = 0.0
    global_pnl_pips: float = 0.0
    avg_sharpe: float = 0.0
    pipeline_dominant: str = "N/A"
    # Couverture modules
    vsa_coverage_pct: float = 0.0
    fractal_coverage_pct: float = 0.0
    mtf_filter_count: int = 0
    # Modules actifs
    modules_active: Dict[str, bool] = field(default_factory=dict)
    tf_role_map: Dict[str, str] = field(default_factory=dict)
    # Détails par paire×TF
    by_pair_tf: List[Dict] = field(default_factory=list)
    # Résumé cycle
    summary: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ── DB helpers ────────────────────────────────────────────────────────────────
def _db_connect(db_path: str) -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None


def _load_bars(
    conn: sqlite3.Connection,
    symbol: str,
    tf: str,
    limit: int,
) -> List[Dict]:
    """Charge les barres OHLCV depuis forces_snapshots (ordre chronologique)."""
    queries = [
        # Table principale V10
        (
            "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
            "real_volume FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), limit),
        ),
        # Table fallback V9
        (
            "SELECT time AS timestamp, open, high, low, close, tick_volume "
            "FROM ohlcv "
            "WHERE symbol=? AND timeframe=? "
            "ORDER BY time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), limit),
        ),
    ]
    for sql, params in queries:
        try:
            rows = conn.execute(sql, params).fetchall()
            if rows:
                bars = []
                for r in reversed(rows):
                    b = dict(r)
                    for k in ("open", "high", "low", "close"):
                        b[k] = float(b.get(k, 0.0) or 0.0)
                    b["tick_volume"] = float(b.get("tick_volume", 0.0) or 0.0)
                    bars.append(b)
                return bars
        except Exception:
            continue
    return []


def _load_h4_bias(conn: sqlite3.Connection, symbol: str, db_path: str) -> float:
    """
    Calcule le biais H4 comme cs_delta = force_base - force_quote.
    Utilise les closes H4 si force_base/force_quote non disponibles.
    Retourne float ∈ [-1..+1], 0.0 si données manquantes (R6 fail-open).
    """
    try:
        # Essai 1 : colonnes force directement dans forces_snapshots
        rows = conn.execute(
            "SELECT force_base, force_quote FROM forces_snapshots "
            "WHERE symbol=? AND timeframe='H4' AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT 10",
            (symbol.upper(),),
        ).fetchall()
        if rows:
            deltas = [
                float(r["force_base"] or 0.0) - float(r["force_quote"] or 0.0)
                for r in rows
                if r["force_base"] is not None and r["force_quote"] is not None
            ]
            if deltas:
                return round(sum(deltas) / len(deltas), 4)
    except Exception:
        pass
    try:
        # Essai 2 : pente des closes H4 normalisée
        rows = conn.execute(
            "SELECT close FROM forces_snapshots "
            "WHERE symbol=? AND timeframe='H4' AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT 30",
            (symbol.upper(),),
        ).fetchall()
        if len(rows) >= 5:
            closes = [float(r["close"]) for r in reversed(rows)]
            n = len(closes)
            xs = list(range(n))
            mx = sum(xs) / n
            my = sum(closes) / n
            num = sum((x - mx) * (c - my) for x, c in zip(xs, closes))
            den = sum((x - mx) ** 2 for x in xs) or 1e-9
            slope = (num / den) / (my or 1.0)
            # Normaliser en [-1, +1]
            return round(max(-1.0, min(1.0, slope * 200)), 4)
    except Exception:
        pass
    return 0.0


# ── Couche VSA ─────────────────────────────────────────────────────────────
def _run_vsa(
    bars: List[Dict],
    symbol: str,
    tf: str,
    direction: str,
) -> Dict:
    """
    Lance compute_vsa sur les barres courantes.
    Retourne un dict normalisé pour la décision.
    R6 : toute exception → dict neutre.
    """
    neutral = {
        "ok": False,
        "state": "NEUTRAL",
        "effort": 0.0,
        "conviction": 0.0,
        "no_supply": False,
        "no_demand": False,
        "stopping": False,
        "climax": False,
        "aligned": False,
        "upgrade": False,
        "downgrade": False,
        "hard_hold": False,
    }
    if not _VSA_OK or compute_vsa is None or not bars:
        return neutral
    try:
        ts = str(bars[-1].get("timestamp", ""))
        result = compute_vsa(
            symbol=symbol,
            timestamp=ts,
            timeframe=tf,
            bars=bars,
        )
        if result.data_insufficient:
            return neutral

        state_val = result.state.value if hasattr(result.state, "value") else str(result.state)
        # Alignement VSA avec direction
        dir_up = direction in ("long", "BUY", "BULLISH", "buy")
        dir_dn = direction in ("short", "SELL", "BEARISH", "sell")
        vsa_bull = state_val in ("MARKUP", "ACCUMULATION")
        vsa_bear = state_val in ("MARKDOWN", "DISTRIBUTION")
        aligned = (dir_up and vsa_bull) or (dir_dn and vsa_bear)
        opposed = (dir_up and vsa_bear) or (dir_dn and vsa_bull)

        # Conviction : effort_vs_result + volume_relative normalisé
        conviction = min(1.0, result.effort_vs_result + min(0.4, result.volume_relative * 0.15))

        # Règles upgrade/downgrade
        upgrade = False
        downgrade = False
        hard_hold = False

        if result.stopping_volume:
            hard_hold = True  # stopping_volume → HOLD dur
        elif aligned and state_val == "ACCUMULATION" or state_val == "MARKUP":
            # Continuation alignée : upgrade A3→A2
            upgrade = True
        elif opposed:
            # Résultat opposé : downgrade A2→A3
            downgrade = True

        return {
            "ok": True,
            "state": state_val,
            "effort": round(result.effort_vs_result, 4),
            "conviction": round(conviction, 4),
            "no_supply": result.no_supply,
            "no_demand": result.no_demand,
            "stopping": result.stopping_volume,
            "climax": result.climax,
            "aligned": aligned,
            "upgrade": upgrade,
            "downgrade": downgrade,
            "hard_hold": hard_hold,
        }
    except Exception as exc:
        log.debug("[VSA] %s/%s fail-open: %s", symbol, tf, exc)
        return neutral


# ── Couche Fatman ─────────────────────────────────────────────────────────
def _run_fatman(
    bars: List[Dict],
    symbol: str,
    tf: str,
    direction: str,
) -> Dict:
    """
    Lance get_fatman_signal sur les barres.
    R6 : toute exception → dict neutre.
    """
    neutral = {
        "ok": False,
        "signal": "NEUTRAL",
        "pattern": "N/A",
        "strength": 0.0,
        "aligned": False,
        "upgrade": False,
        "downgrade": False,
    }
    if not _FATMAN_OK or get_fatman_signal is None or not bars:
        return neutral
    try:
        result = get_fatman_signal(bars=bars, pair=symbol, tf=tf)
        if result is None:
            return neutral
        sig = result.get("signal", "NEUTRAL") if isinstance(result, dict) else getattr(result, "signal", "NEUTRAL")
        pattern = result.get("pattern", "N/A") if isinstance(result, dict) else getattr(result, "pattern", "N/A")
        strength = float(result.get("strength", 0.0) if isinstance(result, dict) else getattr(result, "strength", 0.0))

        dir_up = direction in ("long", "BUY", "BULLISH", "buy")
        dir_dn = direction in ("short", "SELL", "BEARISH", "sell")
        aligned = (dir_up and sig == "BUY") or (dir_dn and sig == "SELL")
        opposed = (dir_up and sig == "SELL") or (dir_dn and sig == "BUY")

        return {
            "ok": True,
            "signal": sig,
            "pattern": str(pattern),
            "strength": round(strength, 4),
            "aligned": aligned,
            "upgrade": aligned and strength > 0.6,
            "downgrade": opposed,
        }
    except Exception as exc:
        log.debug("[FATMAN] %s/%s fail-open: %s", symbol, tf, exc)
        return neutral


# ── Ajustement signal_level ───────────────────────────────────────────────
def _adjust_signal_level(
    signal_level: str,
    vsa: Dict,
    fatman: Dict,
) -> Tuple[str, str]:
    """
    Ajuste le signal_level selon les couches VSA et Fatman.
    Retourne (nouveau_signal_level, raison).

    Ordre de priorité :
      1. VSA stopping_volume  → HOLD_VSA_STOP (dur)
      2. VSA upgrade + Fatman upgrade → A1
      3. VSA upgrade OU Fatman upgrade → A2 (si A3)
      4. VSA downgrade OU Fatman downgrade → A3 (si A2)
      5. Sinon inchangé
    """
    if vsa.get("hard_hold"):
        return "HOLD", "VSA_STOPPING_VOLUME"

    level_map = {"A1": 3, "A2": 2, "A3": 1}
    rev_map = {3: "A1", 2: "A2", 1: "A3"}
    current = level_map.get(signal_level, 2)  # défaut A2

    upgrades = 0
    downgrades = 0

    if vsa.get("upgrade"):
        upgrades += 1
    if fatman.get("upgrade"):
        upgrades += 1
    if vsa.get("downgrade"):
        downgrades += 1
    if fatman.get("downgrade"):
        downgrades += 1

    # Bonus conviction VSA flags
    if vsa.get("no_supply") or vsa.get("no_demand"):
        upgrades += 1

    net = upgrades - downgrades
    new_level = max(1, min(3, current + net))
    reason = ""
    if net > 0:
        reason = f"upgrade+{net}(vsa:{vsa.get('state','?')},fatman:{fatman.get('signal','?')})"
    elif net < 0:
        reason = f"downgrade{net}(vsa:{vsa.get('state','?')},fatman:{fatman.get('signal','?')})"

    return rev_map[new_level], reason


# ── Cœur de la décision barre par barre ──────────────────────────────────
def _decide_one(
    pair: str,
    tf: str,
    tf_role: str,
    bars: List[Dict],
    h4_bias: float,
    fractal_conf: Optional[Any],
    db_path: str,
    session: str = "LONDON",
) -> Optional[DecisionRecord]:
    """
    Pipeline complet pour UNE barre sur une paire×TF.
    Retourne DecisionRecord ou None (skip silencieux).
    """
    if not bars or len(bars) < 10:
        return None

    cur = bars[-1]
    ts = str(cur.get("timestamp", datetime.now(timezone.utc).isoformat()))

    # ── 1. SignalGeneratorLive ────────────────────────────────────────────
    sgl_direction = "long"
    sgl_signal_level = "A2"
    sgl_pipeline = "fallback"

    if _SGL_OK and SignalGeneratorLive is not None:
        try:
            sgl = SignalGeneratorLive()
            sig_out = sgl.generate(symbol=pair, timeframe=tf, bars=bars)
            if sig_out is not None:
                sgl_direction = sig_out.get("direction", "long") if isinstance(sig_out, dict) else getattr(sig_out, "direction", "long")
                sgl_signal_level = sig_out.get("signal_level", "A2") if isinstance(sig_out, dict) else getattr(sig_out, "signal_level", "A2")
                sgl_pipeline = "signal_generator_live"
        except Exception as exc:
            log.debug("[SGL] %s/%s fail-open: %s", pair, tf, exc)

    # ── 2. Couche VSA (structure) ─────────────────────────────────────────
    vsa = _run_vsa(bars, pair, tf, sgl_direction)

    # ── 3. Couche Fatman (conviction institutionnelle) ────────────────────
    fatman = _run_fatman(bars, pair, tf, sgl_direction)

    # ── 4. Ajustement signal_level ────────────────────────────────────────
    signal_level, adjust_reason = _adjust_signal_level(sgl_signal_level, vsa, fatman)

    # ── 5. Filtres durs (ordre de priorité) ──────────────────────────────
    held_reason = ""

    # 5a. VSA stopping volume
    if signal_level == "HOLD":
        held_reason = adjust_reason

    # 5b. Biais H4 opposé
    if not held_reason:
        dir_up = sgl_direction in ("long", "BUY", "buy")
        h4_opposes = (dir_up and h4_bias < -H4_BIAS_THRESHOLD) or \
                     (not dir_up and h4_bias > H4_BIAS_THRESHOLD)
        if h4_opposes:
            held_reason = f"H4_BIAS_OPPOSE(h4={h4_bias:.3f},dir={sgl_direction})"

    # 5c. Scalp TF : filtre strict — H4 doit être aligné
    if not held_reason and tf_role == "SCALP_TRIGGER":
        h4_aligned = (dir_up and h4_bias > 0.1) or (not dir_up and h4_bias < -0.1)
        if not h4_aligned:
            held_reason = f"SCALP_NO_H4_ALIGN(h4={h4_bias:.3f})"

    # 5d. Fractal boost veto
    fractal_boost = 0.0
    fractal_dir = "NONE"
    fractal_aligned = False
    if not held_reason and _FRACTAL_OK and fractal_conf is not None:
        try:
            cine = compute_fast_cinematics(
                symbol=pair,
                decision_timeframe=tf,
                db_path=db_path,
            )
            fsig = fractal_signal(
                confluence=fractal_conf,
                cinematics=cine,
                decision_direction=sgl_direction,
            )
            fractal_boost = fsig.boost
            fractal_dir = fsig.direction
            fractal_aligned = fsig.aligned
            if fractal_boost < FRACTAL_VETO_THRESHOLD:
                held_reason = f"FRACTAL_VETO(boost={fractal_boost:.3f})"
        except Exception as exc:
            log.debug("[FRACTAL] %s/%s fail-open: %s", pair, tf, exc)

    # ── 6. decide_entry (pipeline complet) ───────────────────────────────
    action = "HOLD" if held_reason else "HOLD"
    pipeline_used = sgl_pipeline

    if not held_reason:
        if _DECIDE_OK and decide_entry is not None:
            try:
                import inspect
                sig = inspect.signature(decide_entry)
                kwargs: Dict[str, Any] = {}
                params = sig.parameters
                if "pair" in params:      kwargs["pair"] = pair
                if "symbol" in params:    kwargs["symbol"] = pair
                if "tf" in params:        kwargs["tf"] = tf
                if "timeframe" in params: kwargs["timeframe"] = tf
                if "ts" in params:        kwargs["ts"] = ts
                if "timestamp" in params: kwargs["timestamp"] = ts
                if "direction" in params: kwargs["direction"] = sgl_direction
                if "signal_level" in params: kwargs["signal_level"] = signal_level
                if "session" in params:   kwargs["session"] = session
                if "bars" in params:      kwargs["bars"] = bars
                if "fractal_boost" in params: kwargs["fractal_boost"] = fractal_boost
                result = decide_entry(**kwargs)
                if result is not None:
                    action_raw = result.get("action", "HOLD") if isinstance(result, dict) else getattr(result, "action", "HOLD")
                    action = str(action_raw).upper()
                    pipeline_used = "decide_entry+sgl"
                else:
                    action = "HOLD"
            except Exception as exc:
                log.debug("[DECIDE] %s/%s fail-open: %s", pair, tf, exc)
                # Fallback : on prend la direction du SGL directement
                action = "BUY" if sgl_direction in ("long", "buy") else "SELL"
                pipeline_used = "sgl_direct_fallback"
        else:
            action = "BUY" if sgl_direction in ("long", "buy") else "SELL"
            pipeline_used = "sgl_direct_fallback"

    # ── 7. Construit le record ────────────────────────────────────────────
    mtf_aligned = fractal_aligned and (abs(h4_bias) > 0.1)

    rec = DecisionRecord(
        pair=pair,
        tf=tf,
        tf_role=tf_role,
        timestamp=ts,
        direction=sgl_direction,
        signal_level=signal_level,
        action=action,
        pipeline=pipeline_used,
        vsa_state=vsa["state"],
        vsa_effort=vsa["effort"],
        vsa_conviction=vsa["conviction"],
        vsa_no_supply=vsa["no_supply"],
        vsa_no_demand=vsa["no_demand"],
        vsa_stopping=vsa["stopping"],
        vsa_climax=vsa["climax"],
        vsa_ok=vsa["ok"],
        fractal_boost=fractal_boost,
        fractal_direction=fractal_dir,
        fractal_aligned=fractal_aligned,
        h4_bias=h4_bias,
        mtf_aligned=mtf_aligned,
        fatman_signal=fatman["signal"],
        fatman_pattern=fatman["pattern"],
        fatman_strength=fatman["strength"],
        held_reason=held_reason,
    )
    return rec


# ── Replay par paire×TF ───────────────────────────────────────────────────
def _replay_pair_tf(
    pair: str,
    tf: str,
    db_path: str,
    limit: int,
    session: str = "LONDON",
) -> PairTFResult:
    """
    Rejoue `limit` barres d'une paire×TF.
    Calcule le biais H4 une fois en amont (filtre de contexte).
    Calcule la confluence fractale une fois en amont.
    Puis décide barre par barre avec fenêtre glissante (min 30 barres).
    """
    tf_role = TF_ROLE.get(tf, "ENTRY_STRUCTURE")
    result = PairTFResult(pair=pair, tf=tf, tf_role=tf_role)

    if tf not in TRADE_TFS:
        # H4/D1 : on ne génère pas de trades directs, juste du contexte
        return result

    conn = _db_connect(db_path)
    if conn is None:
        log.warning("[REPLAY] DB inaccessible: %s", db_path)
        return result

    try:
        # ── Biais H4 (contexte — calculé une seule fois par paire) ────────
        h4_bias = _load_h4_bias(conn, pair, db_path)

        # ── Confluence fractale (calculée une seule fois par paire) ───────
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

        # ── Barres pour ce TF ──────────────────────────────────────────────
        all_bars = _load_bars(conn, pair, tf, limit)
        if not all_bars:
            log.warning("[REPLAY] 0 barres pour %s/%s", pair, tf)
            return result

        # ── Stats pour la couverture ───────────────────────────────────────
        n_vsa_ok = 0
        n_fractal_ok = 0
        n_mtf_filtered = 0

        # ── Replay barre par barre (fenêtre glissante min 30 barres) ──────
        WIN_SIZE = 30
        decisions: List[DecisionRecord] = []

        for i in range(WIN_SIZE, len(all_bars)):
            window = all_bars[max(0, i - 200): i + 1]  # max 200 barres d'historique
            rec = _decide_one(
                pair=pair,
                tf=tf,
                tf_role=tf_role,
                bars=window,
                h4_bias=h4_bias,
                fractal_conf=fractal_conf,
                db_path=db_path,
                session=session,
            )
            if rec is None:
                continue

            decisions.append(rec)
            result.n_decisions += 1

            if rec.vsa_ok:
                n_vsa_ok += 1
            if rec.fractal_boost != 0.0:
                n_fractal_ok += 1
            if rec.held_reason and ("H4_BIAS" in rec.held_reason or "SCALP_NO_H4" in rec.held_reason or "FRACTAL_VETO" in rec.held_reason):
                n_mtf_filtered += 1

            if rec.action in ("BUY", "SELL"):
                result.n_trades += 1
                # Simulation PnL simplifiée (mean reversion heuristique)
                pnl = _simulate_pnl(all_bars, i, rec.action, pair)
                rec.pnl_pips = pnl
                rec.win = pnl > 0
                result.pnl_pips += pnl
                if pnl > 0:
                    result.n_wins += 1
            else:
                result.n_holds += 1

        # ── Calcul WR et couvertures ───────────────────────────────────────
        if result.n_trades > 0:
            result.wr = round(result.n_wins / result.n_trades, 4)
        if result.n_decisions > 0:
            result.vsa_coverage_pct = round(n_vsa_ok / result.n_decisions, 4)
            result.fractal_coverage_pct = round(n_fractal_ok / result.n_decisions, 4)
        result.mtf_filter_count = n_mtf_filtered

        result.decisions = [d.as_dict() for d in decisions]

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return result


def _simulate_pnl(
    bars: List[Dict],
    entry_idx: int,
    action: str,
    pair: str,
    tp_pips: float = 15.0,
    sl_pips: float = 10.0,
    max_bars_hold: int = 5,
) -> float:
    """
    Simulation PnL simplifiée (heuristique backtest léger).
    TP = 15 pips, SL = 10 pips, max 5 barres de tenue.
    Retourne pips gagnés (positif) ou perdus (négatif).
    """
    pip = 0.0001 if not pair.upper().endswith("JPY") else 0.01
    entry_close = float(bars[entry_idx].get("close", 0.0) or 0.0)
    if entry_close == 0:
        return 0.0

    tp_price = entry_close + tp_pips * pip * (1 if action == "BUY" else -1)
    sl_price = entry_close - sl_pips * pip * (1 if action == "BUY" else -1)

    for j in range(entry_idx + 1, min(entry_idx + 1 + max_bars_hold, len(bars))):
        high = float(bars[j].get("high", entry_close) or entry_close)
        low = float(bars[j].get("low", entry_close) or entry_close)

        if action == "BUY":
            if high >= tp_price:
                return tp_pips
            if low <= sl_price:
                return -sl_pips
        else:  # SELL
            if low <= tp_price:
                return tp_pips
            if high >= sl_price:
                return -sl_pips

    # Pas touché TP/SL : exit au close final
    exit_close = float(bars[min(entry_idx + max_bars_hold, len(bars) - 1)].get("close", entry_close) or entry_close)
    pnl_raw = (exit_close - entry_close) * (1 if action == "BUY" else -1)
    return round(pnl_raw / pip, 2)


# ── ReplayEngine (API publique) ───────────────────────────────────────────
class ReplayEngine:
    """
    Orchestre le replay multi-paires × multi-TF avec pipeline multifractal V10.

    Usage :
        engine = ReplayEngine(db_path="data/powerflow.db")
        report = engine.run_all(pairs=[...], timeframes=[...], limit=200)
        import json
        print(json.dumps(report.as_dict(), indent=2))
    """

    def __init__(
        self,
        db_path: str = "data/powerflow.db",
        session: str = "LONDON",
    ):
        self.db_path = db_path
        self.session = session
        self._modules_active = {
            "signal_generator_live": _SGL_OK,
            "decide_entry": _DECIDE_OK,
            "vsa": _VSA_OK,
            "fractal_context": _FRACTAL_OK,
            "fatman_bible": _FATMAN_OK,
            "rl_adapter": _RL_OK,
            "meta_optimizer": _META_OK,
            "learning_persistence": _PERSIST_OK,
            "risk_shield": _RISK_OK,
        }
        log.info(
            "[ReplayEngine C4] init — modules: %s",
            {k: v for k, v in self._modules_active.items()},
        )

    def run_all(
        self,
        pairs: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        limit: int = 200,
        workers: int = 4,
    ) -> ReplayReport:
        """
        Lance le replay sur toutes les combinaisons paires×TF en parallèle.

        Parameters
        ----------
        pairs       : liste de symboles (défaut = 7 majeurs)
        timeframes  : liste de TFs (défaut = M1/M5/M15/M30/H1)
        limit       : nombre max de barres par paire×TF
        workers     : threads parallèles

        Returns
        -------
        ReplayReport (sérialisable via .as_dict())
        """
        if pairs is None:
            pairs = DEFAULT_PAIRS
        if timeframes is None:
            timeframes = DEFAULT_TFS

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report = ReplayReport(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            pairs=list(pairs),
            timeframes=list(timeframes),
            modules_active=dict(self._modules_active),
            tf_role_map=dict(TF_ROLE),
        )

        combos = [
            (pair, tf)
            for pair in pairs
            for tf in timeframes
            if tf in TRADE_TFS
        ]
        log.info("[ReplayEngine C4] %d combos à rejouer", len(combos))

        all_results: List[PairTFResult] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _replay_pair_tf,
                    pair, tf, self.db_path, limit, self.session,
                ): (pair, tf)
                for pair, tf in combos
            }
            for fut in as_completed(futs):
                pair, tf = futs[fut]
                try:
                    res = fut.result(timeout=60)
                    all_results.append(res)
                except Exception as exc:
                    log.warning("[REPLAY] %s/%s exception: %s", pair, tf, exc)
                    log.debug(traceback.format_exc())
                    all_results.append(PairTFResult(pair=pair, tf=tf, tf_role=TF_ROLE.get(tf, "?")))

        # ── Agrégation globale ────────────────────────────────────────────
        total_decisions = sum(r.n_decisions for r in all_results)
        total_trades = sum(r.n_trades for r in all_results)
        total_wins = sum(r.n_wins for r in all_results)
        total_pnl = sum(r.pnl_pips for r in all_results)
        total_vsa_ok = sum(r.n_decisions * r.vsa_coverage_pct for r in all_results)
        total_fractal_ok = sum(r.n_decisions * r.fractal_coverage_pct for r in all_results)
        total_mtf = sum(r.mtf_filter_count for r in all_results)

        # Pipeline dominant
        from collections import Counter
        pipeline_counter: Counter = Counter()
        for r in all_results:
            for d in r.decisions:
                pipeline_counter[d.get("pipeline", "fallback")] += 1
        pipeline_dominant = pipeline_counter.most_common(1)[0][0] if pipeline_counter else "N/A"

        # Sharpe simplifié
        all_pnls = [
            d.get("pnl_pips", 0.0)
            for r in all_results
            for d in r.decisions
            if d.get("action") in ("BUY", "SELL")
        ]
        sharpe = 0.0
        if len(all_pnls) > 1:
            mean_pnl = sum(all_pnls) / len(all_pnls)
            std_pnl = (sum((x - mean_pnl) ** 2 for x in all_pnls) / len(all_pnls)) ** 0.5
            sharpe = round(mean_pnl / std_pnl, 3) if std_pnl > 0 else 0.0

        report.n_total_decisions = total_decisions
        report.n_total_trades = total_trades
        report.n_wins = total_wins
        report.global_wr = round(total_wins / total_trades, 4) if total_trades > 0 else 0.0
        report.global_pnl_pips = round(total_pnl, 2)
        report.avg_sharpe = sharpe
        report.pipeline_dominant = pipeline_dominant
        report.vsa_coverage_pct = round(total_vsa_ok / total_decisions, 4) if total_decisions > 0 else 0.0
        report.fractal_coverage_pct = round(total_fractal_ok / total_decisions, 4) if total_decisions > 0 else 0.0
        report.mtf_filter_count = total_mtf
        report.by_pair_tf = [
            {
                "pair": r.pair, "tf": r.tf, "role": r.tf_role,
                "n_decisions": r.n_decisions, "n_trades": r.n_trades,
                "n_wins": r.n_wins, "n_holds": r.n_holds,
                "wr": r.wr, "pnl_pips": round(r.pnl_pips, 2),
                "vsa_coverage": r.vsa_coverage_pct,
                "fractal_coverage": r.fractal_coverage_pct,
                "mtf_filter_count": r.mtf_filter_count,
            }
            for r in all_results
        ]
        report.summary = {
            "cycle": 4,
            "c4_features": [
                "vsa_branched", "fractal_context_branched",
                "fatman_branched", "h4_bias_filter",
                "scalp_tf_h4_gate", "mtf_3layer_pipeline",
            ],
            "tf_roles": TF_ROLE,
            "modules_active": self._modules_active,
            "global_wr_c4": report.global_wr,
            "global_pnl_c4": report.global_pnl_pips,
            "vsa_coverage_pct": report.vsa_coverage_pct,
            "fractal_coverage_pct": report.fractal_coverage_pct,
            "mtf_filter_count": total_mtf,
            "pipeline_dominant": pipeline_dominant,
            "n_combos": len(combos),
        }

        log.info(
            "[ReplayEngine C4] DONE — trades=%d WR=%.1f%% PnL=%.0f pips Sharpe=%.2f",
            total_trades,
            report.global_wr * 100,
            report.global_pnl_pips,
            sharpe,
        )
        return report


# ── Compatibilité import direct ───────────────────────────────────────────
__all__ = [
    "ReplayEngine",
    "ReplayReport",
    "PairTFResult",
    "DecisionRecord",
    "TF_ROLE",
    "TRADE_TFS",
    "SCALP_TFS",
    "DEFAULT_PAIRS",
    "DEFAULT_TFS",
]
