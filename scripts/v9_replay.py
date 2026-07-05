#!/usr/bin/env python3
"""v9_replay.py — Replay / inspection en lecture seule, chaîne cognitive V9.

Permet de lister, afficher en détail, comparer et rechercher des
comportements qualifiés (et les couches associées : scène, snapshot de
forces, fenêtre, exploitabilité). Lecture seule stricte sur
data/v9_forces.db — aucune écriture, aucune logique de trading, aucune
logique d'exécution d'ordre.

Usage :
    python scripts/v9_replay.py --list
    python scripts/v9_replay.py --show <behavior_id>
    python scripts/v9_replay.py --compare <behavior_id_1> <behavior_id_2>
    python scripts/v9_replay.py --search qualification=bascule
    python scripts/v9_replay.py --search intensite=forte symbol=GBPUSD
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402

JSON_FIELDS_SCENES = [
    "zone_json", "coalitions_json", "antagonismes_json",
    "cinematique_json", "confluences_mtf_json", "contexte_temporel_json",
]

SEARCHABLE_FIELDS = {
    "qualification": "qualification",
    "intensite": "intensite",
    "phase": "phase",
    "symbol": "symbol",
    "timeframe": "timeframe",
}


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _s(value) -> str:
    """Convertit une valeur potentiellement None en chaîne affichable."""
    return "" if value is None else str(value)


def _row_to_dict(conn: sqlite3.Connection, table: str, row: tuple) -> dict:
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    return dict(zip(cols, row))


def fetch_all_behaviors(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "behaviors"):
        return []
    rows = conn.execute("SELECT * FROM behaviors ORDER BY id ASC").fetchall()
    return [_row_to_dict(conn, "behaviors", row) for row in rows]


def fetch_behavior_by_id(conn: sqlite3.Connection, behavior_id: str) -> dict | None:
    if not table_exists(conn, "behaviors"):
        return None
    row = conn.execute(
        "SELECT * FROM behaviors WHERE behavior_id = ?", (behavior_id,)
    ).fetchone()
    return _row_to_dict(conn, "behaviors", row) if row else None


def fetch_scene_by_id(conn: sqlite3.Connection, scene_id: str) -> dict | None:
    if not table_exists(conn, "scenes"):
        return None
    row = conn.execute(
        "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
    ).fetchone()
    if not row:
        return None
    scene = _row_to_dict(conn, "scenes", row)
    for field in JSON_FIELDS_SCENES:
        raw = scene.get(field)
        if raw:
            try:
                scene[field] = json.loads(raw)
            except (TypeError, ValueError):
                pass
    return scene


def fetch_forces_snapshot_by_id(conn: sqlite3.Connection, snapshot_id: str) -> dict | None:
    if not table_exists(conn, "forces_snapshots"):
        return None
    row = conn.execute(
        "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    return _row_to_dict(conn, "forces_snapshots", row) if row else None


def fetch_window_by_behavior_id(conn: sqlite3.Connection, behavior_id: str) -> dict | None:
    if not table_exists(conn, "windows"):
        return None
    row = conn.execute(
        "SELECT * FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1", (behavior_id,)
    ).fetchone()
    return _row_to_dict(conn, "windows", row) if row else None


def fetch_exploitability_by_window_id(conn: sqlite3.Connection, window_id: str) -> dict | None:
    if not table_exists(conn, "exploitability"):
        return None
    row = conn.execute(
        "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1", (window_id,)
    ).fetchone()
    return _row_to_dict(conn, "exploitability", row) if row else None


# ── --list ────────────────────────────────────────────────
def run_list(conn: sqlite3.Connection | None) -> int:
    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 0

    behaviors = fetch_all_behaviors(conn)
    if not behaviors:
        print("Aucun comportement qualifié pour l'instant.")
        return 0

    header = f"{'behavior_id':<40} {'timestamp':<25} {'qualification':<16} {'intensite':<10} {'confiance':<9} {'symbol':<10} {'tf':<5} scene_id_ref"
    print(header)
    print("-" * len(header))
    for b in behaviors:
        print(
            f"{_s(b.get('behavior_id')):<40} {_s(b.get('timestamp')):<25} "
            f"{_s(b.get('qualification')):<16} {_s(b.get('intensite')):<10} "
            f"{_s(b.get('confiance_qualification')):<9} {_s(b.get('symbol')):<10} "
            f"{_s(b.get('timeframe')):<5} {_s(b.get('scene_id_ref'))}"
        )
    return 0


# ── --show ────────────────────────────────────────────────
def run_show(conn: sqlite3.Connection | None, behavior_id: str) -> int:
    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 1

    behavior = fetch_behavior_by_id(conn, behavior_id)
    if behavior is None:
        print(f"Comportement introuvable : {behavior_id}")
        return 1

    print("=" * 60)
    print(f"COMPORTEMENT — {behavior_id}")
    print("=" * 60)
    print(json.dumps(behavior, ensure_ascii=False, indent=2, default=str))

    scene = fetch_scene_by_id(conn, behavior.get("scene_id_ref"))
    print("\n" + "-" * 60)
    print("SCÈNE SOURCE")
    print("-" * 60)
    if scene:
        print(json.dumps(scene, ensure_ascii=False, indent=2, default=str))
    else:
        print("(scène source introuvable)")

    snapshot = None
    if scene and scene.get("forces_snapshot_ref"):
        snapshot = fetch_forces_snapshot_by_id(conn, scene["forces_snapshot_ref"])
    print("\n" + "-" * 60)
    print("SNAPSHOT DE FORCES SOURCE")
    print("-" * 60)
    if snapshot:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    else:
        print("(snapshot de forces introuvable)")

    window = fetch_window_by_behavior_id(conn, behavior_id)
    print("\n" + "-" * 60)
    print("FENÊTRE PRODUITE")
    print("-" * 60)
    if window:
        print(json.dumps(window, ensure_ascii=False, indent=2, default=str))
    else:
        print("(aucune fenêtre produite pour ce comportement)")

    evaluation = None
    if window:
        evaluation = fetch_exploitability_by_window_id(conn, window["window_id"])
    print("\n" + "-" * 60)
    print("ÉVALUATION D'EXPLOITABILITÉ")
    print("-" * 60)
    if evaluation:
        print(json.dumps(evaluation, ensure_ascii=False, indent=2, default=str))
    else:
        print("(aucune évaluation d'exploitabilité pour ce comportement)")

    return 0


# ── --compare ─────────────────────────────────────────────
def _cinematique_of(conn: sqlite3.Connection, behavior: dict) -> dict:
    scene = fetch_scene_by_id(conn, behavior.get("scene_id_ref"))
    if not scene:
        return {}
    cinematique = scene.get("cinematique_json")
    return cinematique if isinstance(cinematique, dict) else {}


def _coalitions_antagonismes_of(conn: sqlite3.Connection, behavior: dict) -> tuple[list, list]:
    scene = fetch_scene_by_id(conn, behavior.get("scene_id_ref"))
    if not scene:
        return [], []
    coalitions = scene.get("coalitions_json")
    antagonismes = scene.get("antagonismes_json")
    coalitions = coalitions if isinstance(coalitions, list) else []
    antagonismes = antagonismes if isinstance(antagonismes, list) else []
    return coalitions, antagonismes


def compute_similarity_score(behavior_a: dict, behavior_b: dict, cinematique_a: dict, cinematique_b: dict) -> float:
    """Score de similarité heuristique (0.0-1.0), indépendant du champ
    `similarite_score` de chaque comportement (qui compare à l'historique
    replay, pas à un autre comportement précis). Pondération : qualification
    (0.3), intensité (0.15), phase (0.15), symbol (0.1), timeframe (0.1),
    acceleration_deceleration (0.1), compression_extension.etat (0.1)."""
    score = 0.0
    if behavior_a.get("qualification") == behavior_b.get("qualification"):
        score += 0.3
    if behavior_a.get("intensite") == behavior_b.get("intensite"):
        score += 0.15
    if behavior_a.get("phase") == behavior_b.get("phase"):
        score += 0.15
    if behavior_a.get("symbol") == behavior_b.get("symbol"):
        score += 0.1
    if behavior_a.get("timeframe") == behavior_b.get("timeframe"):
        score += 0.1
    if cinematique_a.get("acceleration_deceleration") == cinematique_b.get("acceleration_deceleration"):
        score += 0.1
    ce_a = cinematique_a.get("compression_extension") or {}
    ce_b = cinematique_b.get("compression_extension") or {}
    if ce_a.get("etat") == ce_b.get("etat"):
        score += 0.1
    return round(score, 2)


def run_compare(conn: sqlite3.Connection | None, id_a: str, id_b: str) -> int:
    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 1

    behavior_a = fetch_behavior_by_id(conn, id_a)
    behavior_b = fetch_behavior_by_id(conn, id_b)
    if behavior_a is None:
        print(f"Comportement introuvable : {id_a}")
        return 1
    if behavior_b is None:
        print(f"Comportement introuvable : {id_b}")
        return 1

    print("=" * 60)
    print(f"COMPARAISON — {id_a} vs {id_b}")
    print("=" * 60)

    print("\nQualification / intensité / phase :")
    for field in ("qualification", "intensite", "phase"):
        val_a, val_b = behavior_a.get(field), behavior_b.get(field)
        marker = "==" if val_a == val_b else "!="
        print(f"  {field:<14}: {val_a!r:<20} {marker} {val_b!r}")

    cinematique_a = _cinematique_of(conn, behavior_a)
    cinematique_b = _cinematique_of(conn, behavior_b)
    print("\nCinématique locale (scène source) :")
    keys = sorted(set(cinematique_a.keys()) | set(cinematique_b.keys()))
    if keys:
        for key in keys:
            val_a, val_b = cinematique_a.get(key), cinematique_b.get(key)
            marker = "==" if val_a == val_b else "!="
            print(f"  {key:<25}: {val_a!r:<20} {marker} {val_b!r}")
    else:
        print("  (cinématique indisponible pour l'une ou l'autre scène)")

    coalitions_a, antagonismes_a = _coalitions_antagonismes_of(conn, behavior_a)
    coalitions_b, antagonismes_b = _coalitions_antagonismes_of(conn, behavior_b)
    print("\nCoalitions :")
    print(f"  {id_a}: {len(coalitions_a)} coalition(s)")
    print(f"  {id_b}: {len(coalitions_b)} coalition(s)")
    print("\nAntagonismes :")
    print(f"  {id_a}: {len(antagonismes_a)} antagonisme(s)")
    print(f"  {id_b}: {len(antagonismes_b)} antagonisme(s)")

    score = compute_similarity_score(behavior_a, behavior_b, cinematique_a, cinematique_b)
    print(f"\nScore de similarité (heuristique) : {score}")

    return 0


# ── --search ──────────────────────────────────────────────
def parse_search_terms(terms: list[str]) -> dict:
    parsed = {}
    for term in terms:
        if "=" not in term:
            raise ValueError(f"Critère de recherche invalide (attendu key=value) : {term!r}")
        key, _, value = term.partition("=")
        parsed[key.strip()] = value.strip()
    return parsed


def matches_search(behavior: dict, criteria: dict) -> bool:
    for key, value in criteria.items():
        if key == "min_confiance":
            confiance = behavior.get("confiance_qualification")
            if confiance is None or confiance < float(value):
                return False
            continue
        column = SEARCHABLE_FIELDS.get(key)
        if column is None:
            raise ValueError(f"Critère de recherche non supporté : {key!r}")
        if str(behavior.get(column, "")) != value:
            return False
    return True


def run_search(conn: sqlite3.Connection | None, terms: list[str]) -> int:
    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 0

    try:
        criteria = parse_search_terms(terms)
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1

    behaviors = fetch_all_behaviors(conn)
    matched = [b for b in behaviors if matches_search(b, criteria)]

    if not matched:
        print(f"Aucun résultat pour {criteria}.")
        return 0

    header = f"{'behavior_id':<40} {'timestamp':<25} {'qualification':<16} {'intensite':<10} {'confiance':<9} {'symbol':<10} {'tf':<5}"
    print(f"{len(matched)} résultat(s) pour {criteria} :\n")
    print(header)
    print("-" * len(header))
    for b in matched:
        print(
            f"{_s(b.get('behavior_id')):<40} {_s(b.get('timestamp')):<25} "
            f"{_s(b.get('qualification')):<16} {_s(b.get('intensite')):<10} "
            f"{_s(b.get('confiance_qualification')):<9} {_s(b.get('symbol')):<10} "
            f"{_s(b.get('timeframe')):<5}"
        )
    return 0


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Replay / inspection - PowerFlow V9")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="Lister tous les comportements qualifiés")
    group.add_argument("--show", metavar="BEHAVIOR_ID", help="Afficher le détail complet d'un comportement")
    group.add_argument("--compare", nargs=2, metavar=("BEHAVIOR_ID_1", "BEHAVIOR_ID_2"), help="Comparer deux comportements")
    group.add_argument("--search", nargs="+", metavar="KEY=VALUE", help="Rechercher par critère(s)")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.list:
            return run_list(conn)
        if args.show:
            return run_show(conn, args.show)
        if args.compare:
            return run_compare(conn, args.compare[0], args.compare[1])
        if args.search:
            return run_search(conn, args.search)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
