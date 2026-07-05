#!/usr/bin/env python3
"""deploy_v9.py — Déploiement et vérification du serveur de capture V9.

Script autonome (pas de daemon) : chaque invocation s'exécute et se termine,
à l'exception de `--start` qui reste au premier plan tant que le serveur de
capture tourne (Ctrl+C ou `--stop` depuis un autre terminal pour arrêter).

Couche cognitive : outillage de déploiement uniquement. Aucune logique de
trading, aucune décision, aucune interprétation des forces.

Usage :
    python scripts/deploy_v9.py --check
    python scripts/deploy_v9.py --start
    python scripts/deploy_v9.py --status
    python scripts/deploy_v9.py --stop
"""

from __future__ import annotations

import argparse
import importlib
import socket
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, LISTEN_HOST, LISTEN_PORT, LOG_PATH  # noqa: E402

PID_FILE = ROOT_DIR / "logs" / "v9_capture.pid"

CORE_MODULES = [
    "core.v9.config",
    "core.v9.market_calendar",
    "core.v9.stale_gate",
    "core.v9.forces_reader",
    "core.v9.db_schema",
    "core.v9.capture_server",
    "core.v9.scene_builder",
    "core.v9.scene_db",
    "core.v9.behavior_analyzer",
    "core.v9.behavior_db",
    "core.v9.window_gate",
    "core.v9.window_db",
    "core.v9.exploitability_evaluator",
    "core.v9.exploitability_db",
    "core.v9.orchestrator",
]

MIN_PYTHON = (3, 11)


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    mark = "OK " if passed else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")
    return passed


def check_python_version() -> bool:
    version = sys.version_info
    passed = (version.major, version.minor) >= MIN_PYTHON
    return _ok(
        "Python 3.11+",
        passed,
        f"detecte {version.major}.{version.minor}.{version.micro}",
    )


def check_modules_importable() -> bool:
    all_ok = True
    for mod_name in CORE_MODULES:
        try:
            importlib.import_module(mod_name)
        except Exception as exc:  # noqa: BLE001
            _ok(f"import {mod_name}", False, str(exc))
            all_ok = False
    if all_ok:
        _ok(f"Modules core/v9/ importables ({len(CORE_MODULES)})", True)
    return all_ok


def check_db() -> bool:
    from core.v9.db_schema import init_db
    from core.v9.scene_db import init_scene_db
    from core.v9.behavior_db import init_behavior_db
    from core.v9.window_db import init_window_db
    from core.v9.exploitability_db import init_exploitability_db

    existed_before = DB_PATH.exists()
    init_db()
    init_scene_db()
    init_behavior_db()
    init_window_db()
    init_exploitability_db()

    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    expected = {"forces_snapshots", "scenes", "behaviors", "windows", "exploitability"}
    missing = expected - tables
    passed = not missing
    detail = (
        f"{DB_PATH} ({'creee' if not existed_before else 'existante'})"
        if passed
        else f"tables manquantes: {sorted(missing)}"
    )
    return _ok("Base de donnees v9_forces.db + 5 tables", passed, detail)


def check_port_available(port: int = LISTEN_PORT) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((LISTEN_HOST, port))
        passed = True
        detail = f"{LISTEN_HOST}:{port} libre"
    except OSError as exc:
        passed = False
        detail = f"{LISTEN_HOST}:{port} indisponible ({exc})"
    finally:
        sock.close()
    return _ok("Port TCP disponible", passed, detail)


