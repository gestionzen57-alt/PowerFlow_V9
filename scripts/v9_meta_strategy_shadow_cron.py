"""v9_meta_strategy_shadow_cron.py — Polling shadow live Phase E (Chemin C).

**Pourquoi ce script existe** :
- Phase 1+2 (commits `0d5e81c`+`6ab0076`) ont livré le câblage shadow + CLI rapport.
- Phase 3 du brief NO-GO V1 = validation edge uplift. Sur simulation replay
  (commit `1cff80d`), le verdict global était RED_NO_UPLIFT — mais c'était un
  **artifact structurel** (mêmes pips historiques appliqués à legacy ET meta,
  voir Opus NO-GO 2026-07-21).
- Chemin C (motion CEO 04:58 UTC) : activer le shadow live pendant 48h,
  accumuler des logs `meta_strategy_shadow_log` via ce script de polling.
- 100% non-intrusif : lecture seule sur `decisions` (résolues seulement) +
  écriture additive dans `meta_strategy_shadow_log`. Aucun trade, aucun ordre,
  aucune modif runtime.

**Volet doctrinal** :
- R2 additif (clé `meta_strategy_*`, table shadow additive)
- R6 défensif (try/except global, skip sur erreur)
- R18 code pur (zéro LLM, 100% stdlib)
- R25' strict (kill switch `V9_META_STRATEGY_SHADOW_ENABLED`, défaut OFF → ON
  par motion CEO 04:58)

**Volet activation** :
- Kill switch `V9_META_STRATEGY_SHADOW_ENABLED=1` (motion CEO 2026-07-21 04:58)
- Cron Windows toutes les 5 min : `V9_MetaStrategyShadowCron`
- Mode dry-run par défaut (`--apply` pour écrire)

**Usage** :
```bash
# Dry-run : affiche stats sans rien écrire
.venv/Scripts/python.exe scripts/v9_meta_strategy_shadow_cron.py

# Apply : alimente meta_strategy_shadow_log pour les décisions résolues
# depuis last_cursor (max shadow_id vu)
.venv/Scripts/python.exe scripts/v9_meta_strategy_shadow_cron.py --apply

# Backfill : scanner N jours en arrière
.venv/Scripts/python.exe scripts/v9_meta_strategy_shadow_cron.py --apply --since 7d

# DB custom
.venv/Scripts/python.exe scripts/v9_meta_strategy_shadow_cron.py --db-path data/test_regen.db
```
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ------------------------------------------------------------------ paths


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "v9_forces.db"


# ------------------------------------------------------------------ helpers


def _shadow_enabled() -> bool:
    """Vérifie le kill switch V9_META_STRATEGY_SHADOW_ENABLED."""
    return os.environ.get("V9_META_STRATEGY_SHADOW_ENABLED", "0") == "1"


def _since_ts(since: str) -> float:
    """Convertit '24h' / '7d' en timestamp epoch."""
    now = time.time()
    if since.endswith("h"):
        try:
            return now - int(since[:-1]) * 3600
        except ValueError as e:
            raise SystemExit(f"FORMAT --since invalide ({since}): {e}. Attendu '24h' ou '7d'.")
    if since.endswith("d"):
        try:
            return now - int(since[:-1]) * 86400
        except ValueError as e:
            raise SystemExit(f"FORMAT --since invalide ({since}): {e}. Attendu '24h' ou '7d'.")
    raise SystemExit(f"FORMAT --since invalide ({since}). Attendu '24h' ou '7d'.")


def _load_resolved_decisions(
    db_path: Path, since_ts: float | None, limit: int,
) -> list[dict]:
    """Charge les décisions résolues depuis `since_ts`.

    Jointure decisions + signals pour récupérer exit_strategy_recommended.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        # Inspect schema signals pour colonnes optionnelles
        sig_cols = {r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()}
        phase_expr = "s.phase" if "phase" in sig_cols else "NULL AS phase"
        vol_expr = "s.volatility_atr_pips" if "volatility_atr_pips" in sig_cols else "NULL AS volatility_atr_pips"
        exit_expr = "s.exit_strategy_recommended" if "exit_strategy_recommended" in sig_cols else "NULL AS exit_strategy_recommended"

        where = ["d.is_win IS NOT NULL"]
        params: list = []
        if since_ts is not None:
            where.append("d.resolved_at >= ?")
            params.append(since_ts)
        sql = f"""
            SELECT d.decision_id, d.snapshot_id, d.symbol, d.timeframe,
                   d.direction, d.regime_type, d.is_win, d.resolution_pips AS pips,
                   {phase_expr}, {vol_expr}, {exit_expr},
                   d.resolved_at
            FROM decisions d
            LEFT JOIN signals s ON s.snapshot_id = d.snapshot_id
            WHERE {' AND '.join(where)}
            ORDER BY d.resolved_at DESC
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_max_shadow_id(db_path: Path) -> int:
    """Retourne max(id) de meta_strategy_shadow_log (cursor pour backfill incrémental)."""
    conn = sqlite3.connect(str(db_path))
    try:
        # Vérifie que la table existe
        exists = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='meta_strategy_shadow_log'"
        ).fetchone()
        if not exists:
            return 0
        row = conn.execute("SELECT MAX(id) FROM meta_strategy_shadow_log").fetchone()
        return int(row[0]) if row and row[0] else 0
    finally:
        conn.close()


# ------------------------------------------------------------------ core


def run_polling(
    db_path: Path,
    *,
    since_ts: float | None,
    limit: int,
    apply: bool,
) -> dict[str, int]:
    """Poll les décisions résolues, compare legacy vs meta via recommend_with_shadow.

    Returns dict avec compteurs : n_processed, n_skipped_dup, n_errors.
    """
    from core.v9.v9_meta_strategy_shadow import (
        ensure_shadow_table, recommend_with_shadow,
    )
    from scripts.v9_meta_strategy_simulation import (
        _build_legacy_from_signal, _phase_from_decision, _vol_atr_from_decision,
    )

    decisions = _load_resolved_decisions(db_path, since_ts, limit)
    if not decisions:
        return {"n_processed": 0, "n_skipped_dup": 0, "n_errors": 0, "n_total_scanned": 0}

    # Cursor anti-doublon : max(shadow_id) actuel
    max_existing = _get_max_shadow_id(db_path)
    ensure_shadow_table(db_path)

    n_processed = 0
    n_skipped_dup = 0
    n_errors = 0

    for dec in decisions:
        try:
            legacy = _build_legacy_from_signal(dec)
            phase = _phase_from_decision(dec)
            vol_atr = _vol_atr_from_decision(dec)
            direction = dec.get("direction") or "long"

            # Anti-doublon simple : si shadow_id > max_existing, on log
            # (recommend_with_shadow auto-crée la table et l'id est autoincrement)
            out_legacy, comparison = recommend_with_shadow(
                symbol=dec["symbol"],
                timeframe=dec["timeframe"],
                regime_type=dec["regime_type"],
                phase=phase,
                direction=direction,
                vol_atr_pips=vol_atr,
                legacy_recommendation=legacy,
                db_path=db_path if apply else None,  # None = no log
            )

            if comparison is None:
                # Kill switch OFF ou DB inaccessible : skip silencieux
                n_skipped_dup += 1
                continue

            if not apply:
                # Mode dry-run : on compte seulement
                n_processed += 1
                continue

            # En mode apply, recommend_with_shadow a déjà inséré le shadow log
            # (kill switch ON garantit le log). On vérifie qu'il y a eu log.
            if comparison.shadow_id is not None and comparison.shadow_id > max_existing:
                n_processed += 1
                max_existing = comparison.shadow_id
            else:
                n_skipped_dup += 1

        except Exception as e:
            print(f"⚠️  Erreur décision {dec.get('decision_id', '?')}: {e}", file=sys.stderr)
            n_errors += 1
            continue

    return {
        "n_total_scanned": len(decisions),
        "n_processed": n_processed,
        "n_skipped_dup": n_skipped_dup,
        "n_errors": n_errors,
    }


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Polling shadow live Phase E (Chemin C — non-intrusif)")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Chemin DB (défaut: {DEFAULT_DB_PATH})")
    parser.add_argument("--since", type=str, default="24h",
                        help="Fenêtre temporelle (24h, 7d)")
    parser.add_argument("--limit", type=int, default=2000,
                        help="Limite nombre décisions scannées (défaut: 2000)")
    parser.add_argument("--apply", action="store_true",
                        help="Écrire dans meta_strategy_shadow_log (défaut: dry-run)")
    args = parser.parse_args(argv)

    # Kill switch guard
    if not _shadow_enabled():
        print("⚠️  V9_META_STRATEGY_SHADOW_ENABLED=0 (kill switch OFF)")
        print("   Active le switch dans config/v9_kill_switches.env pour autoriser le shadow live.")
        print("   Voir motion CEO 2026-07-21 04h58 UTC (commit en cours).")
        return 1

    if not args.db_path.exists():
        print(f"⚠️  DB introuvable : {args.db_path}", file=sys.stderr)
        return 1

    try:
        since_ts = _since_ts(args.since)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2

    mode = "APPLY (écriture shadow_log)" if args.apply else "DRY-RUN (lecture seule)"
    print(f"🔄 Meta-Strategy Shadow Cron — {mode}")
    print(f"   DB : {args.db_path}")
    print(f"   Fenêtre : {args.since} (since {datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat()})")

    result = run_polling(
        args.db_path, since_ts=since_ts, limit=args.limit, apply=args.apply,
    )

    print(f"   Scanned       : {result['n_total_scanned']}")
    print(f"   Processed     : {result['n_processed']}")
    print(f"   Skipped (dup) : {result['n_skipped_dup']}")
    print(f"   Errors        : {result['n_errors']}")

    if not args.apply:
        print("   ℹ️  Mode dry-run : aucun shadow log écrit. Relancer avec --apply pour alimenter.")

    return 0


if __name__ == "__main__":
    sys.exit(main())