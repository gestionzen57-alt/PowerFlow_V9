"""v9_edge_decay_monitor_run.py — Runner CLI du EdgeDecayMonitor (Phase E, 2026-07-28).

Transforme le module `core/v9/edge_decay_monitor.py` en filet de sécurité
opérationnel : appelable par le cron `V9_EdgeDecayMonitor` (daily 06:00 UTC),
avec journal JSONL, sortie JSON structurée et alerte Telegram optionnelle.

Usage :
    python scripts/v9_edge_decay_monitor_run.py [--db-path PATH] [--json]
        [--exit-code] [--alert-telegram] [--log-file PATH] [--once]
        [--principle ID] [--dry-run]

Codes de sortie (si --exit-code, sinon 0) :
    0 = no_alert      1 = warnings_only     2 = critical_present
    3 = disabled      4 = db_error

Doctrine :
- R2  : additif. Aucune modif core/v9/* (le module edge_decay_monitor est
        déjà livré dormant par 74c2d79).
- R6  : défensif. Toute exception = exit 4 db_error (alerte), pas un crash.
        Le cron ne doit jamais échouer bruyamment.
- R18 : code pur (sqlite3 + math). Telegram = effet de bord optionnel best-effort.
- R25' : le runner ne mute AUCUN kill switch — `apply_actions` est volontairement
        absent. Seules les alertes sont émises ; les décisions d'auto-blacklist /
        démotion / observation sont déjà codées en interne dans
        `EdgeDecayMonitor` (champ `action` de chaque Alert), à valider par CEO.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.edge_decay_monitor import (  # noqa: E402
    Alert,
    edge_decay_monitor_enabled,
    run_edge_decay_check,
)

EDGE_DECAY_MONITOR_VERSION = "1.0"  # aligné sur le pattern des autres modules V9

DEFAULT_DB_PATH = ROOT / "data" / "v9_forces.db"
DEFAULT_LOG_FILE = ROOT / "logs" / "v9_edge_decay_monitor.log"


def append_log(report: dict, log_file: Path) -> None:
    """Append une ligne JSONL au log (best-effort, jamais bloquant)."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] impossible d'écrire le log {log_file}: {e}", file=sys.stderr)


def send_telegram_alert(alerts: list[Alert]) -> bool:
    """Envoie une alerte Telegram (best-effort, jamais bloquant).

    Import paresseux + try/except : en CLI le notifier Telegram peut être
    indisponible (pas de token, MCP down). Retourne True si envoi OK.
    """
    if not alerts:
        return False
    critical = [a for a in alerts if a.level == "CRITICAL"]
    warnings = [a for a in alerts if a.level == "WARNING"]
    level = "🔴 CRITICAL" if critical else "🟡 WARNING"
    header = f"[V9 EDGE_DECAY {level}] {len(critical)} critical, {len(warnings)} warning"
    lines = [header, ""]
    for a in critical + warnings:
        lines.append(
            f"  {a.level} {a.principle_id} | {a.session or '?'} | {a.regime_type or '?'}"
        )
        lines.append(f"    {a.message}")
        lines.append(f"    Action: {a.action}")
    text = "\n".join(lines)
    try:
        from core.v9.telegram_notifier import send_message  # type: ignore
        send_message(text)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[INFO] alerte Telegram non envoyée ({e})", file=sys.stderr)
        return False


def build_report(alerts: list[Alert], enabled: bool, db_path: Path) -> dict:
    """Construit le rapport structuré (sérialisable JSON)."""
    critical = [a for a in alerts if a.level == "CRITICAL"]
    warnings = [a for a in alerts if a.level == "WARNING"]
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "version": EDGE_DECAY_MONITOR_VERSION,
        "kill_switch": "V9_EDGE_DECAY_MONITOR_ENABLED",
        "enabled": enabled,
        "db_path": str(db_path),
        "n_alerts": len(alerts),
        "n_critical": len(critical),
        "n_warnings": len(warnings),
        "alerts": [a.to_dict() for a in alerts],
    }


def alerts_to_exit_code(alerts: list[Alert], enabled: bool, db_error: bool) -> int:
    """Mappe le résultat sur un code de sortie (utile pour cron monitoring)."""
    if db_error:
        return 4
    if not enabled:
        return 3
    if any(a.level == "CRITICAL" for a in alerts):
        return 2
    if alerts:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Runner EdgeDecayMonitor V9 (Phase E).")
    p.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                   help="Chemin de v9_forces.db (défaut: data/v9_forces.db)")
    p.add_argument("--json", action="store_true",
                   help="Sortie JSON structurée sur stdout")
    p.add_argument("--exit-code", action="store_true",
                   help="Code de sortie mappé sur le statut (0-4). Sinon 0.")
    p.add_argument("--alert-telegram", action="store_true",
                   help="Envoie une alerte Telegram si alertes présentes")
    p.add_argument("--log-file", default=str(DEFAULT_LOG_FILE),
                   help="Journal JSONL (défaut: logs/v9_edge_decay_monitor.log)")
    p.add_argument("--once", action="store_true",
                   help="Exécute une seule passe (défaut)")
    p.add_argument("--principle", type=str, default=None,
                   help="Check un seul principe (mode debug)")
    p.add_argument("--dry-run", action="store_true",
                   help="Affiche ce qui serait fait sans rien logger/notifier")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    enabled = edge_decay_monitor_enabled()
    db_path = Path(args.db_path)

    # Cas disabled : on log et on sort
    if not enabled:
        report = build_report([], enabled=False, db_path=db_path)
        if not args.dry_run:
            append_log(report, Path(args.log_file))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"edge_decay: status=disabled kill_switch=V9_EDGE_DECAY_MONITOR_ENABLED")
        return 3 if args.exit_code else 0

    # Check
    db_error = False
    alerts: list[Alert] = []
    try:
        alerts = run_edge_decay_check(db_path)
    except Exception as e:  # noqa: BLE001
        db_error = True
        print(f"[ERROR] edge_decay_check failed: {e}", file=sys.stderr)
        if not args.dry_run:
            traceback.print_exc(file=sys.stderr)

    report = build_report(alerts, enabled=True, db_path=db_path)
    report["db_error"] = db_error

    if not args.dry_run:
        append_log(report, Path(args.log_file))
        if args.alert_telegram and alerts:
            telegram_ok = send_telegram_alert(alerts)
            report["telegram_sent"] = telegram_ok

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "db_error" if db_error else ("alerts" if alerts else "ok")
        print(
            f"edge_decay: status={status} n_alerts={len(alerts)} "
            f"critical={report['n_critical']} warnings={report['n_warnings']}"
        )

    return alerts_to_exit_code(alerts, enabled, db_error) if args.exit_code else 0


if __name__ == "__main__":
    sys.exit(main())
