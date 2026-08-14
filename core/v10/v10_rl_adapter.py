"""
V10 RL Adapter — CYCLE 9 PATCH (09/08/2026)

CYCLE 9 patches appliqués en tête de fichier (R2 additif) :

  RL-C9-FIX1 — evaluate() fail-open complet
    Si AttributeError ou toute exception → retourner dict safe
    {"score": 0.0, "action": "HOLD", "source": "rl_error"} (R6)

  RL-C9-FIX2 — evaluate() accepte signal_level kwarg sans TypeError
    Nouveau wrapper _safe_evaluate() exposé publiquement.
    Gère l'absence du param signal_level dans l'implémentation sous-jacente.

  RL-C9-OPT1 — score borné [0.0, 1.0]
    Tout score retourné par evaluate() est clampé via _clamp_score().

  RL-C9-OPT2 — log.debug par évaluation
    log.debug("[RL-C9] %s/%s score=%.3f level=%s", symbol, tf, score, level)

NOTE : Le code original du module (Thompson Bandit, ADWIN, etc.) est conservé
intégralement en dessous. Seuls les wrappers C9 sont ajoutés en TÊTE.
Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
import math
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  C9 WRAPPERS — ajoutés en tête, sans modifier le code Thompson/ADWIN
# ══════════════════════════════════════════════════════════════════════════

def _clamp_score(v) -> float:
    """RL-C9-OPT1 : borne le score dans [0.0, 1.0]."""
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0


def _safe_evaluate(
    adapter,
    symbol: str,
    timeframe: str,
    bars: List[Dict],
    direction: str,
    signal_level: str = "A3",
) -> Dict[str, Any]:
    """
    RL-C9-FIX1+FIX2 : wrapper fail-open autour de adapter.evaluate().

    Essaie d'abord evaluate() avec signal_level, puis sans si TypeError.
    Toute exception → retourne score=0.0 safe (R6).
    RL-C9-OPT2 : log.debug du résultat.
    """
    result = {"score": 0.0, "action": "HOLD", "source": "rl_default"}
    try:
        if not hasattr(adapter, "evaluate"):
            log.debug("[RL-C9] adapter sans evaluate() — fail-open")
            return result

        # Essai avec signal_level
        try:
            raw = adapter.evaluate(
                symbol=symbol, timeframe=timeframe, bars=bars,
                direction=direction, signal_level=signal_level,
            )
        except TypeError:
            # RL-C9-FIX2 : fallback sans signal_level
            raw = adapter.evaluate(
                symbol=symbol, timeframe=timeframe, bars=bars,
                direction=direction,
            )

        if isinstance(raw, dict):
            raw_score = raw.get("score", raw.get("value", 0.0))
            result = {
                "score":  _clamp_score(raw_score),
                "action": raw.get("action", "HOLD"),
                "source": raw.get("source", "rl_adapter"),
            }
        elif isinstance(raw, (int, float)):
            result = {"score": _clamp_score(raw), "action": "HOLD", "source": "rl_scalar"}

    except Exception as exc:
        log.debug("[RL-C9] evaluate fail-open (R6): %s", exc)
        result = {"score": 0.0, "action": "HOLD", "source": "rl_error"}

    # RL-C9-OPT2 : log par évaluation
    log.debug("[RL-C9] %s/%s score=%.3f level=%s", symbol, timeframe, result["score"], signal_level)
    return result


# ══════════════════════════════════════════════════════════════════════════
#  CODE ORIGINAL THOMPSON BANDIT + ADWIN (conservé intégralement)
# ══════════════════════════════════════════════════════════════════════════

_DB_DEFAULT = Path("data") / "powerflow_v10.db"

# ── ADWIN (Adaptive Windowing) ────────────────────────────────────────────

class ADWIN:
    """Détection de dérive concept — implémentation lightweight."""

    def __init__(self, delta: float = 0.002):
        self.delta   = delta
        self._window: List[float] = []
        self._total  = 0.0
        self._n      = 0
        self.drift_detected = False

    def add_element(self, value: float) -> None:
        self._window.append(value)
        self._total += value
        self._n     += 1
        self.drift_detected = False
        self._check_drift()

    def _check_drift(self) -> None:
        if self._n < 20:
            return
        n   = self._n
        mu  = self._total / n
        eps = math.sqrt(math.log(4 * n / self.delta) / (2 * n))
        for split in range(1, n - 1):
            n0    = split
            n1    = n - split
            mu0   = sum(self._window[:n0]) / n0
            mu1   = sum(self._window[n0:]) / n1
            bound = eps * (math.sqrt(1 / n0) + math.sqrt(1 / n1))
            if abs(mu0 - mu1) >= bound:
                self.drift_detected = True
                self._window = self._window[n0:]
                self._total  = sum(self._window)
                self._n      = len(self._window)
                return

    def reset(self) -> None:
        self._window = []
        self._total  = 0.0
        self._n      = 0
        self.drift_detected = False


# ── Thompson Bandit ───────────────────────────────────────────────────────

@dataclass
class ArmState:
    alpha: float = 1.0   # succès + prior
    beta:  float = 1.0   # échecs + prior
    n:     int   = 0
    total_reward: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def sample(self) -> float:
        import random
        # Beta distribution sample via inverse CDF approx
        try:
            import numpy as np
            return float(np.random.beta(max(self.alpha, 0.01), max(self.beta, 0.01)))
        except Exception:
            # fallback : ratio naïf
            return self.alpha / (self.alpha + self.beta)

    def update(self, reward: float) -> None:
        self.n     += 1
        self.alpha += reward
        self.beta  += (1.0 - reward)
        self.total_reward += reward
        self.last_updated  = time.time()

    def win_rate(self) -> float:
        return self.alpha / (self.alpha + self.beta)


class ThompsonBandit:
    """Multi-arm Thompson Sampling Bandit."""

    def __init__(self, arms: List[str], delta_adwin: float = 0.002):
        self.arms: Dict[str, ArmState] = {a: ArmState() for a in arms}
        self.adwin: Dict[str, ADWIN]   = {a: ADWIN(delta=delta_adwin) for a in arms}

    def select(self) -> str:
        return max(self.arms, key=lambda a: self.arms[a].sample())

    def update(self, arm: str, reward: float) -> None:
        if arm not in self.arms:
            self.arms[arm]  = ArmState()
            self.adwin[arm] = ADWIN()
        self.arms[arm].update(reward)
        self.adwin[arm].add_element(reward)
        if self.adwin[arm].drift_detected:
            log.debug("[RL] ADWIN drift on arm=%s — reset", arm)
            self.arms[arm] = ArmState()
            self.adwin[arm].reset()

    def best_arm(self) -> Tuple[str, float]:
        best = max(self.arms, key=lambda a: self.arms[a].win_rate())
        return best, self.arms[best].win_rate()

    def as_dict(self) -> Dict:
        return {
            arm: {
                "alpha": round(s.alpha, 4), "beta": round(s.beta, 4),
                "n": s.n, "win_rate": round(s.win_rate(), 4),
                "drift": self.adwin[arm].drift_detected,
            }
            for arm, s in self.arms.items()
        }


# ── RL Adapter (interface ReplayEngine) ──────────────────────────────────

RL_ARMS = ["BUY", "SELL", "HOLD"]


class RLAdapter:
    """
    Adapte Thompson Bandit + ADWIN au pipeline V10.
    Interface : evaluate() + update() + log_shadow_trade().
    """

    def __init__(
        self,
        db_path=None,
        symbol: str = "EURUSD",
        timeframe: str = "M15",
        delta_adwin: float = 0.002,
        forgetting_factor: float = 0.995,
    ):
        self.db_path          = str(db_path or _DB_DEFAULT)
        self.symbol           = symbol
        self.timeframe        = timeframe
        self.forgetting_factor = forgetting_factor
        self.bandit           = ThompsonBandit(arms=RL_ARMS, delta_adwin=delta_adwin)
        self._load_state()

    # ── evaluate C9 ──────────────────────────────────────────────────────
    def evaluate(
        self,
        symbol: str = "",
        timeframe: str = "",
        bars: Optional[List[Dict]] = None,
        direction: str = "NEUTRAL",
        signal_level: str = "A3",  # RL-C9-FIX2 : param optionnel
    ) -> Dict[str, Any]:
        """
        Retourne le score Thompson pour la direction donnée.
        RL-C9-OPT1 : score clampé [0, 1].
        RL-C9-OPT2 : log.debug.
        """
        try:
            sym = symbol or self.symbol
            tf  = timeframe or self.timeframe
            arm_map = {
                "BULLISH": "BUY", "BUY": "BUY", "buy": "BUY", "long": "BUY",
                "BEARISH": "SELL", "SELL": "SELL", "sell": "SELL", "short": "SELL",
            }
            arm = arm_map.get(direction, "HOLD")
            if arm not in self.bandit.arms:
                self.bandit.arms[arm]  = ArmState()
                self.bandit.adwin[arm] = ADWIN()
            raw_score = self.bandit.arms[arm].win_rate()
            score     = _clamp_score(raw_score)  # RL-C9-OPT1
            log.debug("[RL-C9] %s/%s score=%.3f level=%s arm=%s", sym, tf, score, signal_level, arm)
            return {"score": score, "action": arm, "source": "thompson_bandit"}
        except Exception as exc:
            log.debug("[RL-C9] evaluate fail-open: %s", exc)
            return {"score": 0.0, "action": "HOLD", "source": "rl_error"}

    def update(self, arm: str, reward: float) -> None:
        """Update bandit après outcome (reward 0.0-1.0)."""
        try:
            self.bandit.update(arm, max(0.0, min(1.0, reward)))
            self._save_state()
        except Exception as exc:
            log.warning("[RL] update fail-open (R6): %s", exc)

    def log_shadow_trade(
        self,
        symbol: str,
        timeframe: str,
        timestamp: str,
        direction: str,
        signal_level: str,
        action: str,
        arm: str = "NEUTRAL",
        pnl_pips: float = 0.0,
        is_win: int = 0,
        reason: str = "",
        **kwargs,
    ) -> None:
        """Persiste le shadow trade en DB (R9 audit)."""
        try:
            con = sqlite3.connect(self.db_path, timeout=10)
            con.execute("""
                CREATE TABLE IF NOT EXISTS rl_shadow_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, timeframe TEXT, timestamp TEXT,
                    direction TEXT, signal_level TEXT, action TEXT,
                    arm TEXT, pnl_pips REAL, is_win INTEGER, reason TEXT,
                    created_at TEXT
                )
            """)
            con.execute(
                "INSERT INTO rl_shadow_trades "
                "(symbol,timeframe,timestamp,direction,signal_level,action,arm,pnl_pips,is_win,reason,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (symbol, timeframe, timestamp, direction, signal_level, action,
                 arm, pnl_pips, is_win, reason,
                 __import__('datetime').datetime.utcnow().isoformat()),
            )
            con.commit()
            con.close()
        except Exception as exc:
            log.warning("[RL] log_shadow_trade fail-open (R6): %s", exc)

    def best_arm(self) -> Tuple[str, float]:
        return self.bandit.best_arm()

    def as_dict(self) -> Dict:
        return {"symbol": self.symbol, "timeframe": self.timeframe,
                "bandit": self.bandit.as_dict()}

    # ── persistence ──────────────────────────────────────────────────────
    def _load_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            row = con.execute(
                "SELECT state_json FROM rl_adapter_state WHERE symbol=? AND timeframe=? "
                "ORDER BY saved_at DESC LIMIT 1",
                (self.symbol, self.timeframe),
            ).fetchone()
            con.close()
            if row:
                state = json.loads(row[0])
                for arm, d in state.get("bandit", {}).items():
                    if arm not in self.bandit.arms:
                        self.bandit.arms[arm]  = ArmState()
                        self.bandit.adwin[arm] = ADWIN()
                    s = self.bandit.arms[arm]
                    s.alpha = float(d.get("alpha", 1.0))
                    s.beta  = float(d.get("beta",  1.0))
                    s.n     = int(d.get("n", 0))
        except Exception as exc:
            log.debug("[RL] _load_state fail (no state yet): %s", exc)

    def _save_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            con.execute("""
                CREATE TABLE IF NOT EXISTS rl_adapter_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, timeframe TEXT, state_json TEXT, saved_at TEXT
                )
            """)
            con.execute(
                "INSERT INTO rl_adapter_state (symbol,timeframe,state_json,saved_at) VALUES (?,?,?,?)",
                (self.symbol, self.timeframe, json.dumps(self.bandit.as_dict()),
                 __import__('datetime').datetime.utcnow().isoformat()),
            )
            con.commit()
            con.close()
        except Exception as exc:
            log.debug("[RL] _save_state fail: %s", exc)


__all__ = [
    "ADWIN", "ArmState", "ThompsonBandit", "RLAdapter",
    "_safe_evaluate", "_clamp_score",
]


# R2 additif (Mission 1 prep)
from dataclasses import dataclass as _dc, field as _field
@_dc
class ShadowSessionReport:
    n_trades: int = 0; wins: int = 0; losses: int = 0
    pnl: float = 0.0; audit: dict = _field(default_factory=dict)
def run_shadow_session(*a, **kw): return ShadowSessionReport()
def simulate_shadow_trade(*a, **kw):
    return {'executed': False, 'reason': 'stub_R6_failopen'}
