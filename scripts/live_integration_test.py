#!/usr/bin/env python3
"""live_integration_test.py — Test d'intégration live, chaîne complète V9.

Attend que le serveur de capture (core/v9/capture_server.py, DB de
production data/v9_forces.db) reçoive de vrais snapshots de marché, puis
fait traverser chaque nouveau snapshot non-stale à travers la chaîne
cognitive complète (Scènes → Comportements → Fenêtres → Exploitabilité) sur
une DB de test dédiée, copiée à partir du snapshot réel.

Règle : ce script ne modifie JAMAIS la DB de production (lecture seule sur
data/v9_forces.db). Toutes les écritures des couches avales se font sur une
DB de test séparée (par défaut data/v9_live_test.db, recréée à chaque
lancement sauf --keep-db).

Couche cognitive : orchestration de test uniquement. Aucune logique de
trading, aucune décision, aucune interprétation au-delà de ce que chaque
couche produit déjà.

Usage :
    python scripts/live_integration_test.py --duration 300
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.behavior_analyzer import BehaviorAnalyzer  # noqa: E402
from core.v9.config import DB_PATH, ROOT_DIR as CFG_ROOT  # noqa: E402
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db  # noqa: E402
from core.v9.exploitability_evaluator import ExploitabilityEvaluator  # noqa: E402
from core.v9.scene_builder import SceneBuilder  # noqa: E402
from core.v9.window_gate import WindowGate  # noqa: E402

DEFAULT_TEST_DB = CFG_ROOT / "data" / "v9_live_test.db"
LAYERS = ["scenes", "behaviors", "windows", "exploitability"]


class ChainStats:
    def __init__(self) -> None:
        self.snapshots_processed = 0
        self.snapshots_stale_skipped = 0
        self.scenes = 0
        self.behaviors = 0
        self.windows = 0
        self.evaluations = 0
        self.layer_times_ms: dict[str, list[float]] = {layer: [] for layer in LAYERS}
        self.errors: list[str] = []
        self.first_behavior: dict | None = None
        self.first_window: dict | None = None
        self.first_evaluation: dict | None = None

    def stale_rate(self) -> float:
        total = self.snapshots_processed + self.snapshots_stale_skipped
        return (self.snapshots_stale_skipped / total * 100) if total else 0.0

    def avg_layer_ms(self, layer: str) -> float:
        times = self.layer_times_ms[layer]
        return sum(times) / len(times) if times else 0.0


def _fetch_new_snapshots(last_id: int) -> list[dict]:
    """Lecture seule sur la DB de production."""
    conn = get_connection(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT * FROM forces_snapshots WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM forces_snapshots LIMIT 0").description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def _max_snapshot_id() -> int:
    if not DB_PATH.exists():
        return 0
    conn = get_connection(DB_PATH)
    try:
        result = conn.execute("SELECT COALESCE(MAX(id), 0) FROM forces_snapshots").fetchone()
        return result[0]
    finally:
        conn.close()


def _copy_snapshot_to_test_db(row: dict, test_db_path: Path) -> None:
    conn = get_connection(test_db_path)
    try:
        col_names = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        conn.execute(
            f"INSERT OR IGNORE INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()


def _run_chain_for_snapshot(
    snapshot_id: str, test_db_path: Path, memory_dir: Path, stats: ChainStats
) -> None:
    try:
        t0 = time.perf_counter()
        scene_builder = SceneBuilder(db_path=test_db_path, config={"memory_dir": memory_dir})
        scene = scene_builder.build_scene(snapshot_id)
        scene_builder._write_scene_to_db(scene)
        stats.layer_times_ms["scenes"].append((time.perf_counter() - t0) * 1000)
        stats.scenes += 1
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"scene_builder[{snapshot_id}]: {exc}")
        return

    try:
        t0 = time.perf_counter()
        behavior_analyzer = BehaviorAnalyzer(db_path=test_db_path, config={"memory_dir": memory_dir})
        behavior = behavior_analyzer.analyze_scene(scene["scene_id"])
        stats.layer_times_ms["behaviors"].append((time.perf_counter() - t0) * 1000)
        stats.behaviors += 1
        if stats.first_behavior is None:
            stats.first_behavior = behavior
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"behavior_analyzer[{scene['scene_id']}]: {exc}")
        return

    try:
        t0 = time.perf_counter()
        window_gate = WindowGate(db_path=test_db_path, memory_path=memory_dir / "memory_temp.md")
        window = window_gate.evaluate_behavior(behavior["behavior_id"])
        stats.layer_times_ms["windows"].append((time.perf_counter() - t0) * 1000)
        stats.windows += 1
        if stats.first_window is None:
            stats.first_window = window
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"window_gate[{behavior['behavior_id']}]: {exc}")
        return

    try:
        t0 = time.perf_counter()
        evaluator = ExploitabilityEvaluator(db_path=test_db_path, config={"memory_dir": memory_dir})
        evaluation = evaluator.evaluate_window(window["window_id"])
        stats.layer_times_ms["exploitability"].append((time.perf_counter() - t0) * 1000)
        stats.evaluations += 1
        if stats.first_evaluation is None:
            stats.first_evaluation = evaluation
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"exploitability_evaluator[{window['window_id']}]: {exc}")
        return


def print_final_report(stats: ChainStats) -> None:
    print("=" * 60)
    print("Rapport final - Test d'integration live V9")
    print("=" * 60)
    print(f"Snapshots traites          : {stats.snapshots_processed}")
    print(f"Snapshots stale ignores    : {stats.snapshots_stale_skipped}")
    print(f"Taux de stale              : {stats.stale_rate():.1f}%")
    print(f"Scenes produites           : {stats.scenes}")
    print(f"Comportements qualifies    : {stats.behaviors}")
    print(f"Fenetres produites         : {stats.windows}")
    print(f"Evaluations exploitabilite : {stats.evaluations}")
    print("Temps moyen par couche (ms):")
    for layer in LAYERS:
        avg = stats.avg_layer_ms(layer)
        n = len(stats.layer_times_ms[layer])
        print(f"  {layer:<15} : {avg:.2f}ms (n={n})")
    print(f"Erreurs detectees ({len(stats.errors)}):")
    for err in stats.errors[:20]:
        print(f"  - {err}")
    if len(stats.errors) > 20:
        print(f"  ... et {len(stats.errors) - 20} autres")

    print("-" * 60)
    if stats.first_behavior:
        comportement = stats.first_behavior["comportement"]
        print(
            f"Premier comportement qualifie : {comportement['qualification']} "
            f"(confiance={comportement['confiance_qualification']})"
        )
    else:
        print("Premier comportement qualifie : aucun")

    if stats.first_window:
        print(f"Premier statut de fenetre     : {stats.first_window['statut']}")
    else:
        print("Premier statut de fenetre     : aucun")

    if stats.first_evaluation:
        print(f"Premier statut d'exploitabilite: {stats.first_evaluation['statut']}")
    else:
        print("Premier statut d'exploitabilite: aucun")


def run(duration_s: float, interval_s: float, test_db_path: Path, keep_db: bool) -> int:
    if not DB_PATH.exists():
        print(f"DB de production introuvable : {DB_PATH}")
        print("Demarrer d'abord le serveur de capture : python scripts/deploy_v9.py --start")
        return 1

    if test_db_path.exists() and not keep_db:
        test_db_path.unlink()
        for suffix in ("-wal", "-shm"):
            side = Path(str(test_db_path) + suffix)
            if side.exists():
                side.unlink()

    init_db(test_db_path)
    memory_dir = test_db_path.parent / "memory_live_test"
    memory_dir.mkdir(parents=True, exist_ok=True)

    stats = ChainStats()
    last_id = _max_snapshot_id()
    print(f"DB production   : {DB_PATH}")
    print(f"DB test (aval)  : {test_db_path}")
    print(f"Snapshot id de depart (lecture seule) : {last_id}")
    print(f"En attente de nouveaux snapshots pendant {duration_s:.0f}s (poll={interval_s}s)...")

    deadline = time.monotonic() + duration_s
    received_any = False

    while time.monotonic() < deadline:
        new_rows = _fetch_new_snapshots(last_id)
        for row in new_rows:
            last_id = row["id"]
            received_any = True
            if row.get("stale"):
                stats.snapshots_stale_skipped += 1
                continue

            _copy_snapshot_to_test_db(row, test_db_path)
            stats.snapshots_processed += 1
            print(f"[{stats.snapshots_processed}] snapshot {row['snapshot_id']} "
                  f"({row['symbol']} {row['timeframe']}) -> chaine complete...")
            _run_chain_for_snapshot(row["snapshot_id"], test_db_path, memory_dir, stats)

        time.sleep(interval_s)

    if not received_any:
        print("Aucun nouveau snapshot recu pendant la duree du test "
              "(marche probablement ferme, ou EA non lance).")

    print_final_report(stats)
    return 0 if not stats.errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test d'integration live - chaine complete V9")
    parser.add_argument("--duration", type=float, default=300.0, help="Duree du test en secondes (defaut: 300)")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalle de poll en secondes (defaut: 2)")
    parser.add_argument("--test-db", type=Path, default=DEFAULT_TEST_DB, help="Chemin de la DB de test (aval)")
    parser.add_argument("--keep-db", action="store_true", help="Ne pas recreer la DB de test au demarrage")
    args = parser.parse_args()

    return run(args.duration, args.interval, args.test_db, args.keep_db)


if __name__ == "__main__":
    sys.exit(main())
