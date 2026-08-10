"""V10 Live Monitor — boucle polling + alertes (ÉTAPE 7).

Plan HERMES_PLAN_V10 §MODULE 7 :
  - Boucle polling MT4/MT5 → currency_strength → signal_engine
  - Fréquence : 60s (M5/M15) ou 30s (M1)
  - Alerte : webhook/telegram sur signal fort (S1/S2 du plan)

Ce module agrège :
  - v10_signal_engine.compute_signal_engine (ÉTAPE 3)
  - v10_session_filter.classify_session (ÉTAPE 4, pré-existant)
  - v10_atr_manager.compute_sl_tp (ÉTAPE 5)
  - v10_fatman_editor.compute_fatman_editor (ÉTAPE 1)

Doctrine V10 : R2 additif pur (0 import core/v9/), R6 fail-open
(data manquante → pas d'alerte), R10 (compute only, pas d'ordre
réel — voir V9_EXECUTION_ENABLED).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


def _signal_engine_safe(symbol, pair, ts, tf, **kwargs):
    try:
        from .v10_signal_engine import compute_signal_engine
        return compute_signal_engine(symbol, pair, ts, tf, **kwargs)
    except Exception:
        return None


def _session_filter_safe(ts):
    try:
        from .v10_session_filter import classify_session
        return classify_session(ts)
    except Exception:
        return None


def _vol_forecast_safe(closes, **kwargs):
    try:
        from .v10_vol_forecast import forecast_vol, sl_tp_combined_atr_vol
        return forecast_vol(closes, **kwargs), sl_tp_combined_atr_vol
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────
# Config (R8 surchargeable)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: Dict = {
    "poll_interval_seconds": 60,
    "alert_min_leverage": 30,
    "alert_min_signal_fatman": "MOYEN",
    "max_signals_per_poll": 5,
    "enable_telegram_alert": False,
    "enable_webhook_alert": False,
    "polling_timeframe_default": "M5",
    "use_vol_forecast": True,  # S23-B: enable GARCH/EWMA vol forecast for SL/TP
    "vol_forecast_method": "auto",  # "auto" | "garch" | "ewma"
}

# Alertes configurées par défaut
ALERT_SOURCES_REGISTERED: Dict = {
    "telegram": ("hermes_send_report_telegram.py", "send_telegram"),
    "webhook": ("urllib.request", "Request"),
}

# ─────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────
@dataclass
class MonitorTickResult:
    """Résultat d'un poll de surveillance."""
    timestamp: str = ""
    n_pairs_checked: int = 0
    n_signals_total: int = 0
    n_signals_emitted: int = 0
    alerted_pairs: List[str] = field(default_factory=list)
    signals: List[Dict] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "n_pairs_checked": self.n_pairs_checked,
            "n_signals_total": self.n_signals_total,
            "n_signals_emitted": self.n_signals_emitted,
            "alerted_pairs": self.alerted_pairs,
            "signals": self.signals,
            "notes": dict(self.notes),
        }


@dataclass
class LiveAlert:
    """Alerte émise sur un signal fort (au moins leverage >= threshold)."""
    timestamp: str = ""
    pair: str = ""
    direction: str = ""
    leverage: int = 0
    score_composite: float = 0.0
    fatman_signal: str = ""
    fatman_delta: float = 0.0
    atr_pips: float = 0.0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    session: str = ""
    severity: str = "INFO"  # INFO/WARN/ALERT/CRITICAL
    message: str = ""

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "pair": self.pair, "direction": self.direction,
            "leverage": self.leverage,
            "score_composite": round(self.score_composite, 1),
            "fatman_signal": self.fatman_signal,
            "fatman_delta": round(self.fatman_delta, 3),
            "atr_pips": round(self.atr_pips, 1),
            "sl_pips": round(self.sl_pips, 1),
            "tp_pips": round(self.tp_pips, 1),
            "session": self.session,
            "severity": self.severity,
            "message": self.message,
        }


# ─────────────────────────────────────────────────────────────────────
# Emetteur d'alertes (R6 fail-open : pas d'alerte si source absente)
# ─────────────────────────────────────────────────────────────────────
def emit_alerts(alerts: List[LiveAlert], *,
                sources: Optional[Dict] = None,
                config: Optional[Dict] = None) -> Dict:
    """Émet les alertes sur les canaux configurés.

    Returns dict {source: n_alerted}.
    """
    cfg = config or DEFAULT_CONFIG
    sources = sources or {}
    out: Dict[str, int] = {}
    if not alerts:
        return out

    if cfg.get("enable_webhook_alert"):
        try:
            import urllib.request as _urlreq
            import json as _json
            payload = _json.dumps(
                [a.as_dict() for a in alerts]
            ).encode()
            req = _urlreq.Request(
                "http://localhost/v10/alerts",
                data=payload, headers={"Content-Type": "application/json"},
            )
            try:
                _urlreq.urlopen(req, timeout=2).read()
                out["webhook"] = len(alerts)
            except Exception:
                out["webhook"] = 0
        except Exception:
            out["webhook"] = 0

    if cfg.get("enable_telegram_alert"):
        try:
            import subprocess as _sp
            for a in alerts:
                text = a.message
                try:
                    _sp.run(
                        ["python", "scripts/hermes_send_report_telegram.py",
                         text],
                        timeout=5, capture_output=True,
                    )
                except Exception:
                    pass
            out["telegram"] = len(alerts)
        except Exception:
            out["telegram"] = 0

    return out


