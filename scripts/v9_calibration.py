#!/usr/bin/env python3
"""v9_calibration.py — Calibration des seuils, export et statistiques V9.

Lit uniquement data/v9_forces.db (5 tables). Ne modifie jamais la DB, et ne
modifie jamais core/v9/config.py : `--analyze` ne fait que SUGGÉRER des
valeurs de seuils, à appliquer manuellement après revue humaine.

Couche cognitive : outillage de calibration / export uniquement. Aucune
logique de trading, aucune logique d'exécution d'ordre.

Usage :
    python scripts/v9_calibration.py --analyze
    python scripts/v9_calibration.py --export csv
    python scripts/v9_calibration.py --export json
    python scripts/v9_calibration.py --stats
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, DEVISES  # noqa: E402

TABLES = ["forces_snapshots", "scenes", "behaviors", "windows", "exploitability"]

EXPORT_FILENAMES = {
    "forces_snapshots": "forces_export",
    "scenes": "scenes_export",
    "behaviors": "behaviors_export",
    "windows": "windows_export",
    "exploitability": "exploitability_export",
}

OUTPUT_DIR = ROOT_DIR / "output"

TF_ORDER = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def connect() -> sqlite3.Connection | None:
    """Connexion en lecture (aucune écriture n'est jamais exécutée par ce
    script). Retourne None si la DB n'existe pas encore."""
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def fetch_all_dicts(conn: sqlite3.Connection, table: str) -> list[dict]:
    if not table_exists(conn, table):
        return []
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(zip(cols, row)) for row in rows]


def column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(conn, table):
        return []
    return [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]


# ── --stats ───────────────────────────────────────────────
def run_stats(conn: sqlite3.Connection | None) -> int:
    print("=" * 60)
    print("PowerFlow V9 - Statistiques globales (--stats)")
    print("=" * 60)

    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 0

    print("Nombre total par couche :")
    for table in TABLES:
        n = len(fetch_all_dicts(conn, table)) if table_exists(conn, table) else 0
        print(f"  {table:<18}: {n}")
    print()

    behaviors = fetch_all_dicts(conn, "behaviors")
    if behaviors:
        print("Distribution des qualifications de comportement :")
        qual_counts = Counter(b.get("qualification") for b in behaviors)
        for qual, n in qual_counts.most_common():
            print(f"  {qual:<30}: {n}")
        print()

        print("Top 5 des comportements les plus fréquents :")
        for qual, n in qual_counts.most_common(5):
            print(f"  {qual:<30}: {n}")
        print()

        print("Top 5 des paires les plus actives :")
        symbol_counts = Counter(b.get("symbol") for b in behaviors)
        for symbol, n in symbol_counts.most_common(5):
            print(f"  {symbol:<10}: {n}")
        print()
    else:
        print("Aucun comportement qualifié pour l'instant.\n")

    windows = fetch_all_dicts(conn, "windows")
    if windows:
        print("Distribution des statuts de fenêtre :")
        statut_counts = Counter(w.get("statut") for w in windows)
        for statut, n in statut_counts.most_common():
            print(f"  {statut:<15}: {n}")
        print()
    else:
        print("Aucune fenêtre évaluée pour l'instant.\n")

    exploitability = fetch_all_dicts(conn, "exploitability")
    if exploitability:
        print("Distribution des statuts d'exploitabilité :")
        statut_counts = Counter(e.get("statut") for e in exploitability)
        for statut, n in statut_counts.most_common():
            print(f"  {statut:<15}: {n}")
        print()
    else:
        print("Aucune évaluation d'exploitabilité pour l'instant.\n")

    return 0


