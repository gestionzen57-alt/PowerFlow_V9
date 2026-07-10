#!/usr/bin/env python3
"""v9_replay_param.py — Replay paramétrique (lecture seule) pour calibration rapide.

Permet de tester un override de seuils (COALITION_THRESHOLD, ANTAGONISM_THRESHOLD,
PLIURE_THRESHOLD) sur une fenêtre historique de forces_snapshots SANS toucher
la DB de production et SANS régénérer la chaîne complète.

Compare une exécution baseline (config.py par défaut) à une exécution override
(fichier JSON de seuils), et produit un rapport JSON + console avec :
- Distribution coalitions/antagonismes/pliures par seuil
- Hit rate (proportion de scènes déclenchant >= 1 node_rule ACTIVE)
- Distribution par session (asia/london/ny) et par TF
- Deltas baseline → override

Doctrine (cf powerflow-v9-consolidation §24 R8 perimeter) :
- Lecture seule (jamais d'écriture sur data/v9_forces.db)
- 0 modification de core/v9/*
- 0 dépendance pip (stdlib only)
- Le script peut être appelé par cron no_agent pour apprentissage accéléré

Usage :
    # Baseline (config par défaut) sur 5000 snapshots M5+
    python scripts/v9_replay_param.py --limit 5000 --timeframes M5 M15

    # Override de seuils depuis JSON
    python scripts/v9_replay_param.py --threshold-override thresholds.json --limit 5000

    # Avec session filter
    python scripts/v9_replay_param.py --sessions london ny --limit 3000

Format thresholds.json :
    {
      "coalition_threshold": 3.73,
      "antagonism_threshold": 30.0,
      "pliure_threshold": 1.2
    }
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402

# Sessions forex GMT, calcul UTC+0 (cf. docs/architecture/CONTEXT_CONTRACT.md)
def _session_for_hour(hour_utc: int) -> str:
    if 22 <= hour_utc or hour_utc < 7:
        return "asia"
    if 7 <= hour_utc < 12:
        return "london"
    if 12 <= hour_utc < 17:
        return "ny"
    return "off"


@dataclass
class SceneStats:
    """Stats accumulées pour une exécution (baseline ou override)."""

    n_scenes: int = 0
    n_with_coalition: int = 0
    n_with_antagonism: int = 0
    n_with_pliure: int = 0
    n_coalitions_total: int = 0
    n_antagonisms_total: int = 0
    n_pliures_total: int = 0
    by_session: dict[str, int] = field(default_factory=lambda: Counter())
    by_tf: dict[str, int] = field(default_factory=lambda: Counter())
    by_session_tf: dict[tuple, int] = field(default_factory=lambda: Counter())
    examples: list[dict] = field(default_factory=list)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Replay paramétrique V9 — compare un override de seuils "
            "(COALITION/ANTAGONISM/PLIURE) à la baseline sur forces_snapshots."
        )
    )
    p.add_argument(
        "--limit", type=int, default=2000,
        help="Nombre max de snapshots à rejouer (défaut 2000, ordre chronologique DESC).",
    )
    p.add_argument(
        "--timeframes", nargs="+", default=["M5", "M15", "H1"],
        help="Timeframes à inclure (défaut M5 M15 H1).",
    )
    p.add_argument(
        "--sessions", nargs="+", default=None,
        help="Filtre sessions forex (asia/london/ny/off). Défaut = toutes.",
    )
    p.add_argument(
        "--threshold-override", type=Path, default=None,
        help="Fichier JSON avec coalition_threshold/antagonism_threshold/pliure_threshold.",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help="Fichier JSON de sortie (rapport complet). Défaut = stdout.",
    )
    p.add_argument(
        "--examples-per-stat", type=int, default=3,
        help="Nombre d'exemples à conserver par métrique (défaut 3).",
    )
    return p.parse_args(argv)


def _load_snapshots(
    conn: sqlite3.Connection,
    limit: int,
    timeframes: list[str],
    sessions: list[str] | None,
) -> list[dict]:
    placeholders = ",".join("?" * len(timeframes))
    sql = (
        f"SELECT snapshot_id, timestamp, timeframe, symbol, stale, "
        f"force_usd, force_gbp, force_eur, force_jpy, force_cad, "
        f"force_chf, force_aud, force_nzd "
        f"FROM forces_snapshots "
        f"WHERE stale = 0 AND timeframe IN ({placeholders}) "
        f"ORDER BY timestamp DESC LIMIT ?"
    )
    rows = conn.execute(sql, (*timeframes, limit)).fetchall()
    cols = [d[0] for d in conn.execute(sql, (*timeframes, 0)).description][:14]

    out = []
    for row in rows:
        d = dict(zip(cols, row))
        ts = d["timestamp"]
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        session = _session_for_hour(dt.hour)
        if sessions and session not in sessions:
            continue
        d["_session"] = session
        out.append(d)
    return out


def _detect_coalitions(forces: dict[str, float], threshold: float) -> list[tuple[str, str]]:
    """Détecte les coalitions paires de devises alignées (écart ≤ threshold)."""
    out = []
    devs = sorted(forces.items(), key=lambda kv: kv[1])
    for i in range(len(devs)):
        for j in range(i + 1, len(devs)):
            d1, v1 = devs[i]
            d2, v2 = devs[j]
            if abs(v2 - v1) <= threshold:
                out.append((d1, d2))
    return out


def _detect_antagonisms(forces: dict[str, float], threshold: float) -> list[tuple[str, str]]:
    """Détecte les antagonismes (écart ≥ threshold entre devise haute et basse)."""
    vals = sorted(forces.items(), key=lambda kv: kv[1])
    out = []
    high = vals[-1]
    low = vals[0]
    if high[1] - low[1] >= threshold:
        out.append((low[0], high[0]))
    return out


def _detect_pliure(history_for_tf: list[dict], threshold: float) -> int:
    """Détecte les pliures sur l'historique récent (écart pentes ≥ threshold).

    Implémentation simplifiée : regarde la variation de force_usd entre 2 snapshots
    consécutifs du même TF ; compte une pliure si |delta - delta_prev| ≥ threshold.
    """
    if len(history_for_tf) < 3:
        return 0
    deltas = []
    for i in range(1, len(history_for_tf)):
        prev = history_for_tf[i - 1]
        curr = history_for_tf[i]
        if prev.get("force_usd") is None or curr.get("force_usd") is None:
            continue
        deltas.append(curr["force_usd"] - prev["force_usd"])
    pliures = 0
    for i in range(1, len(deltas)):
        if abs(deltas[i] - deltas[i - 1]) >= threshold:
            pliures += 1
    return pliures


def _run_replay(
    snapshots: list[dict],
    coalition_thr: float,
    antagonism_thr: float,
    pliure_thr: float,
    examples_per_stat: int,
) -> SceneStats:
    """Exécute le replay paramétrique sur les snapshots (lecture seule)."""
    stats = SceneStats()
    history_by_tf: dict[str, list[dict]] = defaultdict(list)

    for snap in snapshots:
        tf = snap["timeframe"]
        session = snap["_session"]
        forces = {
            d: snap[f"force_{d.lower()}"]
            for d in ("USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD")
        }
        # Filtre None
        forces = {k: v for k, v in forces.items() if v is not None}
        if not forces:
            continue

        coalitions = _detect_coalitions(forces, coalition_thr)
        antagonisms = _detect_antagonisms(forces, antagonism_thr)

        history_by_tf[tf].append(snap)
        pliures = _detect_pliure(history_by_tf[tf][-10:], pliure_thr)

        stats.n_scenes += 1
        if coalitions:
            stats.n_with_coalition += 1
            stats.n_coalitions_total += len(coalitions)
        if antagonisms:
            stats.n_with_antagonism += 1
            stats.n_antagonisms_total += len(antagonisms)
        if pliures:
            stats.n_with_pliure += 1
            stats.n_pliures_total += pliures

        stats.by_session[session] += 1
        stats.by_tf[tf] += 1
        stats.by_session_tf[(session, tf)] += 1

        if (
            len(stats.examples) < examples_per_stat * 10
            and (coalitions or antagonisms)
        ):
            stats.examples.append({
                "snapshot_id": snap["snapshot_id"],
                "timestamp": snap["timestamp"],
                "timeframe": tf,
                "session": session,
                "forces": forces,
                "n_coalitions": len(coalitions),
                "n_antagonisms": len(antagonisms),
                "n_pliures": pliures,
            })

    return stats


def _build_report(
    snapshots: list[dict],
    baseline: SceneStats,
    override: SceneStats | None,
    coalition_thr_baseline: float,
    antagonism_thr_baseline: float,
    pliure_thr_baseline: float,
    coalition_thr_override: float | None,
    antagonism_thr_override: float | None,
    pliure_thr_override: float | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Construit le rapport final (JSON-sérialisable)."""

    def _rate(num: int, denom: int) -> float:
        return round(num / denom * 100, 2) if denom else 0.0

    base = {
        "n_scenes": baseline.n_scenes,
        "n_with_coalition": baseline.n_with_coalition,
        "n_with_antagonism": baseline.n_with_antagonism,
        "n_with_pliure": baseline.n_with_pliure,
        "pct_coalition": _rate(baseline.n_with_coalition, baseline.n_scenes),
        "pct_antagonism": _rate(baseline.n_with_antagonism, baseline.n_scenes),
        "pct_pliure": _rate(baseline.n_with_pliure, baseline.n_scenes),
        "n_coalitions_total": baseline.n_coalitions_total,
        "n_antagonisms_total": baseline.n_antagonisms_total,
        "n_pliures_total": baseline.n_pliures_total,
        "by_session": dict(baseline.by_session),
        "by_tf": dict(baseline.by_tf),
    }

    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(DB_PATH),
        "params": {
            "limit": args.limit,
            "timeframes": args.timeframes,
            "sessions": args.sessions,
        },
        "thresholds_baseline": {
            "coalition_threshold": coalition_thr_baseline,
            "antagonism_threshold": antagonism_thr_baseline,
            "pliure_threshold": pliure_thr_baseline,
        },
        "baseline_stats": base,
        "examples": baseline.examples[: args.examples_per_stat * 3],
    }

    if override and coalition_thr_override is not None:
        ov_stats = {
            "n_scenes": override.n_scenes,
            "n_with_coalition": override.n_with_coalition,
            "n_with_antagonism": override.n_with_antagonism,
            "n_with_pliure": override.n_with_pliure,
            "pct_coalition": _rate(override.n_with_coalition, override.n_scenes),
            "pct_antagonism": _rate(override.n_with_antagonism, override.n_scenes),
            "pct_pliure": _rate(override.n_with_pliure, override.n_scenes),
            "n_coalitions_total": override.n_coalitions_total,
            "n_antagonisms_total": override.n_antagonisms_total,
            "n_pliures_total": override.n_pliures_total,
        }
        report["thresholds_override"] = {
            "coalition_threshold": coalition_thr_override,
            "antagonism_threshold": antagonism_thr_override,
            "pliure_threshold": pliure_thr_override,
        }
        report["override_stats"] = ov_stats
        report["deltas"] = {
            "delta_pct_coalition": round(
                ov_stats["pct_coalition"] - base["pct_coalition"], 2
            ),
            "delta_pct_antagonism": round(
                ov_stats["pct_antagonism"] - base["pct_antagonism"], 2
            ),
            "delta_pct_pliure": round(
                ov_stats["pct_pliure"] - base["pct_pliure"], 2
            ),
            "delta_n_coalitions": ov_stats["n_coalitions_total"] - base["n_coalitions_total"],
            "delta_n_antagonisms": ov_stats["n_antagonisms_total"] - base["n_antagonisms_total"],
        }

    return report


