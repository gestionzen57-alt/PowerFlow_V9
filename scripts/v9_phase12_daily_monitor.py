#!/usr/bin/env python3
"""
v9_phase12_daily_monitor.py — Surveillance quotidienne Phase 12 FTMO Challenge
==============================================================================

Script de monitoring complet pour le défi FTMO 10k EUR :
- Walk-forward L7/L8 quotidiens
- Validation FTMO (risque/trade, DD journalier, DD total)
- Rapport de santé système
- Alerte Telegram si dérive détectée

Usage:
    python scripts/v9_phase12_daily_monitor.py --once [--alert-telegram] [--json]
    python scripts/v9_phase12_daily_monitor.py --watch
"""

import argparse
import json
import logging
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ajouter le répertoire du projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9.kill_switches import get as ks_get

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("v9.phase12_monitor")

PHASE12_MONITOR_STATE = Path("data/v9_phase12_monitor_state.json")
FTMO_CAPITAL_EUR = 10000.0
FTMO_MAX_RISK_PER_TRADE_PCT = 0.01   # 1%
FTMO_MAX_DAILY_DD_PCT = 0.05         # 5%
FTMO_MAX_TOTAL_DD_PCT = 0.10         # 10%
PIP_VALUE_EUR_PER_LOT = 10.0         # 1 pip = 10 EUR pour 1 lot GBPUSD (approx)


def run_command(cmd: list[str], cwd: Path = None, timeout: int = 60) -> dict[str, Any]:
    """Exécute une commande et retourne le résultat structuré."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd or Path.cwd(),
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "rc": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout", "success": False}
    except Exception as e:
        return {"rc": -2, "stdout": "", "stderr": str(e), "success": False}


def load_state() -> dict[str, Any]:
    """Charge l'état du monitor."""
    if PHASE12_MONITOR_STATE.exists():
        try:
            return json.loads(PHASE12_MONITOR_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_run": None,
        "last_l7_report": None,
        "last_l8_report": None,
        "consecutive_failures": 0,
        "total_runs": 0
    }


