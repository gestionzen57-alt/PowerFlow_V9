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


def _atr_safe(pair, bars_h1, **kwargs):
    try:
        from .v10_atr_manager import compute_sl_tp
        return compute_sl_tp(pair, bars_h1, **kwargs)
    except Exception:
        return None


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
        atr = None
        if pairs_h1_bars and pair in pairs_h1_bars:
            atr = _atr_safe(pair, pairs_h1_bars[pair])
        alert = LiveAlert(
            timestamp=ts, pair=pair, direction=sig.direction,
            leverage=sig.leverage, score_composite=sig.score_composite,
            fatman_signal=sig.fatman_signal, fatman_delta=sig.fatman_delta,
            atr_pips=atr.atr_pips if atr else 0.0,
            sl_pips=atr.sl_pips if atr else 0.0,
            tp_pips=atr.tp_pips if atr else 0.0,
            session=session_name,
            severity=("ALERT" if sig.leverage >= 50 else "WARN"),
            message=(f"{pair} {sig.direction} leverage {sig.leverage} "
                     f"WR target {sig.score_composite:.0f}/100 "
                     f"fatman={sig.fatman_signal} session={session_name}"),
        )
        alerts.append(alert)
        tick.signals.append(alert.as_dict())
        tick.alerted_pairs.append(pair)
        tick.n_signals_emitted += 1
        if len(alerts) >= cfg["max_signals_per_poll"]:
            break
    return tick, alerts


# ─────────────────────────────────────────────────────────────────────
# Boucle polling (stub + driver)
# ─────────────────────────────────────────────────────────────────────
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
__all__ = [
    "DEFAULT_CONFIG",
    "MonitorTickResult",
    "LiveAlert",
    "emit_alerts",
    "monitor_tick",
    "run_loop",
]