# ─────────────────────────────────────────────────────────────────────
# Calcule un poll
# ─────────────────────────────────────────────────────────────────────
def monitor_tick(
    pairs_bars: Dict[str, Dict[str, List[float]]],
    *,
    timestamp: Optional[str] = None,
    pairs_h1_bars: Optional[Dict[str, List[dict]]] = None,
    config: Optional[Dict] = None,
) -> Tuple[MonitorTickResult, List[LiveAlert]]:
    """Exécute un tick de surveillance et retourne (résultat, alertes).

    pairs_bars : { pair : { tf : [closes] } } pour le moteur.
    pairs_h1_bars : { pair : [bars OHLC H1] } pour ATR.
    R6 : données vides → aucune alerte (pas de crash).
    """
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    tick = MonitorTickResult(timestamp=ts)
    alerts: List[LiveAlert] = []
    if not pairs_bars:
        tick.notes["r6_skip"] = "no pairs_bars provided"
        return tick, alerts

    sess = _session_filter_safe(ts)
    session_name = sess.session if sess else "UNKNOWN"

    for pair, tfs in pairs_bars.items():
        tick.n_pairs_checked += 1
        symbol = pair  # mono-symbole
        sig = _signal_engine_safe(
            symbol, pair, ts, cfg["polling_timeframe_default"],
            pairs_bars=pairs_bars,
        )
        if sig is None:
            continue
        tick.n_signals_total += 1
        # Filtre : leverage < seuil ou fatman_signal < MOYEN
        sig_level = sig.fatman_signal
        thresh = cfg["alert_min_signal_fatman"]
        thresh_order = {"AUCUN": 0, "MOYEN": 1, "FORT": 2}
        if (sig.leverage < cfg["alert_min_leverage"]
                or thresh_order.get(sig_level, -1) < thresh_order.get(thresh, 1)):
            continue
        # Alerte qualifiée
        # S23-B: Use vol forecast for SL/TP (combined with ATR)
        atr_pips = 0.0
        sl_pips = 0.0
        tp_pips = 0.0
        
        if cfg.get("use_vol_forecast", True):
            # Use vol forecast + ATR combined
            try:
                from .v10_vol_forecast import forecast_vol, sl_tp_combined_atr_vol
                # Get ATR from H1 bars if available
                atr_val = 0.0
                if pairs_h1_bars and pair in pairs_h1_bars:
                    atr_result = _atr_safe(pair, pairs_h1_bars[pair])
                    if atr_result and atr_result.atr_pips > 0:
                        atr_val = atr_result.atr_pips
                
                # Get vol forecast
                closes = pairs_bars[pair].get(cfg["polling_timeframe_default"], [])
                if len(closes) >= 10:
                    vol = forecast_vol(closes, symbol=pair, method=cfg.get("vol_forecast_method", "auto"))
                    combined = sl_tp_combined_atr_vol(
                        atr_pips=atr_val,
                        vol_forecast=vol,
                        rr=2.0,
                        atr_weight=0.5,
                        vol_weight=0.5,
                    )
                    if combined.get("valid"):
                        sl_pips = combined["sl_pips"]
                        tp_pips = combined["tp_pips"]
            except Exception:
                # R6 fail-open: fallback to ATR only
                if pairs_h1_bars and pair in pairs_h1_bars:
                    atr = _atr_safe(pair, pairs_h1_bars[pair])
                    if atr:
                        atr_pips = atr.atr_pips
                        sl_pips = atr.sl_pips
                        tp_pips = atr.tp_pips
        else:
            # Legacy ATR only
            if pairs_h1_bars and pair in pairs_h1_bars:
                atr = _atr_safe(pair, pairs_h1_bars[pair])
                if atr:
                    atr_pips = atr.atr_pips
                    sl_pips = atr.sl_pips
                    tp_pips = atr.tp_pips

        # Create LiveAlert with computed SL/TP
        alert = LiveAlert(
            timestamp=ts, pair=pair, direction=sig.direction,
            leverage=sig.leverage, score_composite=sig.score_composite,
            fatman_signal=sig.fatman_signal, fatman_delta=sig.fatman_delta,
            atr_pips=atr_pips,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            session=session_name,
            severity=("ALERT" if sig.leverage >= 50 else "WARN"),
            message=(f"{pair} {sig.direction} leverage {sig.leverage} "
                     f"WR target {sig.score_composite:.0f}/100 "
                     f"fatman={sig.fatman_signal} session={session_name} "
                     f"SL={sl_pips:.1f}p TP={tp_pips:.1f}p"),
        )
        alerts.append(alert)
        tick.signals.append(alert.as_dict())
        tick.alerted_pairs.append(pair)
        tick.n_signals_emitted += 1
        if len(alerts) >= cfg["max_signals_per_poll"]:
            break
    return tick, alerts
