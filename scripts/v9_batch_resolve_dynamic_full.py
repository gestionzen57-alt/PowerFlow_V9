#!/usr/bin/env python3
"""v9_batch_resolve_dynamic_full.py — Re-résolution ensembliste TP_SL -> DYNAMIC/SKIPPED.

Brief O1 (2026-07-12, Phase 13.2 -> 13.3). Corrige le bloqueur du batch
précédent (`scripts/v9_batch_resolve_dynamic.py`, 2026-07-11) : celui-ci
faisait un UPDATE individuel par decision_id, colonne qui n'a AUCUN INDEX
en prod malgré la déclaration `UNIQUE` dans `core/v9/decision_db.py`
(schéma jamais migré sur la DB existante — `CREATE TABLE IF NOT EXISTS`
ne rattrape pas une table déjà créée). Chaque UPDATE faisait donc un
SCAN complet des 69 100 lignes de `decisions`. Résultat : seules les
~1 400 décisions les plus anciennes (1105 DYNAMIC + 295 SKIPPED) ont été
persistées avant timeout ; 8 115 sont restées bloquées en
resolution_strategy='TP_SL'. Le rapport JSON produit par ce run
(`BATCH_RESOLVE_DYNAMIC_20260711.json`, 8217 traded/88.5% WR) correspond
en fait à la sortie de l'analyse `v9_analyze_exit_strategies.py`
(hypothétique, jamais persistée) et non à l'état réel de la DB.

Corrections apportées :
1. Création de l'index manquant idx_decisions_decision_id (idempotent).
2. Sélection STRICTE des décisions preparer_entree encore en
   resolution_strategy='TP_SL' (jamais DYNAMIC/SKIPPED déjà résolues —
   idempotent, rejouable sans duplication).
3. Simulation en mémoire (ExitSimulator DYNAMIC) : asie/london/overlap
   -> simulation TP/SL par session ; new_york/after -> SKIPPED direct
   (pas de résolution directionnelle, cf STATE.md Phase 13.2).
4. UN SEUL UPDATE ensembliste (table temporaire + UPDATE ... FROM) au
   lieu de N UPDATE individuels — élimine le scan répété.

Sécurité :
- Dry-run par défaut. --apply exige --backup <dir> (md5_pre.txt présent).
- --make-backup crée le backup MD5 + MANIFEST avant --apply.
- Idempotent : le UPDATE final filtre explicitement
  `decisions.resolution_strategy = 'TP_SL'` -> un re-run sans nouvelle
  décision TP_SL est un no-op.

Usage :
    python scripts/v9_batch_resolve_dynamic_full.py --dry-run
    python scripts/v9_batch_resolve_dynamic_full.py --make-backup \\
        --backup docs/calibration/backups/2026-07-12_resolve_dynamic_full
    python scripts/v9_batch_resolve_dynamic_full.py --apply \\
        --backup docs/calibration/backups/2026-07-12_resolve_dynamic_full
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.exit_simulator import ExitSimulator, infer_session_from_hour  # noqa: E402

DEFAULT_REPORT_PATH = ROOT_DIR / "docs" / "reports" / "BATCH_RESOLVE_DYNAMIC_FULL_20260712.json"

IDX_DECISION_ID_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_decision_id "
    "ON decisions (decision_id)"
)
IDX_FORCES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_forces_symbol_timeframe_timestamp "
    "ON forces_snapshots (symbol, timeframe, timestamp)"
)

SKIP_SESSIONS = ("new_york", "after")
HORIZON_HOURS = 4
SPREAD_PIPS = 0.5


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Path, timeout: int = 120) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"DB introuvable : {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _verify_backup(backup_dir: Path) -> None:
    """Vérifie que le dossier backup contient md5_pre.txt non vide (R8)."""
    md5_file = backup_dir / "md5_pre.txt"
    if not md5_file.exists():
        raise FileNotFoundError(
            f"Backup MD5 introuvable : {md5_file}. "
            f"Lance d'abord avec --make-backup --backup {backup_dir}."
        )
    lines = [ln for ln in md5_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{md5_file} est vide — backup incomplet (aucun MD5).")


def make_backup(db_path: Path, backup_dir: Path) -> str:
    """Backup MD5 + MANIFEST (R8) avant toute modification de la DB."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    md5 = hashlib.md5(db_path.read_bytes()).hexdigest()
    (backup_dir / "md5_pre.txt").write_text(md5, encoding="utf-8")
    (backup_dir / "MANIFEST.md").write_text(
        "# Backup pré-batch — Brief O1 (2026-07-12)\n\n"
        f"- Fichier : `{db_path}`\n"
        f"- MD5 (avant modification) : `{md5}`\n"
        f"- Taille : {db_path.stat().st_size / (1024 * 1024):.1f} MB\n"
        "- Contexte : re-résolution des 8115 décisions preparer_entree "
        "bloquées en resolution_strategy='TP_SL' vers DYNAMIC/SKIPPED, "
        "création de l'index idx_decisions_decision_id (manquant en prod), "
        "régénération de la table principle_scores sur les nouveaux labels.\n"
        "- Référence : workspace/perplexity/memory/DECISIONS_LOG.md "
        "§2026-07-12 Brief O1.\n",
        encoding="utf-8",
    )
    return md5


