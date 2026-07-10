#!/usr/bin/env python3
"""v9_recalibrate_arbiter.py — Recalibrage Phase 13 des pondérations arbiter (lecture seule).

Analyse le hit rate des décisions résolues (is_win IS NOT NULL) par
(zone_type, session) et propose des ajustements de pondération pour
l'arbiter (cf. core/v9/arbiter.py lignes 240-263).

NE MODIFIE PAS le code (R8 : aucune écriture sur core/v9/*). Produit
un rapport avec suggestions que Søn valide manuellement avant commit.

Doctrine :
- R8 : lecture seule sur DB, 0 modif core/v9/arbiter.py
- R18 : 0 LLM (calcul stdlib pur)
- R25' : propositions jamais appliquées automatiquement, CEO requis
- R30 : seuil HR ≥ 60% sur ≥ 50 décl. pour valider une pondération

Usage :
    python scripts/v9_recalibrate_arbiter.py
    python scripts/v9_recalibrate_arbiter.py --output docs/reports/ARBITER_RECAL_<date>.json
    python scripts/v9_recalibrate_arbiter.py --min-decisions 50  # filtre statistical significance
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402

# Pondérations hardcodées actuelles dans arbiter.py (lecture seule, référence)
CURRENT_WEIGHTS = {
    "zone_type": {
        "naissance": +5,
        "continuation": -2,
    },
    "session": {
        "asie": -3,
        "after": -3,
    },
}


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Recalibrage arbiter V9 (Phase 13) — analyse hit rate par "
            "(zone_type, session) et propose ajustements (lecture seule)."
        )
    )
    p.add_argument(
        "--min-decisions", type=int, default=50,
        help="Min décisions résolues par (zone_type, session) pour proposer un ajustement (R30).",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help="Fichier JSON de sortie pour le rapport complet.",
    )
    return p.parse_args(argv)


def _load_resolved_with_context(conn: sqlite3.Connection) -> list[dict]:
    """Charge les décisions résolues avec zone_type/session.

    Le contexte est zlib-compressé (cf. decision_db.py). On décompresse et
    on extrait :
    - zone_type depuis scene.zone_json.structure (mapping direct)
    - session depuis le timestamp UTC
    """
    rows = conn.execute("""
        SELECT d.decision_id,
               d.timestamp,
               d.action,
               d.is_win,
               d.resolution_pips,
               d.contexte_complet_json
        FROM decisions d
        WHERE d.is_win IS NOT NULL
          AND d.action = 'preparer_entree'
          AND d.contexte_complet_json IS NOT NULL
          AND d.timestamp > '2026-07-07'
        ORDER BY d.timestamp DESC
    """).fetchall()

    # Mapping structure zone_json → zone_type (cf. core/v9/zone_db.py)
    ZONE_TYPE_MAP = {
        "zone neutre": "neutre",
        "zone accumulation": "accumulation",
        "zone distribution": "distribution",
        "zone extension": "extension",
        "zone compression": "compression",
        "zone naissance": "naissance",
    }

    out = []
    for row in rows:
        try:
            data = row[5]
            if isinstance(data, bytes):
                ctx_bytes = data
            else:
                ctx_bytes = data.encode("latin-1") if isinstance(data, str) else data
            try:
                ctx = json.loads(zlib.decompress(ctx_bytes))
            except (zlib.error, json.JSONDecodeError):
                # Pas compressé (legacy)
                if isinstance(data, str):
                    ctx = json.loads(data)
                else:
                    continue

            # Zone type depuis scene.zone_json.structure
            zone_json_raw = ctx.get("scene", {}).get("zone_json", "{}")
            try:
                zone_json = json.loads(zone_json_raw) if isinstance(zone_json_raw, str) else zone_json_raw
            except json.JSONDecodeError:
                zone_json = {}
            structure = zone_json.get("structure", "")
            zone_type = ZONE_TYPE_MAP.get(structure, structure or None)

            # Session depuis timestamp UTC
            ts_str = row[1] or ""
            session = None
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                h = ts.hour
                if 22 <= h or h < 7:
                    session = "asie"
                elif 7 <= h < 12:
                    session = "london"
                elif 12 <= h < 17:
                    session = "ny"
                else:
                    session = "after"
            except (ValueError, AttributeError):
                pass

            out.append({
                "decision_id": row[0],
                "timestamp": row[1],
                "is_win": bool(row[3]),
                "pips": row[4],
                "zone_type": zone_type,
                "session": session,
            })
        except Exception:
            continue
    return out


def _aggregate(decisions: list[dict]) -> dict:
    """Agrège par (zone_type, session)."""
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "losses": 0, "pips_total": 0.0}
    )
    for d in decisions:
        zt = d["zone_type"] or "unknown"
        sess = d["session"] or "unknown"
        k = (zt, sess)
        agg[k]["n"] += 1
        if d["is_win"]:
            agg[k]["wins"] += 1
        else:
            agg[k]["losses"] += 1
        agg[k]["pips_total"] += d["pips"] or 0.0
    return agg


def _propose_adjustment(
    bucket: dict,
    current_zt_weight: int | None,
    current_session_weight: int | None,
    min_decisions: int,
) -> dict:
    """Propose un ajustement de pondération basé sur HR observé vs R30 (60%)."""
    n = bucket["n"]
    if n < min_decisions:
        return {
            "proposed": False,
            "reason": f"n={n} < min_decisions={min_decisions} (significance R30)",
        }
    hr_pct = round(bucket["wins"] / n * 100, 1)
    avg_pips = round(bucket["pips_total"] / n, 2) if n else 0.0

    # Si HR < 60% → réduire le boost (ou augmenter la pénalité)
    # Si HR > 80% → augmenter le boost (diminuer la pénalité)
    # Linéaire entre les bornes
    target_hr = 75.0
    delta_hr = hr_pct - target_hr
    proposed_delta = round(-delta_hr * 0.3)  # 1pt delta HR → 0.3pt poids

    # Bornes de sécurité : ±15 max (cohérent avec arbiter.py)
    proposed_delta = max(-15, min(15, proposed_delta))

    return {
        "proposed": True,
        "n": n,
        "wins": bucket["wins"],
        "losses": bucket["losses"],
        "hr_pct": hr_pct,
        "avg_pips": avg_pips,
        "current_weight": None,  # sera rempli par caller
        "proposed_delta": proposed_delta,
        "rationale": (
            f"HR={hr_pct}% vs target {target_hr}% → delta={proposed_delta:+d} pts "
            f"(avg_pips={avg_pips:+.1f})"
        ),
    }


def _build_report(decisions: list[dict], min_decisions: int) -> dict:
    """Construit le rapport complet."""
    agg = _aggregate(decisions)

    buckets = []
    for (zt, sess), b in sorted(agg.items()):
        current_zt = CURRENT_WEIGHTS["zone_type"].get(zt)
        current_sess = CURRENT_WEIGHTS["session"].get(sess)
        proposal = _propose_adjustment(b, current_zt, current_sess, min_decisions)
        proposal["zone_type"] = zt
        proposal["session"] = sess
        proposal["current_zone_type_weight"] = current_zt
        proposal["current_session_weight"] = current_sess
        buckets.append(proposal)

    n_total = len(decisions)
    n_won = sum(1 for d in decisions if d["is_win"])
    wr_global = round(n_won / n_total * 100, 2) if n_total else 0.0

    n_significant = sum(1 for b in buckets if b.get("proposed"))
    n_proposals = sum(
        1 for b in buckets
        if b.get("proposed") and abs(b.get("proposed_delta", 0)) >= 2
    )

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(DB_PATH),
        "n_total_decisions": n_total,
        "n_won": n_won,
        "wr_global_pct": wr_global,
        "min_decisions_threshold": min_decisions,
        "n_buckets_significant": n_significant,
        "n_proposals": n_proposals,
        "current_weights_reference": CURRENT_WEIGHTS,
        "buckets": buckets,
    }


def _print_console(report: dict) -> None:
    print("=" * 70)
    print("V9 — RECALIBRAGE ARBITER (Phase 13, lecture seule)")
    print("=" * 70)
    print(f"Timestamp UTC   : {report['timestamp_utc']}")
    print(f"DB              : {report['db_path']}")
    print(f"Décisions       : {report['n_total_decisions']} résolues")
    print(f"WR global       : {report['wr_global_pct']}%")
    print(f"Min décisions   : {report['min_decisions_threshold']} (R30)")
    print(f"Buckets significatifs : {report['n_buckets_significant']}")
    print(f"Proposals ≥2pts       : {report['n_proposals']}")
    print()
    print("Pondérations actuelles (core/v9/arbiter.py) :")
    print(f"  zone_type.naissance    = {CURRENT_WEIGHTS['zone_type']['naissance']:+d}")
    print(f"  zone_type.continuation = {CURRENT_WEIGHTS['zone_type']['continuation']:+d}")
    print(f"  session.asie           = {CURRENT_WEIGHTS['session']['asie']:+d}")
    print(f"  session.after          = {CURRENT_WEIGHTS['session']['after']:+d}")
    print()
    print("Propositions par (zone_type, session) :")
    for b in report["buckets"]:
        if not b.get("proposed"):
            status = f"SKIP (n={b.get('n', 0)} < {report['min_decisions_threshold']})"
            print(f"  ({b['zone_type']:14s}, {b['session']:8s}) → {status}")
            continue
        marker = " ★ APPLY" if abs(b.get("proposed_delta", 0)) >= 2 else ""
        print(
            f"  ({b['zone_type']:14s}, {b['session']:8s}) "
            f"n={b['n']:4d} HR={b['hr_pct']:5.1f}% "
            f"avg_pips={b['avg_pips']:+6.2f} "
            f"Δ_weight={b['proposed_delta']:+d}{marker}"
        )


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)

    if not DB_PATH.exists():
        print(f"ERREUR : DB absente à {DB_PATH}", file=sys.stderr)
        return 2

    conn = get_connection(DB_PATH)
    try:
        decisions = _load_resolved_with_context(conn)
    finally:
        conn.close()

    if not decisions:
        print("Aucune décision résolue avec contexte zone_type — pas de recalibrage possible.", file=sys.stderr)
        return 1

    report = _build_report(decisions, args.min_decisions)
    _print_console(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"Rapport complet écrit : {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())