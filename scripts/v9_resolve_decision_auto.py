"""v9_resolve_decision_auto.py — Résolution automatique WIN/LOSS prix-based (Phase 9.10).

Boucle le data flow WIN/LOSS de la V9. Pour chaque décision
`action='preparer_entree'` avec `is_win=NULL` et `timestamp < now - horizon`,
calcule le résultat via les prix MFE/MAE sur la fenêtre d'observation
suivante, et pose `is_win`, `resolution_pips`, `resolved_at`.

Doctrine (cf DECISIONS_LOG §Phase 9.10) :
- Zéro exécution d'ordre — on ne trade PAS, on simule le résultat post-trade
  à partir des prix historiques disponibles dans forces_snapshots.
- Dry-run par défaut, --apply exige --backup <dir>.
- Transaction unique, idempotent (re-run = no-op si déjà résolu).
- Pas de LLM dans la boucle (Règle 18 préservée).
- `is_win = 1` si MFE > 0 (haussière : prix monte ; baissière : prix baisse),
  `is_win = 0` sinon. Pas de seuil de rentabilité — la résolution brute est
  le signal de calibration, le seuillage se fera dans le R30 / Phase 13.
- Pips = MFE * 10000 (convention GBPUSD 4 décimales).

Usage :
    # Dry-run (lecture seule, ne modifie rien)
    python scripts/v9_resolve_decision_auto.py --dry-run

    # Application réelle (après backup MD5)
    python scripts/v9_resolve_decision_auto.py --apply \\
        --backup backups/2026-07-08_pre_resolve/

    # Custom horizon (défaut 4h) + skip resolutions si prix futurs absents
    python scripts/v9_resolve_decision_auto.py --apply \\
        --horizon-hours 2 --skip-no-future-prices

    # Filtrer sur symbole / TF
    python scripts/v9_resolve_decision_auto.py --apply \\
        --symbol GBPUSD --timeframe M15

Sécurité :
- Dry-run par défaut (rien n'est modifié).
- --apply exige --backup <dir> (le dossier doit contenir md5_pre.txt).
- Transaction unique BEGIN IMMEDIATE ... COMMIT/ROLLBACK.
- Skip automatique des décisions sans prix futur dans la fenêtre (skip_no_future).
- Idempotent : un re-run sur décision déjà résolue ne change rien (vérif
  resolved_at IS NULL).
"""

from __future__ import annotations

import argparse
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
from core.v9.db_schema import get_connection  # noqa: E402

# Horizon d'observation post-décision (défaut 4h, cohérent horizon court_terme).
DEFAULT_HORIZON_HOURS = 4
# Convention pips GBPUSD (4 décimales).
PIPS_MULTIPLIER = 10000


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Path) -> sqlite3.Connection:
    """Connexion sqlite3 (sans WAL — incompatible avec VACUUM, mais on ne
    fait pas de VACUUM ici, on veut juste écrire). Pragmas alignés sur
    db_schema.get_connection. Row factory = sqlite3.Row par défaut pour
    accès par clé dans toutes les requêtes."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB introuvable : {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    return conn


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    """Parse ISO8601 UTC ('Z' ou '+00:00')."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _verify_backup(backup_dir: Path) -> None:
    """Vérifie que le dossier backup contient md5_pre.txt non vide."""
    md5_file = backup_dir / "md5_pre.txt"
    if not md5_file.exists():
        raise FileNotFoundError(
            f"Backup MD5 introuvable : {md5_file}. "
            f"Lance d'abord : python scripts/v9_db_hygiene.py --apply "
            f"--backup {backup_dir}  (ou md5sum manuel)."
        )
    md5_lines = [
        line for line in md5_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    if not md5_lines:
        raise ValueError(f"{md5_file} est vide — backup incomplet (aucun MD5).")


def _fetch_unresolved(
    conn: sqlite3.Connection,
    symbol: str | None = None,
    timeframe: str | None = None,
    actions: list[str] | None = None,
) -> list[sqlite3.Row]:
    """Toutes les décisions non résolues pour les actions spécifiées, triées
    par timestamp ASC (les plus anciennes d'abord).

    Par défaut (actions=None) : uniquement `preparer_entree` (backward compat).
    Passer actions=['aucune_action', 'preparer_entree'] pour inclure les
    décisions d'analyse sans exécution.
    """
    if actions is None:
        actions = ["preparer_entree"]
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in actions)
    sql = (
        "SELECT decision_id, timestamp, symbol, timeframe, direction, "
        "       snapshot_id, confiance, action "
        "FROM decisions "
        f"WHERE action IN ({placeholders}) AND is_win IS NULL "
        "AND timestamp IS NOT NULL"
    )
    params: list[Any] = list(actions)
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol)
    if timeframe:
        sql += " AND timeframe = ?"
        params.append(timeframe)
    sql += " ORDER BY timestamp ASC"
    return list(conn.execute(sql, params).fetchall())


