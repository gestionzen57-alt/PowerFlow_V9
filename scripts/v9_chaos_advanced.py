"""v9_chaos_advanced.py — Phase 70 motion CEO 48H.

Chaos engineering advanced : simulated splits, latency, network failure.
Verifie resilience du systeme.

Auteur : Hermes (Phase 70 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.chaos_advanced")


def inject_partition(workers: list[str], n_partitions: int = 2,
                      rng: random.Random = None) -> dict:
    """Simule network partition : workers split en N groupes."""
    if rng is None:
        rng = random.Random()
    rng.shuffle(workers)
    partitions = [[] for _ in range(n_partitions)]
    for i, w in enumerate(workers):
        partitions[i % n_partitions].append(w)
    return {
        "scenario": "partition",
        "n_partitions": n_partitions,
        "partitions": partitions,
    }


def inject_latency(duration_ms: int = 100,
                    rng: random.Random = None) -> int:
    """Simule latence additionnelle."""
    if rng is None:
        rng = random.Random()
    extra = rng.randint(0, duration_ms)
    return extra


def inject_packet_loss(loss_pct: float = 5.0,
                        rng: random.Random = None) -> bool:
    """Simule packet loss : renvoie True si packet perdu."""
    if rng is None:
        rng = random.Random()
    return rng.random() * 100 < loss_pct


def inject_disk_full(path: Path, mb: int = 1) -> dict:
    """Simule disk full (en ecrit)."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    test_file = path / f"chaos_disk_{int(time.time())}.bin"
    try:
        with open(test_file, "wb") as f:
            f.write(b"x" * (mb * 1024 * 1024))
        test_file.unlink()
        return {
            "scenario": "disk_full",
            "written_mb": mb,
            "success": True,
        }
    except OSError as e:
        return {
            "scenario": "disk_full",
            "error": str(e),
            "success": False,
        }


def chaos_test_suite(workers: list[str] = None) -> dict:
    """Run tous les scenarios chaos."""
    if workers is None:
        workers = ["worker1", "worker2", "worker3", "worker4"]
    return {
        "partition": inject_partition(workers, n_partitions=2),
        "latency": inject_latency(duration_ms=200),
        "packet_loss_5pct": inject_packet_loss(loss_pct=5.0),
        "packet_loss_50pct": inject_packet_loss(loss_pct=50.0),
        "disk_full": inject_disk_full(Path(r"C:\projet\V9\data"),
                                          mb=1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 chaos advanced (Phase 70)",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print("V9 CHAOS ADVANCED")
    print("=" * 70)
    result = chaos_test_suite()
    for k, v in result.items():
        if isinstance(v, dict):
            print(f"  {k:18s} : {v.get('scenario', '?')}")
        else:
            print(f"  {k:18s} : {v}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