# ── --export ──────────────────────────────────────────────
def run_export(conn: sqlite3.Connection | None, fmt: str) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Export {fmt} vers {OUTPUT_DIR}/")

    for table in TABLES:
        filename_base = EXPORT_FILENAMES[table]
        if conn is not None and table_exists(conn, table):
            rows = fetch_all_dicts(conn, table)
            cols = column_names(conn, table)
        else:
            rows, cols = [], []

        if fmt == "csv":
            path = OUTPUT_DIR / f"{filename_base}.csv"
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if cols:
                    writer.writerow(cols)
                    for row in rows:
                        writer.writerow([row.get(c) for c in cols])
            print(f"  {path.name} ({len(rows)} lignes)")
        else:  # json
            path = OUTPUT_DIR / f"{filename_base}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
            print(f"  {path.name} ({len(rows)} lignes)")

    return 0


# ── --analyze ─────────────────────────────────────────────
def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _force_amplitude(row: dict) -> float | None:
    values = [row.get(f"force_{d.lower()}") for d in DEVISES]
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    return max(values) - min(values)


def _pairwise_force_gaps(row: dict) -> list[float]:
    values = [row.get(f"force_{d.lower()}") for d in DEVISES]
    values = [v for v in values if v is not None]
    gaps = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            gaps.append(abs(values[i] - values[j]))
    return gaps


def analyze_forces(rows: list[dict]) -> dict:
    by_tf: dict[str, list[dict]] = {}
    for row in rows:
        by_tf.setdefault(row.get("timeframe"), []).append(row)

    report = {}
    for tf, tf_rows in by_tf.items():
        force_stats = {}
        for devise in DEVISES:
            values = [r.get(f"force_{devise.lower()}") for r in tf_rows]
            values = [v for v in values if v is not None]
            if values:
                force_stats[devise] = {
                    "min": min(values),
                    "max": max(values),
                    "mean": round(statistics.mean(values), 2),
                    "stdev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
                }

        amplitudes = [round(a, 2) for a in (_force_amplitude(r) for r in tf_rows) if a is not None]
        vitesses = [r.get("vitesse") for r in tf_rows if r.get("vitesse") is not None]
        croisements = sum(1 for r in tf_rows if r.get("croisement_detecte"))
        stale_count = sum(1 for r in tf_rows if r.get("stale"))
        pairwise_gaps: list[float] = []
        for r in tf_rows:
            pairwise_gaps.extend(_pairwise_force_gaps(r))

        report[tf] = {
            "n_snapshots": len(tf_rows),
            "forces": force_stats,
            "amplitude": {
                "min": min(amplitudes) if amplitudes else None,
                "max": max(amplitudes) if amplitudes else None,
                "mean": round(statistics.mean(amplitudes), 2) if amplitudes else None,
            },
            "vitesse": {
                "min": min(vitesses) if vitesses else None,
                "max": max(vitesses) if vitesses else None,
                "mean": round(statistics.mean(vitesses), 2) if vitesses else None,
            },
            "croisement_frequence_pct": round(croisements / len(tf_rows) * 100, 1) if tf_rows else 0.0,
            "stale_rate_pct": round(stale_count / len(tf_rows) * 100, 1) if tf_rows else 0.0,
            "pairwise_gaps_p20": _percentile(pairwise_gaps, 20),
            "pairwise_gaps_p80": _percentile(pairwise_gaps, 80),
        }
    return report


def analyze_scenes(rows: list[dict]) -> dict:
    coalitions_counts = []
    antagonismes_counts = []
    for row in rows:
        try:
            coalitions = json.loads(row.get("coalitions_json") or "[]")
        except (TypeError, ValueError):
            coalitions = []
        try:
            antagonismes = json.loads(row.get("antagonismes_json") or "[]")
        except (TypeError, ValueError):
            antagonismes = []
        coalitions_counts.append(len(coalitions))
        antagonismes_counts.append(len(antagonismes))

    n = len(rows)
    return {
        "n_scenes": n,
        "coalitions_frequence_pct": round(
            sum(1 for c in coalitions_counts if c > 0) / n * 100, 1
        ) if n else 0.0,
        "antagonismes_frequence_pct": round(
            sum(1 for c in antagonismes_counts if c > 0) / n * 100, 1
        ) if n else 0.0,
        "coalitions_moyenne_par_scene": round(statistics.mean(coalitions_counts), 2) if coalitions_counts else 0.0,
        "antagonismes_moyenne_par_scene": round(statistics.mean(antagonismes_counts), 2) if antagonismes_counts else 0.0,
    }


