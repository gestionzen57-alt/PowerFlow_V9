"""v9_resolve_decision_auto.py — Résolution automatique WIN/LOSS prix-based (Phase 9.10 → 13.2).

Boucle le data flow WIN/LOSS de la V9. Pour chaque décision
`action='preparer_entree'` avec `is_win=NULL` et `timestamp < now - horizon`,
calcule le résultat via ExitSimulator (stratégies de sortie professionnelles)
sur la fenêtre d'observation suivante, et pose `is_win`, `resolution_pips`,
`resolution_strategy`, `resolution_details`, `resolved_at`.

Stratégies de sortie disponibles (ExitSimulator) :
  - TP_SL      : Take-profit + Stop-loss fixes (DÉFAUT, salle de marché)
  - TRAILING   : Trailing stop (accroche les gains)
  - TIME_BASED : Sortie à horizon fixe (N barres)
  - MFE_ONLY   : MFE pur (référence académique, backward compat)

Doctrine (cf DECISIONS_LOG §Phase 9.10 + §Phase 13.2) :
- Zéro exécution d'ordre — on ne trade PAS, on simule le résultat post-trade
  à partir des prix historiques disponibles dans forces_snapshots.
- Dry-run par défaut, --apply exige --backup <dir>.
- Transaction unique, idempotent (re-run = no-op si déjà résolu).
- Pas de LLM dans la boucle (Règle 18 préservée).
- Spread estimé de 0.5 pips soustrait du gain (ajouté à la perte) pour
  simuler le coût réel de transaction.
- `resolution_strategy` stockée dans decisions pour traçabilité.
- `resolution_details` stocke le JSON complet de ExitResult (exit_reason,
  max_favorable, max_adverse, bars_held, exit_price).

Usage :
    # Dry-run avec stratégie TP/SL (défaut)
    python scripts/v9_resolve_decision_auto.py --dry-run

    # Application avec trailing stop
    python scripts/v9_resolve_decision_auto.py --apply \\
        --backup backups/2026-07-11_resolve/ \\
        --exit-strategy TRAILING --trailing-dist 15

    # Application avec TP/SL personnalisé
    python scripts/v9_resolve_decision_auto.py --apply \\
        --backup backups/2026-07-11_resolve/ \\
        --exit-strategy TP_SL --tp-pips 30 --sl-pips 15

    # Re-résolution forcée (même si déjà résolu)
    python scripts/v9_resolve_decision_auto.py --apply \\
        --backup backups/2026-07-11_resolve/ \\
        --force-reresolve

Sécurité :
- Dry-run par défaut (rien n'est modifié).
- --apply exige --backup <dir> (le dossier doit contenir md5_pre.txt).
- Transaction unique BEGIN IMMEDIATE ... COMMIT/ROLLBACK.
- Skip automatique des décisions sans prix futur dans la fenêtre (skip_no_future).
- Idempotent : un re-run sur décision déjà résolue ne change rien (sauf --force-reresolve).
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
from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator, ExitStrategy, infer_session_from_hour, price_to_pips,
)

# Horizon d'observation post-décision (défaut 4h, cohérent horizon court_terme).
DEFAULT_HORIZON_HOURS = 4

# Stratégie de sortie par défaut — DYNAMIC (TP/SL adaptatif par session,
# Brief O1 2026-07-12 : cohérence avec le batch de re-résolution appliqué
# le même jour, cf. DECISIONS_LOG §2026-07-12). Historique : MFE_ONLY
# (Phase 9.10) -> TP_SL fixe (Phase 13.2) -> DYNAMIC (Phase 13.3).
DEFAULT_EXIT_STRATEGY = "DYNAMIC"
DEFAULT_TP_PIPS = 20.0
DEFAULT_SL_PIPS = 10.0
DEFAULT_TRAILING_DIST = 15.0
DEFAULT_SPREAD_PIPS = 0.5
# Sessions sans résolution directionnelle (WR structurellement défavorable —
# 29.6%/20.6% cf. STATE.md §Phase 13.2). Skip = pas de simulation,
# resolution_strategy='SKIPPED' directement.
DEFAULT_SKIP_SESSIONS = "new_york,after"


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
    force_reresolve: bool = False,
) -> list[sqlite3.Row]:
    """Toutes les décisions non résolues pour les actions spécifiées, triées
    par timestamp ASC (les plus anciennes d'abord).

    Si force_reresolve=True, retourne TOUTES les décisions (déjà résolues
    ou non) — utile pour re-résoudre avec une nouvelle stratégie.
    """
    if actions is None:
        actions = ["preparer_entree"]
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in actions)
    sql = (
        "SELECT decision_id, timestamp, symbol, timeframe, direction, "
        "       snapshot_id, confiance, action "
        "FROM decisions "
        f"WHERE action IN ({placeholders})"
    )
    params: list[Any] = list(actions)
    if not force_reresolve:
        sql += " AND is_win IS NULL"
    sql += " AND timestamp IS NOT NULL"
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
    exit_strategy: str = DEFAULT_EXIT_STRATEGY,
    tp_pips: float = DEFAULT_TP_PIPS,
    sl_pips: float = DEFAULT_SL_PIPS,
    trailing_dist: float = DEFAULT_TRAILING_DIST,
    spread_pips: float = DEFAULT_SPREAD_PIPS,
    skip_sessions: list[str] | None = None,
) -> dict[str, Any]:
    """Tente de résoudre une décision avec ExitSimulator.

    Si la session de marché (inférée depuis l'heure UTC de la décision) est
    dans `skip_sessions`, aucune simulation directionnelle n'est faite :
    la décision est marquée resolution_strategy='SKIPPED' (is_win=0,
    pips=0.0). Cf. Brief O1 — sessions New York/After hors doctrine DYNAMIC.

    Retourne un dict avec :
    - resolved: bool (True si UPDATE appliqué)
    - reason: str (si non résolu)
    - pips: float (si résolu)
    - is_win: int (si résolu)
    - n_future_prices: int (combien de prix futurs trouvés)
    - exit_reason: str (raison de sortie simulée)
    - exit_price: float (prix de sortie simulé)
    - max_favorable: float (MFE en pips)
    - max_adverse: float (MAE en pips)
    - bars_held: int (nombre de barres avant sortie)
    - session: str (session de marché inférée)
    - resolution_strategy_override: str (présent uniquement si SKIPPED —
      apply_resolutions() l'utilise à la place de `exit_strategy`)
    """
    decision_id = decision["decision_id"]
    decision_ts = _parse_iso(decision["timestamp"])
    direction = decision["direction"]
    symbol = decision["symbol"]
    timeframe = decision["timeframe"]
    snapshot_id = decision["snapshot_id"]

    session = infer_session_from_hour(decision_ts.hour)
    if skip_sessions and session in skip_sessions:
        return {
            "decision_id": decision_id,
            "resolved": True,
            "is_win": 0,
            "pips": 0.0,
            "exit_reason": f"skipped_{session}",
            "session": session,
            "n_future_prices": 0,
            "resolution_strategy_override": "SKIPPED",
        }

    entry = _fetch_entry_mid(conn, snapshot_id)
    if entry is None:
        return {
            "decision_id": decision_id,
            "resolved": False,
            "reason": "entry_mid_missing",
            "n_future_prices": 0,
        }

    end_ts = decision_ts + timedelta(hours=horizon_hours)
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

    # Utiliser ExitSimulator pour une simulation réaliste. utc_hour permet
    # à la stratégie DYNAMIC de choisir le profil TP/SL de la bonne session
    # (ignoré par les autres stratégies).
    simulator = ExitSimulator(
        strategy=exit_strategy,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        trailing_dist=trailing_dist,
        spread_pips=spread_pips,
    )
    result = simulator.simulate(
        entry, direction, future_mids, utc_hour=decision_ts.hour,
    )

    return {
        "decision_id": decision_id,
        "resolved": True,
        "direction": direction,
        "entry": entry,
        "n_future_prices": len(future_mids),
        "pips": result.pips,
        "is_win": result.is_win,
        "exit_reason": result.exit_reason,
        "exit_price": result.exit_price,
        "max_favorable": result.max_favorable,
        "max_adverse": result.max_adverse,
        "bars_held": result.bars_held,
        "session": session,
    }


def apply_resolutions(
    conn: sqlite3.Connection,
    resolutions: list[dict],
    exit_strategy: str = DEFAULT_EXIT_STRATEGY,
    force_reresolve: bool = False,
) -> int:
    """Applique les résolutions en transaction. Retourne le nombre appliqué.

    Si force_reresolve=True, met à jour même les décisions déjà résolues
    (utile pour re-résoudre avec une nouvelle stratégie).
    """
    now_iso = _now_utc().isoformat()
    applied = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for r in resolutions:
            if not r["resolved"]:
                continue

            # SKIPPED (session hors doctrine) écrase la stratégie CLI.
            strategy_to_write = r.get("resolution_strategy_override", exit_strategy)

            # Préparer resolution_details JSON
            details = json.dumps({
                "exit_reason": r.get("exit_reason", "mfe_end"),
                "exit_price": r.get("exit_price"),
                "entry_price": r.get("entry"),
                "max_favorable": r.get("max_favorable"),
                "max_adverse": r.get("max_adverse"),
                "bars_held": r.get("bars_held", 0),
                "n_future_prices": r.get("n_future_prices", 0),
                "strategy": strategy_to_write,
                "session": r.get("session"),
            })

            if force_reresolve:
                n = conn.execute(
                    "UPDATE decisions "
                    "SET is_win = ?, resolution_pips = ?, "
                    "    resolution_strategy = ?, resolution_details = ?, "
                    "    resolved_at = ? "
                    "WHERE decision_id = ?",
                    (r["is_win"], r["pips"], strategy_to_write, details,
                     now_iso, r["decision_id"]),
                ).rowcount
            else:
                n = conn.execute(
                    "UPDATE decisions "
                    "SET is_win = ?, resolution_pips = ?, "
                    "    resolution_strategy = ?, resolution_details = ?, "
                    "    resolved_at = ? "
                    "WHERE decision_id = ? AND is_win IS NULL",
                    (r["is_win"], r["pips"], strategy_to_write, details,
                     now_iso, r["decision_id"]),
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
    exit_strategy: str = DEFAULT_EXIT_STRATEGY,
    tp_pips: float = DEFAULT_TP_PIPS,
    sl_pips: float = DEFAULT_SL_PIPS,
    trailing_dist: float = DEFAULT_TRAILING_DIST,
    spread_pips: float = DEFAULT_SPREAD_PIPS,
    force_reresolve: bool = False,
    skip_sessions: list[str] | None = None,
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
        unresolved = _fetch_unresolved(
            conn, symbol=symbol, timeframe=timeframe, actions=actions,
            force_reresolve=force_reresolve,
        )
        if limit is not None:
            unresolved = unresolved[:limit]
        resolutions: list[dict] = []
        for dec in unresolved:
            r = resolve_one(
                conn, dec, horizon_hours, skip_no_future,
                exit_strategy=exit_strategy,
                tp_pips=tp_pips, sl_pips=sl_pips,
                trailing_dist=trailing_dist, spread_pips=spread_pips,
                skip_sessions=skip_sessions,
            )
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
            "exit_strategy": exit_strategy,
            "tp_pips": tp_pips,
            "sl_pips": sl_pips,
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
    parser.add_argument(
        "--exit-strategy", type=str, default=DEFAULT_EXIT_STRATEGY,
        help=f"Stratégie de sortie : DYNAMIC, TP_SL, TRAILING, TIME_BASED, "
             f"MFE_ONLY (défaut {DEFAULT_EXIT_STRATEGY})",
    )
    parser.add_argument(
        "--tp-pips", type=float, default=DEFAULT_TP_PIPS,
        help=f"Take-profit en pips (défaut {DEFAULT_TP_PIPS})",
    )
    parser.add_argument(
        "--sl-pips", type=float, default=DEFAULT_SL_PIPS,
        help=f"Stop-loss en pips (défaut {DEFAULT_SL_PIPS})",
    )
    parser.add_argument(
        "--trailing-dist", type=float, default=DEFAULT_TRAILING_DIST,
        help=f"Distance trailing stop en pips (défaut {DEFAULT_TRAILING_DIST})",
    )
    parser.add_argument(
        "--spread-pips", type=float, default=DEFAULT_SPREAD_PIPS,
        help=f"Spread estimé en pips (défaut {DEFAULT_SPREAD_PIPS})",
    )
    parser.add_argument(
        "--force-reresolve", action="store_true",
        help="Force la re-résolution même si déjà résolu (utile pour changer de stratégie)",
    )
    parser.add_argument(
        "--skip-sessions", type=str, default=DEFAULT_SKIP_SESSIONS,
        help="Sessions sans résolution directionnelle, séparées par des "
             f"virgules (défaut {DEFAULT_SKIP_SESSIONS!r}). "
             "Vide (--skip-sessions '') pour désactiver.",
    )
    args = parser.parse_args(argv)

    skip_sessions = [s.strip() for s in args.skip_sessions.split(",") if s.strip()]

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
    print(f"[.. ] Stratégie sortie : {args.exit_strategy}")
    if args.exit_strategy == "TP_SL":
        print(f"[.. ]   TP={args.tp_pips} pips / SL={args.sl_pips} pips")
    elif args.exit_strategy == "TRAILING":
        print(f"[.. ]   Distance trailing={args.trailing_dist} pips")
    print(f"[.. ] Spread estimé : {args.spread_pips} pips")
    if args.force_reresolve:
        print(f"[.. ] Force re-résolution : OUI (même si déjà résolu)")
    if args.symbol:
        print(f"[.. ] Filtre symbol : {args.symbol}")
    if args.timeframe:
        print(f"[.. ] Filtre timeframe : {args.timeframe}")
    if args.limit:
        print(f"[.. ] Limite : {args.limit} décisions")
    if args.include_actions:
        print(f"[.. ] Actions incluses : {args.include_actions}")
    print(f"[.. ] Sessions skip (pas de résolution directionnelle) : "
          f"{skip_sessions or 'aucune'}")

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
        skip_sessions=skip_sessions,
        exit_strategy=args.exit_strategy,
        tp_pips=args.tp_pips,
        sl_pips=args.sl_pips,
        trailing_dist=args.trailing_dist,
        spread_pips=args.spread_pips,
        force_reresolve=args.force_reresolve,
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
        applied = apply_resolutions(
            conn, to_apply,
            exit_strategy=args.exit_strategy,
            force_reresolve=args.force_reresolve,
        )
    finally:
        conn.close()
    print(f"[OK ] {applied} résolutions appliquées")

    # Stats
    n_win = sum(1 for r in to_apply if r["is_win"] == 1)
    n_loss = applied - n_win
    avg_pips = sum(r["pips"] for r in to_apply) / max(1, len(to_apply))
    # Exit reasons stats
    exit_reasons: dict[str, int] = {}
    for r in to_apply:
        reason = r.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    print(f"[.. ] Wins : {n_win} ({n_win/max(1,applied)*100:.1f}%)")
    print(f"[.. ] Losses : {n_loss}")
    print(f"[.. ] Pips moyens : {avg_pips:+.1f}")
    print(f"[.. ] Raisons de sortie : {exit_reasons}")

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