def _ensure_indices(conn: sqlite3.Connection) -> None:
    """Idempotent. L'index sur decision_id est LA correction du bloqueur."""
    conn.execute(IDX_DECISION_ID_SQL)
    conn.execute(IDX_FORCES_SQL)
    conn.commit()


def _fetch_target_decisions(conn: sqlite3.Connection) -> list[tuple]:
    """Décisions preparer_entree STRICTEMENT en resolution_strategy='TP_SL'.
    Ne retouche jamais une décision déjà DYNAMIC ou SKIPPED (idempotence)."""
    return conn.execute(
        """
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe, direction
        FROM decisions
        WHERE action = 'preparer_entree'
          AND resolution_strategy = 'TP_SL'
          AND timestamp IS NOT NULL
        ORDER BY timestamp ASC
        """
    ).fetchall()


def _load_price_context(
    conn: sqlite3.Connection, rows: list[tuple]
) -> tuple[dict[str, float], dict[str, list[tuple[str, float]]]]:
    """Charge en mémoire les mids d'entrée + tous les prix futurs nécessaires
    en 2 requêtes bulk (au lieu d'une requête par décision)."""
    snap_ids = list({r[1] for r in rows if r[1]})
    entry_mids: dict[str, float] = {}
    if snap_ids:
        ph = ",".join("?" for _ in snap_ids)
        for sid, mid in conn.execute(
            f"SELECT snapshot_id, mid FROM forces_snapshots "
            f"WHERE snapshot_id IN ({ph}) AND mid IS NOT NULL",
            snap_ids,
        ):
            entry_mids[sid] = float(mid)

    timestamps = [r[2] for r in rows if r[2]]
    future: dict[str, list[tuple[str, float]]] = {}
    if timestamps:
        min_ts, max_ts = min(timestamps), max(timestamps)
        max_end = (
            datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
            + timedelta(hours=HORIZON_HOURS)
        ).isoformat()
        for sym, tf, ts, mid in conn.execute(
            """
            SELECT symbol, timeframe, timestamp, mid FROM forces_snapshots
            WHERE timestamp > ? AND timestamp <= ? AND mid IS NOT NULL
            ORDER BY symbol, timeframe, timestamp
            """,
            (min_ts, max_end),
        ):
            future.setdefault(f"{sym}|{tf}", []).append((ts, float(mid)))
    return entry_mids, future


