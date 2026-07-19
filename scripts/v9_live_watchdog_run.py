"""v9_live_watchdog_run.py — Runner CLI du watchdog live (Axe 6, pré-réouverture 2026-07-19).

Transforme le module `core/v9/v9_live_watchdog.py` en filet de sécurité
**opérationnel** : appelable par un cron (`V9_LiveWatchdogLoop`, toutes les 5 min),
avec journal structuré, alerte Telegram optionnelle et application optionnelle
(et blacklistée) des recommandations.

Usage :
    python scripts/v9_live_watchdog_run.py [--db-path PATH] [--json]
        [--exit-code] [--alert-telegram] [--apply-recommendations]
        [--log-file PATH] [--once]

Codes de sortie (si --exit-code, sinon 0) :
    0 = ok / no_data     1 = warn     2 = critical     3 = db_error     4 = disabled

Doctrine :
- R6  : défensif. Aucune exception ne remonte non gérée (le cron ne doit jamais
        échouer bruyamment). Un échec de télémétrie = db_error (alerte), pas un crash.
- R18 : code pur (sqlite3 + math dans le module). Telegram = effet de bord optionnel.
- R30 : par défaut le watchdog **recommande** ; seul `--apply-recommendations`
        (geste opérateur) mute le `.env`, et JAMAIS `V9_GBPUSD_LONG_ONLY=0` (blacklist).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.v9_live_watchdog import WatchdogDecision, check_health  # noqa: E402

DEFAULT_DB_PATH = ROOT / "data" / "v9_forces.db"
DEFAULT_LOG_FILE = ROOT / "logs" / "v9_live_watchdog.log"
DEFAULT_ENV_PATH = ROOT / "config" / "v9_kill_switches.env"

# Actions JAMAIS appliquées automatiquement : désactiver le long-only reviendrait
# à ré-autoriser les shorts (le contraire d'un arrêt). Cf. audit edgefund 07-19.
APPLY_BLACKLIST = ("V9_GBPUSD_LONG_ONLY=0",)

# status → code de sortie
_EXIT_CODES = {
    "ok": 0,
    "no_data": 0,
    "warn": 1,
    "critical": 2,
    "db_error": 3,
    "disabled": 4,
}


def status_to_exit_code(status: str) -> int:
    """Mappe un statut watchdog vers un code de sortie process."""
    return _EXIT_CODES.get(status, 0)


def build_report(decision: WatchdogDecision) -> dict:
    """Construit le rapport structuré (JSON-serializable) d'un verdict."""
    report = decision.to_dict()
    report["timestamp"] = datetime.now(timezone.utc).isoformat()
    return report


def append_log(report: dict, log_file: Path) -> None:
    """Ajoute une ligne JSON (JSONL) au journal. Défensif (R6)."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — le log ne doit jamais casser le run
        print(f"[WARN] impossible d'écrire le log {log_file}: {e}", file=sys.stderr)


def send_telegram_alert(text: str) -> bool:
    """Envoie une alerte Telegram (best-effort, jamais bloquant).

    Import paresseux + try/except : en CLI le serveur MCP Telegram n'est pas
    forcément disponible. Retourne True si l'envoi a (probablement) réussi.
    Monkeypatchable dans les tests.
    """
    try:
        from core.v9.telegram_notifier import send_message  # type: ignore
        send_message(text)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[INFO] alerte Telegram non envoyée ({e})", file=sys.stderr)
        return False


def apply_recommendations(
    actions: list[str] | tuple[str, ...],
    env_path: Path,
) -> list[str]:
    """Applique (append) les recommandations au `.env`, avec backup horodaté.

    - Blacklist : `V9_GBPUSD_LONG_ONLY=0` n'est JAMAIS écrit (safety).
    - Backup : `config/v9_kill_switches.env.bak.<timestamp>` avant modification.
    Retourne la liste des actions effectivement écrites.
    """
    to_apply = [a for a in actions if a not in APPLY_BLACKLIST]
    if not to_apply:
        return []
    if not env_path.exists():
        print(f"[WARN] {env_path} absent — recommandations non appliquées", file=sys.stderr)
        return []

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = env_path.with_name(env_path.name + f".bak.{ts}")
    try:
        backup.write_text(env_path.read_text(encoding="utf-8"), encoding="utf-8")
        with env_path.open("a", encoding="utf-8") as f:
            f.write(f"\n# === Watchdog auto-apply {ts} UTC ===\n")
            for a in to_apply:
                f.write(a + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] échec application recommandations: {e}", file=sys.stderr)
        return []
    return to_apply


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Runner watchdog live V9 (Axe 6).")
    p.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                   help="Chemin de v9_forces.db (défaut: data/v9_forces.db)")
    p.add_argument("--json", action="store_true",
                   help="Sortie JSON structurée sur stdout")
    p.add_argument("--exit-code", action="store_true",
                   help="Code de sortie mappé sur le statut (0-4). Sinon 0.")
    p.add_argument("--alert-telegram", action="store_true",
                   help="Envoie une alerte Telegram si alert_level != none")
    p.add_argument("--apply-recommendations", action="store_true",
                   help="Applique (append + backup) les recos au .env (hors blacklist)")
    p.add_argument("--log-file", default=str(DEFAULT_LOG_FILE),
                   help="Journal JSONL (défaut: logs/v9_live_watchdog.log)")
    p.add_argument("--env-file", default=str(DEFAULT_ENV_PATH),
                   help="Chemin du .env pour --apply-recommendations")
    p.add_argument("--once", action="store_true",
                   help="Exécute une seule passe (comportement par défaut ; smoke test)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    decision = check_health(Path(args.db_path))
    report = build_report(decision)

    append_log(report, Path(args.log_file))

    if args.alert_telegram and decision.alert_level != "none":
        level = decision.alert_level.upper()
        text = (
            f"[V9 WATCHDOG {level}] status={decision.status} "
            f"wr_gbpusd_long={decision.wr_long_only_gbpusd} "
            f"net_pnl_24h={decision.net_pnl_24h_pips}pips "
            f"triggered={list(decision.triggered)} "
            f"reco={list(decision.recommended_actions)}"
        )
        send_telegram_alert(text)

    if args.apply_recommendations and decision.recommended_actions:
        applied = apply_recommendations(decision.recommended_actions, Path(args.env_file))
        report["applied_actions"] = applied

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"watchdog: status={decision.status} "
            f"alert={decision.alert_level} "
            f"wr_gbpusd_long={decision.wr_long_only_gbpusd} "
            f"net_pnl_24h={decision.net_pnl_24h_pips}pips "
            f"n={decision.n_recent}"
        )

    return status_to_exit_code(decision.status)


if __name__ == "__main__":
    _args = _build_parser().parse_args()
    _code = main(sys.argv[1:])
    sys.exit(_code if _args.exit_code else 0)
