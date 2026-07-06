#!/usr/bin/env python3
"""regenerate_chain.py — Reconstruit scenes/behaviors/windows/exploitability
(+ regime_snapshots/principle_evaluations/signals/decisions) depuis
forces_snapshots (data/v9_forces.db).

Relit tous les snapshots non-stale de forces_snapshots, par ordre
chronologique, et les fait traverser la chaine cognitive complete via
core.v9.orchestrator.run_chain.

Non-idempotence connue (corrigee ici) — scene_id/behavior_id/window_id/
exploitability_id/signal_id/decision_id/evaluation_id sont generes avec
un suffixe aleatoire (uuid4) a chaque appel de run_chain(). Aucune de ces
tables (a l'exception de regime_snapshots, qui a une contrainte UNIQUE
metier sur (forces_snapshot_ref, currency)) ne porte de cle metier
liee au snapshot source : rejouer ce script sur une DB deja peuplee ne
peut donc jamais detecter un doublon via INSERT OR IGNORE/REPLACE — il
duplique silencieusement chaque ligne derivee a chaque rejeu.

Plutot que d'introduire des cles metier et un upsert dans sept modules
de couche (chantier transverse hors perimetre), ce script applique la
strategie B (delete cible + regeneration complete) derriere un flag
explicite, et refuse par defaut de s'executer sur une DB deja peuplee :

    python scripts/regenerate_chain.py
        Rejeu normal. Refuse (exit 2) si une seule table derivee
        contient deja des lignes — jamais de duplication silencieuse.

    python scripts/regenerate_chain.py --dry-run
        N'ecrit rien : rapporte l'etat actuel des tables derivees et ce
        qui serait fait.

    python scripts/regenerate_chain.py --replace-derived
        Supprime d'abord toutes les lignes des tables derivees (jamais
        forces_snapshots, jamais le catalogue `principles`), puis
        regenere completement depuis les snapshots non-stale. Seul mode
        sur pour rejouer une DB deja peuplee.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.orchestrator import run_chain  # noqa: E402

PROGRESS_EVERY = 50

# Tables peuplees par run_chain() a partir d'un snapshot de forces —
# jamais forces_snapshots (source) ni `principles` (catalogue synchronise
# depuis les YAML, pas un evenement par snapshot). Ordre de suppression :
# de la plus derivee vers la moins derivee (aucune FK SQLite declaree ici,
# mais respecter l'ordre de la chaine cognitive garde un DELETE partiel
# interrompu dans un etat coherent).
DERIVED_TABLES = [
    "decisions",
    "signals",
    "principle_evaluations",
    "regime_snapshots",
    "exploitability",
    "windows",
    "behaviors",
    "scenes",
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _derived_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in DERIVED_TABLES:
        if _table_exists(conn, table):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        else:
            counts[table] = 0
    return counts


def _wipe_derived_tables(conn: sqlite3.Connection, counts: dict[str, int]) -> None:
    for table in DERIVED_TABLES:
        if counts.get(table, 0) and _table_exists(conn, table):
            conn.execute(f"DELETE FROM {table}")
    conn.commit()


def _run_chain_over_snapshots(db_path: Path, memory_dir: Path | None) -> int:
    """Rejoue run_chain() sur tous les snapshots non-stale, par ordre
    chronologique. Retourne 0 si aucune erreur de chaine, 1 sinon."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT snapshot_id FROM forces_snapshots WHERE stale = 0 ORDER BY timestamp ASC"
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    print(f"Snapshots non-stale a traiter : {total}")

    scenes = behaviors = windows = evaluations = errors = 0
    error_details: list[str] = []
    durations_ms: list[float] = []

    for i, (snapshot_id,) in enumerate(rows, start=1):
        t0 = time.perf_counter()
        result = run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir, source_type="replay")
        durations_ms.append((time.perf_counter() - t0) * 1000)

        if result["scene_id"]:
            scenes += 1
        if result["behavior_id"]:
            behaviors += 1
        if result["window_id"]:
            windows += 1
        if result["exploitability_id"]:
            evaluations += 1
        if result["error"]:
            errors += 1
            error_details.append(f"{snapshot_id}: {result['error']}")

        if i % PROGRESS_EVERY == 0 or i == total:
            print(
                f"[{i}/{total}] scenes={scenes} behaviors={behaviors} "
                f"windows={windows} evaluations={evaluations} erreurs={errors}"
            )

    avg_ms = sum(durations_ms) / len(durations_ms) if durations_ms else 0.0

    print("=" * 60)
    print("Rapport final - Regeneration de la chaine V9")
    print("=" * 60)
    print(f"Snapshots traites          : {total}")
    print(f"Scenes produites           : {scenes}")
    print(f"Comportements qualifies    : {behaviors}")
    print(f"Fenetres produites         : {windows}")
    print(f"Evaluations exploitabilite : {evaluations}")
    print(f"Latence moyenne par snapshot (chaine complete) : {avg_ms:.2f}ms")
    print(f"Erreurs detectees ({errors}):")
    for detail in error_details[:20]:
        print(f"  - {detail}")
    if len(error_details) > 20:
        print(f"  ... et {len(error_details) - 20} autres")

    return 0 if errors == 0 else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruit scenes/behaviors/windows/exploitability/regime_snapshots/"
            "principle_evaluations/signals/decisions depuis forces_snapshots."
        )
    )
    parser.add_argument(
        "--replace-derived",
        action="store_true",
        help=(
            "Supprime d'abord toutes les lignes des tables derivees (jamais "
            "forces_snapshots) avant de regenerer completement depuis les "
            "snapshots non-stale. Seul mode explicite autorise sur une DB "
            "deja peuplee."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "N'ecrit rien : rapporte l'etat actuel des tables derivees et "
            "ce qui serait fait, puis s'arrete."
        ),
    )
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    db_path: Path | None = None,
    memory_dir: Path | None = None,
) -> int:
    db_path = db_path or DB_PATH
    args = _parse_args(argv)

    conn = get_connection(db_path)
    try:
        counts = _derived_counts(conn)
    finally:
        conn.close()
    total_derived = sum(counts.values())

    if args.dry_run:
        print("Mode --dry-run : aucune ecriture.")
        print("Etat actuel des tables derivees :")
        for table in DERIVED_TABLES:
            print(f"  - {table:24s}: {counts[table]}")
        if total_derived == 0:
            print(
                "DB derivee vide -> un run sans --replace-derived regenererait "
                "normalement (premier run)."
            )
        elif args.replace_derived:
            print(
                f"{total_derived} lignes derivees seraient supprimees, puis la "
                "chaine serait rejouee depuis forces_snapshots."
            )
        else:
            print(
                f"{total_derived} lignes derivees deja presentes -> un run sans "
                "--replace-derived serait refuse (rejeu non sur, risque de doublons)."
            )
        return 0

    if total_derived and not args.replace_derived:
        print(
            "REFUS : les tables derivees contiennent deja des donnees "
            f"({total_derived} lignes au total) :",
            file=sys.stderr,
        )
        for table in DERIVED_TABLES:
            if counts[table]:
                print(f"  - {table}: {counts[table]}", file=sys.stderr)
        print(
            "Rejouer sur une DB deja peuplee sans --replace-derived produirait "
            "des doublons silencieux (scene_id/behavior_id/window_id/"
            "exploitability_id/signal_id/decision_id sont generes aleatoirement "
            "a chaque appel, aucune cle metier ne protege ces tables). "
            "Relancez avec --replace-derived pour supprimer proprement les "
            "tables derivees (jamais forces_snapshots) puis regenerer depuis "
            "les snapshots, ou avec --dry-run pour inspecter l'etat actuel "
            "sans rien modifier.",
            file=sys.stderr,
        )
        return 2

    if args.replace_derived and total_derived:
        conn = get_connection(db_path)
        try:
            print(f"--replace-derived : suppression de {total_derived} lignes derivees...")
            _wipe_derived_tables(conn, counts)
            for table in DERIVED_TABLES:
                if counts[table]:
                    print(f"  - {table}: {counts[table]} lignes supprimees")
        finally:
            conn.close()

    return _run_chain_over_snapshots(db_path, memory_dir)


if __name__ == "__main__":
    sys.exit(main())