def run_loop(
    pairs_bars_provider,
    *,
    interval_seconds: int = 60,
    max_ticks: int = 0,
    config: Optional[Dict] = None,
    on_alert=None,
) -> List[MonitorTickResult]:
    """Boucle polling. pairs_bars_provider est un callable() -> dict.

    max_ticks=0 → infini, sinon s'arrête après max_ticks polls.
    on_alert(alert) : callback appelé pour chaque alerte.
    """
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    results: List[MonitorTickResult] = []
    n = 0
    while max_ticks == 0 or n < max_ticks:
        n += 1
        try:
            pairs_bars = pairs_bars_provider()
        except Exception:
            pairs_bars = {}
        ts = datetime.now(timezone.utc).isoformat()
        tick, alerts = monitor_tick(pairs_bars, timestamp=ts,
                                     config=cfg)
        results.append(tick)
        for a in alerts:
            if on_alert is not None:
                try:
                    on_alert(a)
                except Exception:
                    pass
        if not alerts:
            emit_summary = cfg.get("enable_summary_log", True)
        if max_ticks != 0:
            continue
        time.sleep(interval_seconds)
    return results


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────



# ══════════════════════════════════════════════════════════════════════
#  API C20 additif (classes réécrites CYCLE 18-19, conservées pour compat)
# ══════════════════════════════════════════════════════════════════════

class PositionStatus:
    pos_id: str
    pair: str
    direction: str
    lot: float
    entry_price: float
    current_price: float
    floating_pnl: float
    pips: float
    r_multiple: float
    sl: Optional[float]
    tp: Optional[float]

    def as_dict(self) -> dict:
        return {
            "id": self.pos_id,
            "pair": self.pair,
            "direction": self.direction,
            "lot": self.lot,
            "entry": round(self.entry_price, 5),
            "current": round(self.current_price, 5),
            "pnl": round(self.floating_pnl, 2),
            "pips": round(self.pips, 1),
            "r": round(self.r_multiple, 2),
            "sl": self.sl,
            "tp": self.tp,
        }


class LiveMonitor:
    """
    Suit les positions ouvertes et calcule le PnL flottant en temps réel.
    """
    PIP = 0.0001
    PIP_VALUE = 10.0   # USD par pip par lot standard

    def __init__(self) -> None:
        self._positions: Dict[str, dict] = {}
        self._alerts: List[str] = []

    def register_position(self, pos_id: str, pair: str, direction: str,
                          lot: float, entry: float,
                          sl: Optional[float] = None,
                          tp: Optional[float] = None) -> None:
        self._positions[pos_id] = {
            "pair": pair, "direction": direction, "lot": lot,
            "entry": entry, "sl": sl, "tp": tp,
        }

    def update(self, pos_id: str, current_price: float) -> Optional[PositionStatus]:
        pos = self._positions.get(pos_id)
        if not pos:
            return None
        sign = 1 if pos["direction"] == "BUY" else -1
        pips = sign * (current_price - pos["entry"]) / self.PIP
        pnl = pips * self.PIP_VALUE * pos["lot"]
        sl_dist = abs(pos["entry"] - pos["sl"]) / self.PIP if pos["sl"] else 1.0
        r = pips / sl_dist if sl_dist > 0 else 0.0

        # Alertes SL/TP proches
        if pos["sl"] and abs(current_price - pos["sl"]) / self.PIP < 5:
            self._alerts.append(f"SL_NEAR {pos_id} ({pos['pair']}) — 5 pips")
        if pos["tp"] and abs(current_price - pos["tp"]) / self.PIP < 5:
            self._alerts.append(f"TP_NEAR {pos_id} ({pos['pair']}) — 5 pips")

        return PositionStatus(
            pos_id=pos_id, pair=pos["pair"], direction=pos["direction"],
            lot=pos["lot"], entry_price=pos["entry"], current_price=current_price,
            floating_pnl=pnl, pips=pips, r_multiple=r,
            sl=pos["sl"], tp=pos["tp"],
        )

    def close_position(self, pos_id: str) -> None:
        self._positions.pop(pos_id, None)

    def total_floating_pnl(self, prices: Dict[str, float]) -> float:
        total = 0.0
        for pid, pos in self._positions.items():
            price = prices.get(pos["pair"], pos["entry"])
            sign = 1 if pos["direction"] == "BUY" else -1
            pips = sign * (price - pos["entry"]) / self.PIP
            total += pips * self.PIP_VALUE * pos["lot"]
        return total

    def alerts(self) -> List[str]:
        return list(self._alerts)

    def reset(self) -> None:
        self._positions.clear()
        self._alerts.clear()

__all__ = [
    "DEFAULT_CONFIG",
    "MonitorTickResult",
    "LiveAlert",
    "emit_alerts",
    "monitor_tick",
    "run_loop",
]
