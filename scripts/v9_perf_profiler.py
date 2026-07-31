"""v9_perf_profiler.py — Phase 34 motion CEO 48h autopilote.

Profile la performance des modules V9 et identifie les goulets
d'etranglement. Genere un rapport avec :
- Temps d'execution par module
- Memory usage
- Queries SQL les plus lentes

Auteur : Hermes (Phase 34 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import logging
import pstats
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.perf")

REPORT_PATH = Path(r"C:\projet\V9\data\perf_report.json")


def time_function(fn, *args, **kwargs) -> tuple[float, any]:
    """Execute une fonction et mesure le temps."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed, result


def benchmark_query(db_path: Path | str, query: str,
                     label: str, n_runs: int = 10) -> dict:
    """Benchmark une requete SQL."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"label": label, "error": "db_missing"}
    times = []
    for _ in range(n_runs):
        start = time.perf_counter()
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(query).fetchall()
            finally:
                conn.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            return {"label": label, "error": str(e)}
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    times.sort()
    return {
        "label": label,
        "n_runs": n_runs,
        "min_ms": round(min(times) * 1000, 3),
        "median_ms": round(times[len(times) // 2] * 1000, 3),
        "max_ms": round(max(times) * 1000, 3),
        "total_ms": round(sum(times) * 1000, 3),
    }


def profile_module(module_name: str, fn_name: str, *args, **kwargs) -> dict:
    """Profile un module/fonction avec cProfile."""
    import importlib
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, fn_name)
    except (ImportError, AttributeError) as e:
        return {"module": module_name, "fn": fn_name, "error": str(e)}
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        result = fn(*args, **kwargs)
    finally:
        profiler.disable()
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(20)
    return {
        "module": module_name,
        "fn": fn_name,
        "stats": s.getvalue(),
        "result": str(result)[:200] if result else None,
    }


def run_benchmarks(db_path: Path | str) -> list[dict]:
    """Execute les benchmarks SQL standards."""
    queries = [
        ("paper_trades_count",
         "SELECT COUNT(*) FROM v9_paper_trades"),
        ("paper_trades_wins",
         "SELECT COUNT(*) FROM v9_paper_trades WHERE pips_net > 0"),
        ("paper_trades_30j",
         "SELECT * FROM v9_paper_trades "
         "WHERE closed_at > REPLACE(datetime('now', '-30 days'), ' ', 'T')"),
        ("decisions_count",
         "SELECT COUNT(*) FROM decisions"),
        ("principles_active",
         "SELECT * FROM principles WHERE status = 'ACTIVE'"),
    ]
    return [benchmark_query(db_path, q, label) for label, q in queries]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 performance profiler (Phase 34 48h)",
    )
    parser.add_argument("--module", default=None,
                        help="Module a profiler (ex: scripts.v9_monte_carlo)")
    parser.add_argument("--fn", default="monte_carlo_bootstrap",
                        help="Fonction a profiler (defaut monte_carlo_bootstrap)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    print("=" * 70)
    print("PHASE 34 — PERFORMANCE PROFILER")
    print("=" * 70)
    print()

    print("--- Benchmarks SQL ---")
    bench_results = run_benchmarks(DB_PATH)
    for r in bench_results:
        if "error" in r:
            print(f"  [{r['label']:30s}] ERROR : {r['error']}")
        else:
            print(f"  [{r['label']:30s}] median={r['median_ms']:.1f}ms  "
                  f"max={r['max_ms']:.1f}ms")
    print()

    if args.module:
        print(f"--- Profile {args.module}.{args.fn} ---")
        prof = profile_module(args.module, args.fn)
        if "error" in prof:
            print(f"  ERROR : {prof['error']}")
        else:
            # Top 10 fonctions
            stats_lines = prof["stats"].split("\n")
            for line in stats_lines[:15]:
                if line.strip():
                    print(f"  {line}")
        print()

    # Sauvegarder rapport
    full_report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sql_benchmarks": bench_results,
    }
    if args.module:
        full_report["profile"] = prof
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(full_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Rapport : {REPORT_PATH}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())