def _fetch_entry_mid(
    conn: sqlite3.Connection, snapshot_id: str
) -> float | None:
    """Récupère le mid au moment de la décision via forces_snapshots."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT mid FROM forces_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()
    return float(row["mid"]) if row and row["mid"] is not None else None


def _fetch_future_mids(
    conn: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    start_iso: str,
    end_iso: str,
) -> list[float]:
    """Récupère tous les mid du (symbol, timeframe) entre start_iso et end_iso
    (inclus). Triés par timestamp ASC.

    Fallback TF : si moins de 3 prix dans la fenêtre sur le TF natif, on
    tente M15 (toujours présent, cf AUDIT_DB §3). Si M15 a aussi < 3 prix,
    on garde la liste originale (vide ou quasi-vide) — le caller décidera.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT mid FROM forces_snapshots "
        "WHERE symbol = ? AND timeframe = ? "
        "AND timestamp > ? AND timestamp <= ? "  # strict > pour exclure entry
        "AND mid IS NOT NULL "
        "ORDER BY timestamp ASC",
        (symbol, timeframe, start_iso, end_iso),
    ).fetchall()
    mids = [float(r["mid"]) for r in rows]
    # Fallback M15 si TF natif a < 3 prix et TF != M15
    if len(mids) < 3 and timeframe != "M15":
        rows_m15 = conn.execute(
            "SELECT mid FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = 'M15' "
            "AND timestamp > ? AND timestamp <= ? "
            "AND mid IS NOT NULL "
            "ORDER BY timestamp ASC",
            (symbol, start_iso, end_iso),
        ).fetchall()
        mids_m15 = [float(r["mid"]) for r in rows_m15]
        if len(mids_m15) > len(mids):
            return mids_m15
    return mids


# Index manquant pour la perf du resolver. Si absent, on le crée à la volée
# (idempotent via IF NOT EXISTS). Cible la query _fetch_future_mids qui
# filtre sur (symbol, timeframe, timestamp).
MISSING_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_forces_symbol_timeframe_timestamp "
    "ON forces_snapshots (symbol, timeframe, timestamp)"
)


def _ensure_perf_index(conn: sqlite3.Connection) -> None:
    """Crée l'index perf (symbol, timeframe, timestamp) sur forces_snapshots
    s'il n'existe pas. Idempotent. Coût : ~30s sur 3.5 GB."""
    conn.execute(MISSING_INDEX_SQL)


def _compute_mfe(
    direction: str, entry: float, future_mids: list[float]
) -> float:
    """Calcule le Maximum Favorable Excursion (MFE) en prix.
    Haussière : max(future) - entry
    Baissière : entry - min(future)
    Renvoie 0.0 si future_mids est vide (sécurité)."""
    if not future_mids:
        return 0.0
    if direction == "haussiere":
        return max(future_mids) - entry
    if direction == "baissiere":
        return entry - min(future_mids)
    return 0.0  # direction inconnue


def _classify(is_win_threshold: float = 0.0):
    """Renvoie une fonction qui classifie is_win selon pips > threshold."""
    def _is_win(pips: float) -> int:
        return 1 if pips > is_win_threshold else 0
    return _is_win