def simulate_all(
    rows: list[tuple],
    entry_mids: dict[str, float],
    future: dict[str, list[tuple[str, float]]],
) -> tuple[list[dict], dict[str, dict[str, Any]]]:
    """Simule chaque décision cible. Retourne (résultats, stats par session).
    N'écrit rien — pure fonction pour être testable et réutilisable en dry-run."""
    sim = ExitSimulator(strategy="DYNAMIC", spread_pips=SPREAD_PIPS)
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)
    results: list[dict] = []
    per_session: dict[str, dict[str, Any]] = {}

    for did, sid, ts, sym, tf, direc in rows:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        entry = entry_mids.get(sid)
        if entry is None:
            continue

        session = infer_session_from_hour(dt.hour)
        bucket = per_session.setdefault(
            session, {"n": 0, "wins": 0, "losses": 0, "skipped": 0, "pips": 0.0}
        )
        bucket["n"] += 1

        if session in SKIP_SESSIONS:
            bucket["skipped"] += 1
            results.append({
                "decision_id": did, "is_win": 0, "pips": 0.0,
                "resolution_strategy": "SKIPPED",
                "resolution_details": json.dumps(
                    {"exit_reason": f"skipped_{session}", "session": session}
                ),
                "resolved_at": now_iso,
            })
            continue

        end_dt = dt + timedelta(hours=HORIZON_HOURS)
        if end_dt > now_dt:
            end_dt = now_dt
        end_iso = end_dt.isoformat()

        key = f"{sym}|{tf}"
        mids = [p[1] for p in future.get(key, []) if p[0] > ts and p[0] <= end_iso]
        if len(mids) < 3 and tf != "M15":
            fmids = [
                p[1] for p in future.get(f"{sym}|M15", [])
                if p[0] > ts and p[0] <= end_iso
            ]
            if len(fmids) > len(mids):
                mids = fmids

        if not mids:
            bucket["skipped"] += 1
            results.append({
                "decision_id": did, "is_win": 0, "pips": 0.0,
                "resolution_strategy": "SKIPPED",
                "resolution_details": json.dumps(
                    {"exit_reason": "no_data", "session": session}
                ),
                "resolved_at": now_iso,
            })
            continue

        res = sim.simulate(entry, direc, mids, session_marche=session)
        if res.is_win:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1
        bucket["pips"] += res.pips
        results.append({
            "decision_id": did, "is_win": res.is_win, "pips": res.pips,
            "resolution_strategy": "DYNAMIC",
            "resolution_details": json.dumps({
                "exit_reason": res.exit_reason,
                "exit_price": res.exit_price,
                "entry_price": res.entry_price,
                "max_favorable": res.max_favorable,
                "max_adverse": res.max_adverse,
                "bars_held": res.bars_held,
                "n_future_prices": len(mids),
                "strategy": "DYNAMIC",
                "session": session,
            }),
            "resolved_at": now_iso,
        })

    return results, per_session


