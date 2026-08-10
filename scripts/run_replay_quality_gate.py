"""
scripts/run_replay_quality_gate.py
Quality gate M15 ReplayEngine — H8
Lance un replay sur les N derniers jours, vérifie les métriques clés.
Si PASS → déclenche v10_rl_promotion | Si FAIL → alerte détaillée.
Config : config/quality_gate.json
"""
from __future__ import annotations
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v10.v10_replay_engine import ReplayEngine  # type: ignore
from core.v10.v10_rl_promotion import RLPromotion      # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("quality_gate")

DEFAULT_CONFIG: Dict[str, Any] = {
    "lookback_days": 30,
    "timeframe": "M15",
    "min_sharpe": 1.2,
    "max_drawdown_pct": 8.0,
    "min_winrate_pct": 52.0,
    "telegram_alert": False,
    "telegram_token": "",
    "telegram_chat_id": "",
}


def load_config(config_path: str = "config/quality_gate.json") -> Dict[str, Any]:
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            user_cfg = json.load(f)
        return {**DEFAULT_CONFIG, **user_cfg}
    log.warning("Config not found at %s — using defaults.", config_path)
    return DEFAULT_CONFIG.copy()


def send_telegram(token: str, chat_id: str, message: str) -> None:
    """Fire-and-forget Telegram alert (requires requests)."""
    try:
        import requests  # type: ignore
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=5)
    except Exception as exc:
        log.error("Telegram alert failed: %s", exc)


def run_gate(config_path: str = "config/quality_gate.json") -> bool:
    cfg = load_config(config_path)
    log.info("=== QUALITY GATE START | lookback=%dd | tf=%s ===",
             cfg["lookback_days"], cfg["timeframe"])

    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=cfg["lookback_days"])

    # ── Run replay ────────────────────────────────────────────────────────────
    engine = ReplayEngine(timeframe=cfg["timeframe"])
    metrics = engine.run(
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )

    sharpe    = float(metrics.get("sharpe", 0.0))
    max_dd    = float(metrics.get("max_drawdown_pct", 999.0))
    win_rate  = float(metrics.get("win_rate_pct", 0.0))

    # ── Evaluate thresholds ───────────────────────────────────────────────────
    checks = {
        "sharpe":    {"value": sharpe,   "threshold": cfg["min_sharpe"],        "op": ">=", "pass": sharpe   >= cfg["min_sharpe"]},
        "max_dd":    {"value": max_dd,   "threshold": cfg["max_drawdown_pct"],  "op": "<=", "pass": max_dd   <= cfg["max_drawdown_pct"]},
        "win_rate":  {"value": win_rate, "threshold": cfg["min_winrate_pct"],   "op": ">=", "pass": win_rate >= cfg["min_winrate_pct"]},
    }

    all_pass = all(c["pass"] for c in checks.values())
    gate_status = "GATE_PASS" if all_pass else "GATE_FAIL"

    # ── Log result ────────────────────────────────────────────────────────────
    log.info("%s", gate_status)
    for name, c in checks.items():
        icon = "✅" if c["pass"] else "❌"
        log.info("  %s %-10s: %.4f %s %.4f", icon, name, c["value"], c["op"], c["threshold"])

    if all_pass:
        log.info("Triggering RL promotion...")
        promoter = RLPromotion()
        promoter.promote(metrics=metrics)
        log.info("RL promotion complete.")
    else:
        fail_details = [
            f"{k}: got {v['value']:.4f}, need {v['op']} {v['threshold']:.4f}"
            for k, v in checks.items() if not v["pass"]
        ]
        detail_msg = " | ".join(fail_details)
        log.warning("GATE_FAIL details: %s", detail_msg)

        if cfg.get("telegram_alert") and cfg.get("telegram_token"):
            msg = f"🚨 PowerFlow Quality Gate FAIL\n{detail_msg}\n{datetime.utcnow().isoformat()}"
            send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)

    return all_pass


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config/quality_gate.json"
    success = run_gate(cfg_path)
    sys.exit(0 if success else 1)