def resolve_one(
    conn: sqlite3.Connection,
    decision: sqlite3.Row,
    horizon_hours: float,
    skip_no_future: bool,
) -> dict[str, Any]:
    """Tente de résoudre une décision. Retourne un dict avec :
    - resolved: bool (True si UPDATE appliqué)
    - reason: str (si non résolu)
    - pips: float (si résolu)
    - is_win: int (si résolu)
    - n_future_prices: int (combien de prix futurs trouvés)
    """
    decision_id = decision["decision_id"]
    decision_ts = _parse_iso(decision["timestamp"])
    direction = decision["direction"]
    symbol = decision["symbol"]
    timeframe = decision["timeframe"]
    snapshot_id = decision["snapshot_id"]

    entry = _fetch_entry_mid(conn, snapshot_id)
    if entry is None:
        return {
            "decision_id": decision_id,
            "resolved": False,
            "reason": "entry_mid_missing",
            "n_future_prices": 0,
        }

    end_ts = decision_ts + timedelta(hours=horizon_hours)
    # Si end_ts > now, on raccourcit à now (pas de prix futur disponible
    # au-delà de l'instant présent).
    now = _now_utc()
    if end_ts > now:
        end_ts = now

    future_mids = _fetch_future_mids(
        conn, symbol, timeframe,
        decision["timestamp"], end_ts.isoformat(),
    )
    if not future_mids:
        if skip_no_future:
            return {
                "decision_id": decision_id,
                "resolved": False,
                "reason": "no_future_prices_in_window",
                "n_future_prices": 0,
            }
        # Sinon on calcule quand même avec 0 future_mids → pips=0, is_win=0
        # (permet de purger les décisions sans données sans bloquer)

    mfe = _compute_mfe(direction, entry, future_mids)
    pips = round(mfe * PIPS_MULTIPLIER, 1)
    is_win = _classify()(pips)

    return {
        "decision_id": decision_id,
        "resolved": True,
        "direction": direction,
        "entry": entry,
        "n_future_prices": len(future_mids),
        "pips": pips,
        "is_win": is_win,
    }


def apply_resolutions(
    conn: sqlite3.Connection,
    resolutions: list[dict],
) -> int:
    """Applique les résolutions en transaction. Retourne le nombre appliqué."""
    now_iso = _now_utc().isoformat()
    applied = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for r in resolutions:
            if not r["resolved"]:
                continue
            # Idempotence : WHERE is_win IS NULL évite d'écraser une
            # résolution déjà faite (par v9_resolve_decision.py manuel par ex.)
            n = conn.execute(
                "UPDATE decisions "
                "SET is_win = ?, resolution_pips = ?, resolved_at = ? "
                "WHERE decision_id = ? AND is_win IS NULL",
                (r["is_win"], r["pips"], now_iso, r["decision_id"]),
            ).rowcount
            applied += n
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return applied