def apply_results(conn: sqlite3.Connection, results: list[dict]) -> int:
    """UPDATE ensembliste : table temporaire + UN SEUL UPDATE ... FROM.
    Idempotent : le WHERE filtre resolution_strategy='TP_SL', donc un
    re-run sans décision TP_SL restante est un no-op (rowcount=0)."""
    conn.execute("DROP TABLE IF EXISTS _o1_resultats")
    conn.execute(
        """
        CREATE TEMP TABLE _o1_resultats (
            decision_id TEXT PRIMARY KEY,
            is_win INTEGER,
            pips REAL,
            resolution_strategy TEXT,
            resolution_details TEXT,
            resolved_at TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO _o1_resultats VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                r["decision_id"], r["is_win"], r["pips"],
                r["resolution_strategy"], r["resolution_details"], r["resolved_at"],
            )
            for r in results
        ],
    )
    cur = conn.execute(
        """
        UPDATE decisions
        SET is_win = _o1_resultats.is_win,
            resolution_pips = _o1_resultats.pips,
            resolution_strategy = _o1_resultats.resolution_strategy,
            resolution_details = _o1_resultats.resolution_details,
            resolved_at = _o1_resultats.resolved_at
        FROM _o1_resultats
        WHERE decisions.decision_id = _o1_resultats.decision_id
          AND decisions.resolution_strategy = 'TP_SL'
        """
    )
    n = cur.rowcount
    conn.execute("DROP TABLE IF EXISTS _o1_resultats")
    return n


def build_report(
    results: list[dict], per_session: dict[str, dict[str, Any]], applied: int | None,
) -> dict[str, Any]:
    n_dynamic = sum(1 for r in results if r["resolution_strategy"] == "DYNAMIC")
    n_skipped = sum(1 for r in results if r["resolution_strategy"] == "SKIPPED")
    n_wins = sum(1 for r in results if r["resolution_strategy"] == "DYNAMIC" and r["is_win"])
    n_losses = n_dynamic - n_wins
    total_pips = sum(r["pips"] for r in results if r["resolution_strategy"] == "DYNAMIC")

    sessions_report = {}
    for session, b in per_session.items():
        traded = b["wins"] + b["losses"]
        sessions_report[session] = {
            "n_decisions": b["n"],
            "n_traded": traded,
            "n_skipped": b["skipped"],
            "win_rate_pct": round(b["wins"] / max(1, traded) * 100, 1) if traded else 0.0,
            "total_pips": round(b["pips"], 1),
            "avg_pips": round(b["pips"] / max(1, traded), 1) if traded else 0.0,
        }

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "brief": "O1",
        "strategy": "DYNAMIC",
        "n_target_decisions": len(results),
        "n_dynamic": n_dynamic,
        "n_skipped": n_skipped,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate_pct": round(n_wins / max(1, n_dynamic) * 100, 1),
        "total_pips": round(total_pips, 1),
        "avg_pips": round(total_pips / max(1, n_dynamic), 1),
        "by_session": sessions_report,
        "n_rows_applied": applied,
    }


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Re-résolution ensembliste TP_SL -> DYNAMIC/SKIPPED (Brief O1)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--make-backup", action="store_true",
                         help="Crée le backup MD5+MANIFEST dans --backup avant --apply")
    parser.add_argument("--backup", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    if args.make_backup:
        if not args.backup:
            print("ERREUR: --make-backup exige --backup <dir>.", file=sys.stderr)
            return 2
        md5 = make_backup(args.db, args.backup)
        print(f"[OK ] Backup MD5 créé : {args.backup}/md5_pre.txt ({md5})")
        if not args.apply:
            return 0

    if args.apply:
        if not args.backup:
            print("ERREUR: --apply exige --backup <dir>.", file=sys.stderr)
            return 2
        try:
            _verify_backup(args.backup)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERREUR backup: {e}", file=sys.stderr)
            return 2
        print(f"[OK ] Backup MD5 vérifié : {args.backup}/md5_pre.txt")
    else:
        print("[.. ] Mode : DRY-RUN (lecture seule, rien n'est modifié)")

    conn = _connect(args.db)
    try:
        _ensure_indices(conn)
        rows = _fetch_target_decisions(conn)
        print(f"[.. ] {len(rows)} décisions cibles (action=preparer_entree, resolution_strategy=TP_SL)")
        if not rows:
            print("[OK ] Rien à faire — 0 décision TP_SL restante (idempotent, déjà appliqué).")
            return 0

        entry_mids, future = _load_price_context(conn, rows)
        print(f"[.. ] {len(entry_mids)} mids d'entrée, "
              f"{sum(len(v) for v in future.values())} prix futurs chargés")

        results, per_session = simulate_all(rows, entry_mids, future)
        n_dynamic = sum(1 for r in results if r["resolution_strategy"] == "DYNAMIC")
        n_skipped = sum(1 for r in results if r["resolution_strategy"] == "SKIPPED")
        print(f"[.. ] Simulé : {n_dynamic} DYNAMIC, {n_skipped} SKIPPED "
              f"(sur {len(results)}/{len(rows)} décisions traitées)")

        applied = None
        if args.apply:
            conn.execute("BEGIN IMMEDIATE")
            try:
                applied = apply_results(conn, results)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            print(f"[OK ] {applied} lignes mises à jour en une seule transaction ensembliste")

            remaining = conn.execute(
                "SELECT COUNT(*) FROM decisions "
                "WHERE action='preparer_entree' AND resolution_strategy='TP_SL'"
            ).fetchone()[0]
            print(f"[.. ] Décisions TP_SL restantes après apply : {remaining}")
            if remaining != 0:
                print("[!! ] ATTENTION : des décisions TP_SL subsistent — vérifier avant de clôturer.",
                      file=sys.stderr)

        report = build_report(results, per_session, applied)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK ] Rapport écrit : {args.report}")

        if not args.apply:
            print()
            print("Aucun changement appliqué (dry-run). Relancer avec --apply --backup <dir>.")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