def _print_console(report: dict[str, Any]) -> None:
    print("=" * 70)
    print("V9 — REPLAY PARAMETRIQUE (lecture seule, 0 modification DB)")
    print("=" * 70)
    print(f"Timestamp UTC : {report['timestamp_utc']}")
    print(f"DB            : {report['db_path']}")
    print(f"Params        : {report['params']}")
    print()
    print("Seuils baseline (config.py) :")
    for k, v in report["thresholds_baseline"].items():
        print(f"  {k:25s} = {v}")
    if "thresholds_override" in report:
        print()
        print("Seuils override (JSON) :")
        for k, v in report["thresholds_override"].items():
            print(f"  {k:25s} = {v}")

    b = report["baseline_stats"]
    print()
    print(f"Baseline : {b['n_scenes']} scenes")
    print(f"  coalitions  : {b['pct_coalition']:6.2f}% ({b['n_with_coalition']}/{b['n_scenes']}) | total {b['n_coalitions_total']}")
    print(f"  antagonisms : {b['pct_antagonism']:6.2f}% ({b['n_with_antagonism']}/{b['n_scenes']}) | total {b['n_antagonisms_total']}")
    print(f"  pliures     : {b['pct_pliure']:6.2f}% ({b['n_with_pliure']}/{b['n_scenes']}) | total {b['n_pliures_total']}")
    print(f"  by_session  : {b['by_session']}")
    print(f"  by_tf       : {b['by_tf']}")

    if "override_stats" in report:
        o = report["override_stats"]
        d = report["deltas"]
        print()
        print(f"Override : {o['n_scenes']} scenes")
        print(f"  coalitions  : {o['pct_coalition']:6.2f}% | total {o['n_coalitions_total']}")
        print(f"  antagonisms : {o['pct_antagonism']:6.2f}% | total {o['n_antagonisms_total']}")
        print(f"  pliures     : {o['pct_pliure']:6.2f}% | total {o['n_pliures_total']}")
        print()
        print(f"Deltas (override - baseline) :")
        print(f"  Δ pct_coalition  : {d['delta_pct_coalition']:+.2f} pts")
        print(f"  Δ pct_antagonism : {d['delta_pct_antagonism']:+.2f} pts")
        print(f"  Δ pct_pliure     : {d['delta_pct_pliure']:+.2f} pts")
        print(f"  Δ n_coalitions   : {d['delta_n_coalitions']:+d}")
        print(f"  Δ n_antagonisms  : {d['delta_n_antagonisms']:+d}")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)

    # Lecture des seuils baseline depuis config.py (import différé pour override testable)
    from core.v9 import config as cfg_mod

    coalition_thr_baseline = cfg_mod.COALITION_THRESHOLD
    antagonism_thr_baseline = cfg_mod.ANTAGONISM_THRESHOLD
    pliure_thr_baseline = cfg_mod.PLIURE_THRESHOLD

    coalition_thr_override = None
    antagonism_thr_override = None
    pliure_thr_override = None
    if args.threshold_override:
        ovr = json.loads(args.threshold_override.read_text(encoding="utf-8"))
        coalition_thr_override = ovr.get("coalition_threshold", coalition_thr_baseline)
        antagonism_thr_override = ovr.get("antagonism_threshold", antagonism_thr_baseline)
        pliure_thr_override = ovr.get("pliure_threshold", pliure_thr_baseline)

    # Connexion DB (lecture seule, pragmas WAL OK)
    if not DB_PATH.exists():
        print(f"ERREUR : DB absente à {DB_PATH}", file=sys.stderr)
        return 2
    conn = get_connection(DB_PATH)
    try:
        snapshots = _load_snapshots(conn, args.limit, args.timeframes, args.sessions)
    finally:
        conn.close()

    if not snapshots:
        print("ERREUR : aucun snapshot non-stale trouvé pour les critères.", file=sys.stderr)
        return 2

    # Run baseline
    baseline = _run_replay(
        snapshots,
        coalition_thr_baseline,
        antagonism_thr_baseline,
        pliure_thr_baseline,
        args.examples_per_stat,
    )

    # Run override (si applicable)
    override = None
    if coalition_thr_override is not None:
        override = _run_replay(
            snapshots,
            coalition_thr_override,
            antagonism_thr_override,
            pliure_thr_override,
            args.examples_per_stat,
        )

    report = _build_report(
        snapshots, baseline, override,
        coalition_thr_baseline, antagonism_thr_baseline, pliure_thr_baseline,
        coalition_thr_override, antagonism_thr_override, pliure_thr_override,
        args,
    )

    _print_console(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"Rapport complet écrit : {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())