def run(
    db_path: Path = DB_PATH,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    skip_no_future: bool = True,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
    init_schema: bool = True,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    """Logique principale : dry-run par défaut, retourne plan + counts.
    Caller applique ensuite via apply_resolutions() si --apply.

    `init_schema=False` permet aux tests d'utiliser une DB tmp sans
    risque de ALTER TABLE sur un schéma incomplet.

    `actions=None` (défaut) = uniquement preparer_entree (backward compat).
    """
    # NOTE: init_decision_db() n'est PAS appelé ici. La DB prod est déjà
    # initialisée par le Phase 9 init. Pour les tests, la fixture fournit
    # le schéma directement. Cela évite un round-trip ALTER inutile.
    conn = _connect(db_path)
    try:
        # Idempotent : ~30s sur 3.5 GB, no-op ensuite.
        _ensure_perf_index(conn)
    except Exception:
        pass  # ne pas bloquer la résolution si l'index échoue (perf dégradée)
    try:
        unresolved = _fetch_unresolved(conn, symbol=symbol, timeframe=timeframe, actions=actions)
        if limit is not None:
            unresolved = unresolved[:limit]
        resolutions: list[dict] = []
        for dec in unresolved:
            r = resolve_one(conn, dec, horizon_hours, skip_no_future)
            resolutions.append(r)
        return {
            "n_unresolved_total": len(unresolved),
            "n_resolvable": sum(1 for r in resolutions if r["resolved"]),
            "n_no_future_prices": sum(
                1 for r in resolutions
                if r["resolved"] and r["n_future_prices"] == 0
            ),
            "n_skipped": sum(1 for r in resolutions if not r["resolved"]),
            "horizon_hours": horizon_hours,
            "skip_no_future": skip_no_future,
            "resolutions": resolutions,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Résolution automatique WIN/LOSS prix-based (Phase 9.10)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument(
        "--horizon-hours", type=float, default=DEFAULT_HORIZON_HOURS,
        help=f"Horizon d'observation post-décision en heures (défaut {DEFAULT_HORIZON_HOURS})",
    )
    parser.add_argument(
        "--skip-no-future-prices", action="store_true",
        help="Skip les décisions sans prix futur dans la fenêtre (sinon pips=0, is_win=0)",
    )
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--timeframe", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--apply", action="store_true",
        help="Applique réellement (sinon dry-run par DÉFAUT — sécurité)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Force le mode dry-run (équivalent à omettre --apply)",
    )
    parser.add_argument(
        "--backup", type=Path, default=None,
        help="Dossier backup MD5 (OBLIGATOIRE avec --apply)",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Écrire rapport JSON dans ce fichier",
    )
    parser.add_argument(
        "--include-actions", type=str, default=None,
        help="Actions à inclure (séparées par des virgules). "
             "Défaut : preparer_entree. "
             "Ex: --include-actions aucune_action,preparer_entree",
    )
    args = parser.parse_args(argv)

    if not args.apply:
        print(f"[.. ] Mode : DRY-RUN (lecture seule)")
    if args.apply:
        if not args.backup:
            print("ERREUR: --apply exige --backup <dir> (voir --help).", file=sys.stderr)
            return 2
        try:
            _verify_backup(args.backup)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERREUR backup: {e}", file=sys.stderr)
            return 2
        print(f"[OK ] Backup MD5 vérifié : {args.backup}/md5_pre.txt")

    print(f"[.. ] DB cible : {args.db}")
    print(f"[.. ] Horizon observation : {args.horizon_hours}h")
    print(f"[.. ] Skip no-future : {args.skip_no_future_prices}")
    if args.symbol:
        print(f"[.. ] Filtre symbol : {args.symbol}")
    if args.timeframe:
        print(f"[.. ] Filtre timeframe : {args.timeframe}")
    if args.limit:
        print(f"[.. ] Limite : {args.limit} décisions")
    if args.include_actions:
        print(f"[.. ] Actions incluses : {args.include_actions}")

    # Parser les actions
    actions = None
    if args.include_actions:
        actions = [a.strip() for a in args.include_actions.split(",")]

    # En CLI production, on est sur la vraie DB → init_decision_db est un
    # no-op idempotent. En test, les fixtures passent par res.run() directement
    # avec init_schema=False (cf test_v9_resolve_decision_auto.py).
    plan = run(
        db_path=args.db,
        horizon_hours=args.horizon_hours,
        skip_no_future=args.skip_no_future_prices,
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        actions=actions,
    )
    print()
    print(f"[.. ] Décisions non résolues ciblées : {plan['n_unresolved_total']}")
    print(f"[.. ] Résolubles (au moins 1 prix futur) : {plan['n_resolvable']}")
    print(f"[.. ] Dont sans prix futur (pips=0 par défaut) : {plan['n_no_future_prices']}")
    print(f"[.. ] Skipped (refus) : {plan['n_skipped']}")

    if not args.apply:
        # Aperçu des 5 premières résolutions
        print()
        print("[.. ] Aperçu (5 premières) :")
        for r in plan["resolutions"][:5]:
            if r["resolved"]:
                print(
                    f"        {r['decision_id']}  pips={r['pips']:+.1f}  "
                    f"is_win={r['is_win']}  n_future={r['n_future_prices']}"
                )
            else:
                print(f"        {r['decision_id']}  SKIP: {r['reason']}")
        print()
        print("Aucun changement appliqué. Relancer avec --apply pour exécuter.")
        if args.report:
            args.report.write_text(
                json.dumps(plan, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"[OK ] Rapport dry-run JSON : {args.report}")
        return 0

    # === APPLY ===
    # Ne garder que les résolutions effectivement applicables
    to_apply = [r for r in plan["resolutions"] if r["resolved"]]
    if not to_apply:
        print("[.. ] Aucune résolution à appliquer (tout skipped).")
        return 0

    conn = _connect(args.db)
    try:
        applied = apply_resolutions(conn, to_apply)
    finally:
        conn.close()
    print(f"[OK ] {applied} résolutions appliquées")

    # Stats
    n_win = sum(1 for r in to_apply if r["is_win"] == 1)
    n_loss = applied - n_win
    avg_pips = sum(r["pips"] for r in to_apply) / max(1, len(to_apply))
    print(f"[.. ] Wins : {n_win} ({n_win/max(1,applied)*100:.1f}%)")
    print(f"[.. ] Losses : {n_loss}")
    print(f"[.. ] Pips moyens : {avg_pips:+.1f}")

    if args.report:
        report = {
            "timestamp_utc": _now_utc().isoformat(),
            "horizon_hours": args.horizon_hours,
            "skip_no_future": args.skip_no_future_prices,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "limit": args.limit,
            "n_unresolved_total": plan["n_unresolved_total"],
            "n_resolvable": plan["n_resolvable"],
            "n_applied": applied,
            "n_win": n_win,
            "n_loss": n_loss,
            "win_rate_pct": round(n_win / max(1, applied) * 100, 1),
            "avg_pips": round(avg_pips, 1),
        }
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[OK ] Rapport JSON : {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