def _pente_deltas_by_tf(rows: list[dict]) -> dict[str, list[float]]:
    """Delta de pente (approx. via vitesse) entre snapshots consécutifs, par
    TF, ordonnés par bar_time."""
    by_tf: dict[str, list[dict]] = {}
    for row in rows:
        by_tf.setdefault(row.get("timeframe"), []).append(row)

    deltas_by_tf: dict[str, list[float]] = {}
    for tf, tf_rows in by_tf.items():
        ordered = sorted(tf_rows, key=lambda r: r.get("bar_time") or 0)
        vitesses = [r.get("vitesse") for r in ordered if r.get("vitesse") is not None]
        deltas = [abs(vitesses[i] - vitesses[i - 1]) for i in range(1, len(vitesses))]
        deltas_by_tf[tf] = deltas
    return deltas_by_tf


def _snapshot_intervals_ms_by_tf(rows: list[dict]) -> dict[str, list[float]]:
    """Intervalles réels (ms) entre snapshots consécutifs, par TF, basés sur
    bar_time (secondes epoch broker) ordonné."""
    by_tf: dict[str, list[dict]] = {}
    for row in rows:
        by_tf.setdefault(row.get("timeframe"), []).append(row)

    intervals_by_tf: dict[str, list[float]] = {}
    for tf, tf_rows in by_tf.items():
        bar_times = sorted(r.get("bar_time") for r in tf_rows if r.get("bar_time") is not None)
        intervals = [(bar_times[i] - bar_times[i - 1]) * 1000 for i in range(1, len(bar_times))]
        intervals_by_tf[tf] = [i for i in intervals if i > 0]
    return intervals_by_tf


def suggest_thresholds(forces_rows: list[dict]) -> dict:
    """Suggestions de seuils — NE modifie jamais config.py. Approche : les
    coalitions/antagonismes réels dépendent de la direction par devise
    (logique interne de scene_builder.py, non ré-implémentée ici) ; à défaut,
    ce script utilise l'écart absolu de force entre toutes les paires de
    devises d'un même snapshot comme proxy observable, et propose
    COALITION_THRESHOLD au 20e percentile (petits écarts = alignement) et
    ANTAGONISM_THRESHOLD au 80e percentile (grands écarts = conflit) de cette
    distribution. PLIURE_THRESHOLD est suggéré à partir du 75e percentile des
    deltas de vitesse consécutifs (proxy de delta de pente). Les seuils de
    staleness sont suggérés à partir du 95e percentile des intervalles réels
    entre snapshots consécutifs par timeframe (x3, marge de sécurité)."""
    all_gaps: list[float] = []
    for row in forces_rows:
        all_gaps.extend(_pairwise_force_gaps(row))

    pente_deltas = _pente_deltas_by_tf(forces_rows)
    all_pente_deltas = [d for deltas in pente_deltas.values() for d in deltas]

    intervals_by_tf = _snapshot_intervals_ms_by_tf(forces_rows)
    stale_suggestions = {}
    for tf, intervals in intervals_by_tf.items():
        p95 = _percentile(intervals, 95)
        if p95 is not None:
            stale_suggestions[tf] = round(p95 * 3)

    coalition_pct = _percentile(all_gaps, 20)
    antagonism_pct = _percentile(all_gaps, 80)
    pliure_pct = _percentile(all_pente_deltas, 75)
    return {
        "COALITION_THRESHOLD": round(coalition_pct, 2) if coalition_pct is not None else None,
        "ANTAGONISM_THRESHOLD": round(antagonism_pct, 2) if antagonism_pct is not None else None,
        "PLIURE_THRESHOLD": round(pliure_pct, 2) if pliure_pct is not None else None,
        "STALE_THRESHOLDS_MS": stale_suggestions,
    }