def save_state(state: dict[str, Any]) -> None:
    """Sauvegarde l'état du monitor."""
    PHASE12_MONITOR_STATE.parent.mkdir(parents=True, exist_ok=True)
    PHASE12_MONITOR_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_walk_forward(script: str, days: int = 30) -> dict[str, Any]:
    """Exécute un script de walk-forward et parse le résultat JSON."""
    cmd = [
        sys.executable, f"scripts/{script}.py",
        "--days", str(days),
        "--dry-run"  # lecture seule
    ]
    result = run_command(cmd, timeout=120)
    
    if not result["success"]:
        return {"error": result["stderr"], "rc": result["rc"]}
    
    # Chercher le JSON dans la sortie
    try:
        output = result["stdout"]
        for line in reversed(output.strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
        return {"error": "No JSON found in output", "raw": output}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": result["stdout"]}


def check_ftmo_compliance() -> dict[str, Any]:
    """Vérifie la conformité FTMO avec le validateur existant."""
    cmd = [sys.executable, "scripts/v9_ftmo_sizing_validator.py"]
    result = run_command(cmd, timeout=60)
    
    if not result["success"]:
        return {"error": result["stderr"], "rc": result["rc"]}
    
    try:
        output = result["stdout"]
        for line in reversed(output.strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
        return {"error": "No JSON found", "raw": output}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": output}


def get_system_health() -> dict[str, Any]:
    """Récupère l'état de santé système via health_one_liner."""
    cmd = [sys.executable, "scripts/v9_health_one_liner.py", "--json"]
    result = run_command(cmd, timeout=30)
    
    if not result["success"]:
        return {"error": result["stderr"]}
    
    try:
        output = result["stdout"]
        for line in reversed(output.strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
        return {"error": "No JSON found", "raw": output}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": output}


def check_kill_switches() -> dict[str, bool]:
    """Vérifie l'état des kill switches critiques Phase 12."""
    critical_switches = {
        "V9_EXECUTION_ENABLED": ks_get("V9_EXECUTION_ENABLED", "0") == "1",
        "V9_DYNAMIC_RISK_ENABLED": ks_get("V9_DYNAMIC_RISK_ENABLED", "0") == "1",
        "V9_DRAWDOWN_PROTECTOR_ENABLED": ks_get("V9_DRAWDOWN_PROTECTOR_ENABLED", "0") == "1",
        "V9_RISK_PARITY_ENABLED": ks_get("V9_RISK_PARITY_ENABLED", "0") == "1",
        "V9_KELLY_FRACTIONAL_ENABLED": ks_get("V9_KELLY_FRACTIONAL_ENABLED", "0") == "1",
        "V9_LOOP_BREAKER_ENABLED": ks_get("V9_LOOP_BREAKER_ENABLED", "0") == "1",
        "V9_ANTI_SERIE_PERDANTE_ENABLED": ks_get("V9_ANTI_SERIE_PERDANTE_ENABLED", "0") == "1",
        "V9_KILL_DD_WR_ENABLED": ks_get("V9_KILL_DD_WR_ENABLED", "0") == "1",
        "V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED": ks_get("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "0") == "1",
        "V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED": ks_get("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED", "0") == "1",
    }
    return critical_switches


def evaluate_drift(l7_report: dict, l8_report: dict, ftmo_report: dict) -> tuple[str, list[str]]:
    """Évalue si une dérive est détectée."""
    alerts = []
    status = "OK"
    
    # Vérifier L7
    if "verdict" in l7_report:
        if l7_report["verdict"] in ("HOLD", "QUASI_PROMOTE"):
            alerts.append(f"L7: {l7_report['verdict']} - edge preserve mais sous seuil PROMOTE")
    
    # Vérifier L8
    if "verdict" in l8_report:
        if l8_report["verdict"] != "PROMOTE":
            alerts.append(f"L8: {l8_report['verdict']} - perte de l'edge transformatif")
            status = "DRIFT"
        elif l8_report.get("pnl_gain_pips", 0) < 500:
            alerts.append(f"L8: gain réduit ({l8_report.get('pnl_gain_pips', 0):.1f}p < 500p)")
            if status == "OK":
                status = "WARNING"
    
    # Vérifier FTMO
    if "verdict" in ftmo_report:
        if ftmo_report["verdict"] != "GO":
            alerts.append(f"FTMO: {ftmo_report['verdict']} - NON CONFORME")
            status = "DRIFT"
    
    # Vérifier kill switches
    switches = check_kill_switches()
    for name, value in switches.items():
        if not value and "ENABLED" in name:
            alerts.append(f"Kill switch OFF: {name}")
            status = "DRIFT"
    
    if not alerts:
        alerts.append("Tous indicateurs normaux")
    
    return status, alerts


def send_telegram_alert(message: str) -> bool:
    """Envoie une alerte Telegram via le notificateur existant."""
    try:
        cmd = [sys.executable, "scripts/v9_telegram_notifier.py", "--send-text", message]
        result = run_command(cmd, timeout=30)
        return result["success"]
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
        return False


def run_monitor(alert_telegram: bool = False, output_json: bool = False) -> dict[str, Any]:
    """Exécute le monitoring complet Phase 12."""
    state = load_state()
    state["total_runs"] += 1
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_number": state["total_runs"],
        "l7_walk_forward": None,
        "l8_walk_forward": None,
        "ftmo_compliance": None,
        "system_health": None,
        "kill_switches": None,
        "drift_status": "UNKNOWN",
        "alerts": []
    }
    
    logger.info("=== Phase 12 Daily Monitor Start ===")
    
    # 1. Walk-forward L7
    logger.info("Running L7 walk-forward...")
    l7_report = run_walk_forward("v9_l7_promotion_walkforward", days=30)
    report["l7_walk_forward"] = l7_report
    if "verdict" in l7_report:
        logger.info(f"L7 verdict: {l7_report['verdict']} (gain: {l7_report.get('pnl_gain_pips', 'N/A')} pips)")
        state["last_l7_report"] = l7_report
    
    # 2. Walk-forward L8
    logger.info("Running L8 walk-forward...")
    l8_report = run_walk_forward("v9_l8_promotion_walkforward", days=30)
    report["l8_walk_forward"] = l8_report
    if "verdict" in l8_report:
        logger.info(f"L8 verdict: {l8_report['verdict']} (gain: {l8_report.get('pnl_gain_pips', 'N/A')} pips)")
        state["last_l8_report"] = l8_report
    
    # 3. FTMO Compliance
    logger.info("Checking FTMO compliance...")
    ftmo_report = check_ftmo_compliance()
    report["ftmo_compliance"] = ftmo_report
    if "verdict" in ftmo_report:
        logger.info(f"FTMO verdict: {ftmo_report['verdict']}")
    
    # 4. System Health
    logger.info("Checking system health...")
    health = get_system_health()
    report["system_health"] = health
    
    # 5. Kill Switches
    logger.info("Checking kill switches...")
    switches = check_kill_switches()
    report["kill_switches"] = switches
    off_switches = [k for k, v in switches.items() if not v]
    if off_switches:
        logger.warning(f"Kill switches OFF: {off_switches}")
    
    # 6. Drift Evaluation
    drift_status, alerts = evaluate_drift(l7_report, l8_report, ftmo_report)
    report["drift_status"] = drift_status
    report["alerts"] = alerts
    
    for alert in alerts:
        logger.info(f"  - {alert}")
    
    if drift_status in ("DRIFT", "WARNING"):
        state["consecutive_failures"] += 1
    else:
        state["consecutive_failures"] = 0
    
    # 7. Telegram Alert si requis
    if alert_telegram and drift_status in ("DRIFT", "WARNING"):
        msg = f"🚨 Phase 12 ALERT [{drift_status}]\n"
        msg += f"Time: {report['timestamp']}\n"
        msg += f"L7: {l7_report.get('verdict', 'N/A')} ({l7_report.get('pnl_gain_pips', 'N/A')} pips)\n"
        msg += f"L8: {l8_report.get('verdict', 'N/A')} ({l8_report.get('pnl_gain_pips', 'N/A')} pips)\n"
        msg += f"FTMO: {ftmo_report.get('verdict', 'N/A')}\n"
        msg += f"Alertes: {'; '.join(alerts[:3])}"
        send_telegram_alert(msg)
    
    # Sauvegarder état
    state["last_run"] = report["timestamp"]
    save_state(state)
    
    logger.info(f"=== Phase 12 Daily Monitor End - Status: {drift_status} ===")
    
    if output_json:
        print(json.dumps(report, indent=2))
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Phase 12 FTMO Daily Monitor")
    parser.add_argument("--once", action="store_true", help="Exécuter une fois et quitter")
    parser.add_argument("--watch", action="store_true", help="Mode surveillance continue (toutes les 4h)")
    parser.add_argument("--alert-telegram", action="store_true", help="Envoyer alerte Telegram si dérive")
    parser.add_argument("--json", action="store_true", help="Sortie JSON structurée")
    parser.add_argument("--interval", type=int, default=240, help="Intervalle en minutes (défaut 240 = 4h)")
    
    args = parser.parse_args()
    
    if not args.once and not args.watch:
        parser.error("Must specify --once or --watch")
    
    if args.once:
        run_monitor(alert_telegram=args.alert_telegram, output_json=args.json)
    elif args.watch:
        logger.info(f"Starting watch mode (interval: {args.interval} min)")
        while True:
            try:
                run_monitor(alert_telegram=True, output_json=False)
            except KeyboardInterrupt:
                logger.info("Watch mode stopped by user")
                break
            except Exception as e:
                logger.error(f"Watch mode error: {e}")
            import time
            time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()