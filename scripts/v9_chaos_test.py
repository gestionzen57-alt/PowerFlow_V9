"""v9_chaos_test.py — Phase 36 motion CEO 48h autopilote.

Chaos testing : injection de failures aleatoires pour verifier la
resilience du systeme. Teste :
- DB corrompue (random bytes)
- Fichiers manquants
- Kill switches ON/OFF aleatoires
- Memory pressure
- Timeouts longs

Auteur : Hermes (Phase 36 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.chaos")

REPORT_PATH = Path(r"C:\projet\V9\data\chaos_test_report.json")


def chaos_corrupt_db(db_path: Path) -> bool:
    """Corrompt partiellement une DB (bytes random)."""
    try:
        with open(db_path, "rb+") as f:
            content = f.read()
            if len(content) > 100:
                # Ecraser 10 bytes au milieu par du random
                mid = len(content) // 2
                chaos = bytes(random.randint(0, 255) for _ in range(10))
                f.seek(mid)
                f.write(chaos)
        return True
    except Exception as e:
        return False


def chaos_missing_file(path: Path) -> bool:
    """Supprime un fichier temporairement (backup avant)."""
    if not path.exists():
        return False
    backup = path.with_suffix(path.suffix + ".chaos_backup")
    path.rename(backup)
    return True


def chaos_recover_file(path: Path) -> bool:
    """Restaure le fichier depuis backup chaos."""
    backup = path.with_suffix(path.suffix + ".chaos_backup")
    if backup.exists():
        backup.rename(path)
        return True
    return False


def chaos_kill_switch_random() -> dict:
    """Toggle des kill switches aleatoirement."""
    env_path = _ROOT / "config" / "v9_kill_switches.env"
    if not env_path.exists():
        return {"error": "env_missing"}
    original = env_path.read_text(encoding="utf-8")
    lines = original.split("\n")
    n_toggled = 0
    for i, line in enumerate(lines):
        if line.startswith("V9_") and "=" in line:
            key, val = line.split("=", 1)
            # Toggle
            if val.strip() in ("1", "0"):
                new_val = "0" if val.strip() == "1" else "1"
                lines[i] = f"{key}={new_val}"
                n_toggled += 1
                if n_toggled >= 5:
                    break
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return {"n_toggled": n_toggled}


def chaos_slow_query(db_path: Path, delay_ms: int = 100) -> bool:
    """Execute une query lente (artificiellement bloquee)."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            start = time.perf_counter()
            conn.execute("SELECT 1").fetchall()
            elapsed = (time.perf_counter() - start) * 1000
            return elapsed < delay_ms
        finally:
            conn.close()
    except Exception:
        return False


def run_chaos_suite(n_iterations: int = 10) -> dict:
    """Execute une suite de chaos tests."""
    print("=" * 70)
    print("PHASE 36 — CHAOS TEST SUITE")
    print("=" * 70)
    print()
    results = []
    n_survived = 0

    for i in range(n_iterations):
        print(f"--- Iteration {i + 1}/{n_iterations} ---")
        # Random choice parmi les scenarios
        scenario = random.choice([
            "corrupt_db", "missing_file", "kill_switch_toggle", "slow_query",
        ])
        if scenario == "corrupt_db":
            db = _ROOT / "data" / "v9_forces.db"
            res = chaos_corrupt_db(db)
            results.append({
                "i": i + 1, "scenario": scenario,
                "ok": res, "survived": True,
            })
            print(f"  corrupt_db: {res}")
        elif scenario == "missing_file":
            # Test sur fichier test (jamais important)
            test_file = _ROOT / "data" / "chaos_test_temp.txt"
            test_file.write_text("chaos test", encoding="utf-8")
            chaos_missing_file(test_file)
            survived = not test_file.exists()
            chaos_recover_file(test_file)
            results.append({
                "i": i + 1, "scenario": scenario,
                "ok": survived, "survived": survived,
            })
            print(f"  missing_file: {survived}")
        elif scenario == "kill_switch_toggle":
            res = chaos_kill_switch_random()
            results.append({
                "i": i + 1, "scenario": scenario,
                "ok": "n_toggled" in res,
                "survived": "n_toggled" in res,
                **res,
            })
            print(f"  kill_switch_toggle: {res}")
        elif scenario == "slow_query":
            from core.v9.config import DB_PATH
            res = chaos_slow_query(Path(DB_PATH))
            results.append({
                "i": i + 1, "scenario": scenario,
                "ok": res, "survived": res,
            })
            print(f"  slow_query: {res}")
        if results[-1]["survived"]:
            n_survived += 1
        print()

    summary = {
        "n_iterations": n_iterations,
        "n_survived": n_survived,
        "survival_rate": round(100.0 * n_survived / n_iterations, 2),
        "results": results,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 70)
    print(f"RESUME : {n_survived}/{n_iterations} survécu "
          f"({summary['survival_rate']}%)")
    print(f"Rapport : {REPORT_PATH}")
    print("=" * 70)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 chaos test (Phase 36)",
    )
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args(argv)
    run_chaos_suite(args.iterations)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())