def run_analyze(conn: sqlite3.Connection | None) -> int:
    print("=" * 60)
    print("PowerFlow V9 - Analyse de calibration (--analyze)")
    print("=" * 60)

    if conn is None:
        print("Aucune donnée disponible (data/v9_forces.db introuvable).")
        return 0

    forces_rows = fetch_all_dicts(conn, "forces_snapshots")
    scenes_rows = fetch_all_dicts(conn, "scenes")

    if not forces_rows:
        print("Aucun snapshot de forces disponible pour l'analyse.")
        return 0

    print("Distribution des forces / amplitude / vitesse / croisements / stale par TF :\n")
    forces_report = analyze_forces(forces_rows)
    for tf in TF_ORDER:
        if tf not in forces_report:
            continue
        r = forces_report[tf]
        print(f"[{tf}] n={r['n_snapshots']}")
        for devise in DEVISES:
            if devise in r["forces"]:
                s = r["forces"][devise]
                print(f"    {devise}: min={s['min']:.1f} max={s['max']:.1f} mean={s['mean']:.1f} stdev={s['stdev']:.1f}")
        amp = r["amplitude"]
        vit = r["vitesse"]
        print(f"    amplitude (max-min) : min={amp['min']} max={amp['max']} mean={amp['mean']}")
        print(f"    vitesse              : min={vit['min']} max={vit['max']} mean={vit['mean']}")
        print(f"    croisements          : {r['croisement_frequence_pct']}%")
        print(f"    stale                : {r['stale_rate_pct']}%")
        print()

    if scenes_rows:
        print("Fréquence des coalitions/antagonismes (couche Scènes) :")
        scenes_report = analyze_scenes(scenes_rows)
        print(f"    scenes avec coalition   : {scenes_report['coalitions_frequence_pct']}%")
        print(f"    scenes avec antagonisme : {scenes_report['antagonismes_frequence_pct']}%")
        print(f"    coalitions / scene (moy): {scenes_report['coalitions_moyenne_par_scene']}")
        print(f"    antagonismes / scene (moy): {scenes_report['antagonismes_moyenne_par_scene']}")
        print()
    else:
        print("Aucune scène disponible pour l'analyse des coalitions/antagonismes.\n")

    print("-" * 60)
    print("Suggestions d'ajustement de seuils (config.py N'EST PAS modifié) :")
    suggestions = suggest_thresholds(forces_rows)
    print(f"  COALITION_THRESHOLD (actuel valeur cf. config.py) -> suggéré : {suggestions['COALITION_THRESHOLD']}")
    print(f"  ANTAGONISM_THRESHOLD                              -> suggéré : {suggestions['ANTAGONISM_THRESHOLD']}")
    print(f"  PLIURE_THRESHOLD                                  -> suggéré : {suggestions['PLIURE_THRESHOLD']}")
    print("  STALE_THRESHOLDS_MS (par TF, p95 des intervalles réels x3) :")
    for tf, value in suggestions["STALE_THRESHOLDS_MS"].items():
        print(f"    {tf:<5}: {value} ms")

    return 0


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Calibration / export / stats - PowerFlow V9")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--analyze", action="store_true", help="Analyser les données et suggérer des seuils")
    group.add_argument("--export", choices=["csv", "json"], help="Exporter toutes les tables (csv ou json)")
    group.add_argument("--stats", action="store_true", help="Afficher les statistiques globales")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.analyze:
            return run_analyze(conn)
        if args.export:
            return run_export(conn, args.export)
        if args.stats:
            return run_stats(conn)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