def check_sdi_connection(timeout_s: float = 3.0) -> bool:
    """Vérification souple (non bloquante) : tente d'accepter une connexion
    EA pendant `timeout_s` secondes. Si aucune connexion n'arrive (marché
    fermé, EA non lancé), ce n'est pas un échec de `--check` — seulement une
    information reportée à l'opérateur."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((LISTEN_HOST, LISTEN_PORT))
        sock.listen(1)
        sock.settimeout(timeout_s)
        try:
            conn, _addr = sock.accept()
            conn.close()
            print(f"[INFO] Connexion EA detectee sur {LISTEN_HOST}:{LISTEN_PORT} (SDI probablement charge).")
            return True
        except socket.timeout:
            print(
                f"[INFO] Aucune connexion EA recue en {timeout_s:.0f}s "
                f"(marche ferme ou EA non lance - non bloquant)."
            )
            return True
    except OSError as exc:
        print(f"[INFO] Verification SDI ignoree (port occupe : {exc}).")
        return True
    finally:
        sock.close()


def run_check() -> int:
    print("=" * 60)
    print("PowerFlow V9 - Verification de deploiement (--check)")
    print("=" * 60)
    results = [
        check_python_version(),
        check_modules_importable(),
        check_db(),
        check_port_available(),
    ]
    check_sdi_connection()
    print("-" * 60)
    if all(results):
        print("Toutes les verifications bloquantes sont passees.")
        return 0
    print("Au moins une verification bloquante a echoue.")
    return 1


def run_start() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        print(f"[WARN] {PID_FILE} existe deja - un serveur est peut-etre deja actif.")
        print("Utiliser --stop d'abord, ou supprimer le fichier PID s'il est perime.")

    print(f"Demarrage du serveur de capture V9 sur {LISTEN_HOST}:{LISTEN_PORT}...")
    print(f"Log : {LOG_PATH}")
    print("Ctrl+C pour arreter, ou 'python scripts/deploy_v9.py --stop' depuis un autre terminal.")

    proc = subprocess.Popen(
        [sys.executable, "-m", "core.v9.capture_server"],
        cwd=str(ROOT_DIR),
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nArret demande (Ctrl+C)...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        PID_FILE.unlink(missing_ok=True)
    return 0


def run_stop() -> int:
    if not PID_FILE.exists():
        print("Aucun serveur actif (fichier PID introuvable).")
        return 0

    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    try:
        pid = int(pid_text)
    except ValueError:
        print(f"Fichier PID invalide ({pid_text!r}) - suppression.")
        PID_FILE.unlink(missing_ok=True)
        return 1

    print(f"Arret du serveur (PID {pid})...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=True,
                capture_output=True,
            )
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
        print("Serveur arrete proprement.")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Impossible de confirmer l'arret du PID {pid} : {exc}")
    finally:
        PID_FILE.unlink(missing_ok=True)
    return 0


def run_status() -> int:
    import sqlite3

    print("=" * 60)
    print("PowerFlow V9 - Statut (--status)")
    print("=" * 60)

    server_active = PID_FILE.exists()
    print(f"Serveur (PID file)   : {'ACTIF' if server_active else 'inactif'}"
          + (f" (PID {PID_FILE.read_text().strip()})" if server_active else ""))

    if not DB_PATH.exists():
        print(f"DB introuvable : {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))

    def count(table: str, where: str = "") -> int:
        try:
            sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
            return conn.execute(sql).fetchone()[0]
        except sqlite3.OperationalError:
            return -1

    snapshots_total = count("forces_snapshots")
    stale_total = count("forces_snapshots", "stale = 1")
    scenes_total = count("scenes")
    behaviors_total = count("behaviors")
    windows_total = count("windows")
    exploitability_total = count("exploitability")

    print(f"Snapshots recus (par TF) :")
    if snapshots_total >= 0:
        rows = conn.execute(
            "SELECT timeframe, COUNT(*) FROM forces_snapshots GROUP BY timeframe ORDER BY timeframe"
        ).fetchall()
        for tf, n in rows:
            print(f"  {tf:>5} : {n}")
        print(f"  TOTAL : {snapshots_total}")
    else:
        print("  (table forces_snapshots absente)")

    stale_rate = (stale_total / snapshots_total * 100) if snapshots_total > 0 else 0.0
    print(f"Stale count           : {stale_total} ({stale_rate:.1f}%)")
    print(f"Scenes produites      : {scenes_total}")
    print(f"Comportements qualifies: {behaviors_total}")
    print(f"Fenetres ouvertes     : {windows_total}")
    print(f"Evaluations exploit.  : {exploitability_total}")

    last = conn.execute(
        "SELECT created_at, symbol, timeframe, stale FROM forces_snapshots "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last:
        created_at, symbol, timeframe, stale = last
        try:
            from datetime import datetime, timezone

            last_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - last_dt).total_seconds()
            age_str = f"{age_s:.0f}s"
        except Exception:  # noqa: BLE001
            age_str = "inconnu"
        print(
            f"Dernier snapshot      : {created_at} {symbol} tf={timeframe} "
            f"stale={bool(stale)} age={age_str}"
        )
    else:
        print("Dernier snapshot      : aucun")

    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploiement et verification V9")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verifier les prerequis de deploiement")
    group.add_argument("--start", action="store_true", help="Demarrer le serveur de capture")
    group.add_argument("--status", action="store_true", help="Afficher l'etat du systeme V9")
    group.add_argument("--stop", action="store_true", help="Arreter le serveur de capture")
    args = parser.parse_args()

    if args.check:
        return run_check()
    if args.start:
        return run_start()
    if args.status:
        return run_status()
    if args.stop:
        return run_stop()
    return 1


if __name__ == "__main__":
    sys.exit(main())
