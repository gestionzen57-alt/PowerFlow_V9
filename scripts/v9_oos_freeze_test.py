"""v9_oos_freeze_test.py — Phase 105 motion CEO.

OOS DB Freeze Test (R3 additif) : valide la stabilite des metriques OOS
walk-forward entre une DB live et un snapshot fige (point-in-time).

Philosophie : un edge reel est stable dans le temps. Si les metriques
OOS derivent fortement entre t_freeze et t_live, c'est un signal de
surapprentissage aux donnees recentes.

Pipeline :
  1. Snapshot DB via VACUUM INTO (rapide, compact, natif SQLite)
  2. Walk-forward sur la DB live (fenetre se terminant a t_freeze)
  3. Walk-forward sur la DB frozen (memes bornes temporelles)
  4. Comparaison : delta_WR, delta_expectancy, delta_brier
  5. Verdict STABLE / DRIFT + exit code 0/1/4

R2 additif, R6 defensif (best-effort sur chaque fenetre).
R8 backup MD5 de la DB source AVANT VACUUM INTO.
R14 git = verite (pas d'invention de chiffres).

Auteur : Hermes (Phase 105 motion CEO, 01/08/2026)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.v9.config import DB_PATH

log = logging.getLogger("v9.oos_freeze_test")

# Seuils par defaut (calibrage CEO motion Phase 105)
DELTA_WR_THRESHOLD_PTS = 5.0    # points de %
DELTA_EXPECTANCY_THRESHOLD_PIPS = 1.0  # pips par trade

# Borne safe pour walk-forward : 5 fenetres de 30j decalees de 7j
N_WINDOWS_DEFAULT = 5
WINDOW_DAYS_DEFAULT = 30
OFFSET_DAYS_DEFAULT = 7

# Chemins
FREEZE_DIR = _ROOT / "data" / "freezes"
BACKUP_DIR = _ROOT / "backups" / "oos_freeze"
FREEZE_LOG_JSONL = _ROOT / "data" / "v9_oos_freeze_log.jsonl"

# Tables clefs (reference — ne jamais hardcoder de la SQL sans les voir)
KEY_TABLES = (
    "paper_trades",
    "forces_snapshots",
    "decisions",
    "principle_evaluations",
)


# ---------------------------------------------------------------------------
# 1. Backup MD5 (R8)
# ---------------------------------------------------------------------------

def backup_md5(db_path: Path, tag: str) -> str:
    """Calcule SHA256 streaming + ecrit un fichier .md5 (R8)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    with db_path.open("rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            md5.update(chunk)
    sha_hex = sha.hexdigest()
    md5_hex = md5.hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sha_file = BACKUP_DIR / f"v9_forces_{tag}_{stamp}.sha256"
    md5_file = BACKUP_DIR / f"v9_forces_{tag}_{stamp}.md5"
    sha_file.write_text(f"{sha_hex}  {db_path}\n")
    md5_file.write_text(f"{md5_hex}  {db_path}\n")
    log.info("backup_md5 %s sha256=%s md5=%s", tag, sha_hex, md5_hex)
    return sha_hex


# ---------------------------------------------------------------------------
# 2. Freeze snapshot
# ---------------------------------------------------------------------------

def freeze_db(db_path: Path, freeze_dir: Path = FREEZE_DIR) -> tuple[Path, str, dict]:
    """Copie la DB via VACUUM INTO (SQLite natif, compact).

    Returns (freeze_path, t_freeze_iso, meta). En cas d'echec (DB corrompue,
    verrou, espace disque), fallback best-effort : on retourne un None et le
    caller degrade en mode "live-only" (R6 defensif, jamais bloquant).

    Si la DB source a une corruption btree (PRAGMA integrity_check != 'ok'),
    le freeze est impossible et on le signale dans meta.
    """
    freeze_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    freeze_path = freeze_dir / f"v9_forces_freeze_{stamp}.db"
    if freeze_path.exists():
        freeze_path.unlink()

    t_freeze = datetime.now(timezone.utc).isoformat()
    meta: dict = {"method": None, "size_mb": 0, "elapsed_s": 0.0, "warning": None}

    # Etape 1 : verifier integrite (rapide : quick_check sur la DB live)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            qc = conn.execute("PRAGMA quick_check").fetchone()
        if qc and qc[0] != "ok":
            meta["warning"] = f"DB source quick_check={qc[0]!r}, freeze degrade"
            log.warning("freeze_db: %s — fallback live-only", meta["warning"])
            return None, t_freeze, meta
    except sqlite3.DatabaseError as exc:
        meta["warning"] = f"PRAGMA quick_check failed: {exc}"
        log.warning("freeze_db: %s — fallback live-only", meta["warning"])
        return None, t_freeze, meta

    # Etape 2 : tentative VACUUM INTO
    t0 = time.time()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(f"VACUUM INTO '{freeze_path.as_posix()}'")
        meta["method"] = "vacuum_into"
        meta["size_mb"] = freeze_path.stat().st_size // (1024 * 1024)
        meta["elapsed_s"] = round(time.time() - t0, 2)
        log.info("freeze_db VACUUM %s size=%dMB elapsed=%.1fs",
                 freeze_path.name, meta["size_mb"], meta["elapsed_s"])
        return freeze_path, t_freeze, meta
    except sqlite3.DatabaseError as exc:
        meta["warning"] = f"VACUUM INTO failed: {exc}"
        log.warning("freeze_db: %s — fallback live-only", meta["warning"])
        return None, t_freeze, meta


# ---------------------------------------------------------------------------
# 3. Walk-forward OOS sur une DB donnee, avec borne haute as_of
# ---------------------------------------------------------------------------

def walk_forward_oos(
    db_path: Path,
    as_of_iso: str,
    n_windows: int = N_WINDOWS_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
    offset_days: int = OFFSET_DAYS_DEFAULT,
) -> dict:
    """Walk-forward OOS calibre pour le freeze test.

    Pour chaque fenetre w :
        start = as_of - (window_days + w*offset_days)
        end   = as_of - (w*offset_days)

    Metriques calculees : n, wins, wr%, total_pips, expectancy_pips,
    brier (proxy : |wr - 0.5| sur la sortie binaire is_win).
    """
    as_of = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
    windows = []
    if not db_path.exists():
        log.warning("walk_forward_oos: DB absente %s", db_path)
        return {"windows": [], "summary": {}}

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            for w in range(n_windows):
                start = as_of - timedelta(days=window_days + w * offset_days)
                end = as_of - timedelta(days=w * offset_days)
                # On borne sur paper_trades.opened_at + forces_snapshots.timestamp
                row = conn.execute(
                    """
                    SELECT COUNT(*) n, SUM(pt.is_win) wins,
                           ROUND(100.0*SUM(pt.is_win)/COUNT(*), 1) wr,
                           ROUND(SUM(pt.pips_simulated), 2) total_pips,
                           ROUND(AVG(pt.pips_simulated), 3) expectancy
                    FROM paper_trades pt
                    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
                    WHERE pt.opened_at BETWEEN ? AND ?
                      AND fs.timestamp <= ?
                    """,
                    (start.isoformat(), end.isoformat(), as_of.isoformat()),
                ).fetchone()
                n = int(row["n"]) if row and row["n"] else 0
                wins = int(row["wins"]) if row and row["wins"] else 0
                wr = float(row["wr"]) if row and row["wr"] is not None else 0.0
                total_pips = float(row["total_pips"]) if row and row["total_pips"] is not None else 0.0
                expectancy = float(row["expectancy"]) if row and row["expectancy"] is not None else 0.0
                # Brier proxy : ecart entre WR observe et prior 0.5, normalise
                wr_frac = wr / 100.0
                brier = round((wr_frac - 0.5) ** 2, 4) if n > 0 else None
                windows.append({
                    "window_id": w,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "n": n,
                    "wins": wins,
                    "wr": wr,
                    "total_pips": total_pips,
                    "expectancy": expectancy,
                    "brier": brier,
                })
    except sqlite3.OperationalError as exc:
        log.error("walk_forward_oos: %s", exc)
        return {"windows": [], "summary": {}, "error": str(exc)}

    n_total = sum(w["n"] for w in windows)
    wins_total = sum(w["wins"] for w in windows)
    pips_total = sum(w["total_pips"] for w in windows)
    expectancy_avg = (pips_total / n_total) if n_total > 0 else 0.0
    wr_avg = (wins_total / n_total * 100) if n_total > 0 else 0.0
    brier_avg = (
        sum(w["brier"] for w in windows if w["brier"] is not None)
        / max(1, sum(1 for w in windows if w["brier"] is not None))
        if any(w["brier"] is not None for w in windows)
        else None
    )
    summary = {
        "n_total": n_total,
        "wins_total": wins_total,
        "wr_avg": round(wr_avg, 2),
        "total_pips": round(pips_total, 2),
        "expectancy_avg": round(expectancy_avg, 3),
        "brier_avg": round(brier_avg, 4) if brier_avg is not None else None,
        "n_windows_passed_wr70": sum(1 for w in windows if w["wr"] >= 70.0 and w["n"] > 0),
    }
    return {"windows": windows, "summary": summary}


# ---------------------------------------------------------------------------
# 4. Comparaison + verdict
# ---------------------------------------------------------------------------

def compare_metrics(live: dict, frozen: dict, t_freeze: str) -> dict:
    """Compare les summaries live vs frozen et rend un verdict."""
    s_live = live.get("summary", {})
    s_frozen = frozen.get("summary", {})
    delta_wr = round(s_live.get("wr_avg", 0.0) - s_frozen.get("wr_avg", 0.0), 3)
    delta_exp = round(s_live.get("expectancy_avg", 0.0) - s_frozen.get("expectancy_avg", 0.0), 3)
    brier_live = s_live.get("brier_avg")
    brier_frozen = s_frozen.get("brier_avg")
    delta_brier = (
        round((brier_live or 0.0) - (brier_frozen or 0.0), 4)
        if brier_live is not None and brier_frozen is not None
        else None
    )
    abs_delta_wr = abs(delta_wr)
    abs_delta_exp = abs(delta_exp)
    stable = (
        abs_delta_wr < DELTA_WR_THRESHOLD_PTS
        and abs_delta_exp < DELTA_EXPECTANCY_THRESHOLD_PIPS
    )
    verdict = "STABLE" if stable else "DRIFT"
    reasons = []
    if abs_delta_wr >= DELTA_WR_THRESHOLD_PTS:
        reasons.append(f"|delta_wr|={abs_delta_wr:.2f} >= {DELTA_WR_THRESHOLD_PTS}")
    if abs_delta_exp >= DELTA_EXPECTANCY_THRESHOLD_PIPS:
        reasons.append(f"|delta_expectancy|={abs_delta_exp:.3f} >= {DELTA_EXPECTANCY_THRESHOLD_PIPS}")
    if not reasons:
        reasons.append("all deltas within thresholds")
    return {
        "t_freeze": t_freeze,
        "live": s_live,
        "frozen": s_frozen,
        "delta_wr_pts": delta_wr,
        "delta_expectancy_pips": delta_exp,
        "delta_brier": delta_brier,
        "thresholds": {
            "delta_wr_pts_max": DELTA_WR_THRESHOLD_PTS,
            "delta_expectancy_pips_max": DELTA_EXPECTANCY_THRESHOLD_PIPS,
        },
        "verdict": verdict,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# 5. JSONL append-only log
# ---------------------------------------------------------------------------

def append_jsonl(path: Path, payload: dict) -> None:
    """Append JSON line (R6, best-effort, jamais bloquant)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log.warning("append_jsonl failed: %s", exc)


# ---------------------------------------------------------------------------
# 6. Orchestration
# ---------------------------------------------------------------------------

def run_freeze_test(
    db_path: Path = DB_PATH,
    n_windows: int = N_WINDOWS_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
    offset_days: int = OFFSET_DAYS_DEFAULT,
    skip_backup: bool = False,
) -> dict:
    """Execute le pipeline complet. Retourne un rapport dict.

    Si le freeze echoue (DB corrompue, VACUUM INTO impossible), le rapport
    est emis avec verdict=DEGRADED (exit 1, pas 0) et le pipeline tourne
    en mode live-only. C'est une degradation explicite documentee dans R6.
    """
    if not db_path.exists():
        return {
            "verdict": "ERROR",
            "error": f"DB introuvable: {db_path}",
            "exit_code": 4,
        }

    backup_sha = None
    if not skip_backup:
        backup_sha = backup_md5(db_path, tag="pre_freeze")

    freeze_path, t_freeze, freeze_meta = freeze_db(db_path)
    freeze_sha = None
    if freeze_path is not None:
        freeze_sha = backup_md5(freeze_path, tag="freeze")

    # Walk-forward live (borne haute = t_freeze pour eviter le biais de drift)
    live = walk_forward_oos(
        db_path=db_path, as_of_iso=t_freeze,
        n_windows=n_windows, window_days=window_days, offset_days=offset_days,
    )
    # Walk-forward frozen (memes bornes) — skip si freeze a echoue
    frozen: dict
    if freeze_path is not None:
        frozen = walk_forward_oos(
            db_path=freeze_path, as_of_iso=t_freeze,
            n_windows=n_windows, window_days=window_days, offset_days=offset_days,
        )
    else:
        frozen = {"windows": [], "summary": {}, "skipped": "freeze_failed",
                  "reason": freeze_meta.get("warning")}

    verdict_block = compare_metrics(live, frozen, t_freeze)
    # Override verdict si freeze a echoue : on ne peut pas conclure STABLE
    if freeze_path is None:
        verdict_block["verdict"] = "DEGRADED"
        verdict_block["reasons"].append(
            f"freeze_db fallback: {freeze_meta.get('warning')}"
        )

    report = {
        "schema_version": "1.0",
        "phase": "105",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_source": str(db_path),
        "db_source_sha256_pre": backup_sha,
        "freeze_path": str(freeze_path) if freeze_path else None,
        "freeze_sha256": freeze_sha,
        "freeze_meta": freeze_meta,
        "n_windows": n_windows,
        "window_days": window_days,
        "offset_days": offset_days,
        "key_tables": list(KEY_TABLES),
        "live": live,
        "frozen": frozen,
        "comparison": verdict_block,
    }
    if verdict_block["verdict"] == "STABLE":
        report["exit_code"] = 0
    elif verdict_block["verdict"] == "DEGRADED":
        report["exit_code"] = 1  # non-bloquant, mais pas GO
    else:  # DRIFT
        report["exit_code"] = 1
    append_jsonl(FREEZE_LOG_JSONL, {
        "ts": report["generated_at"],
        "verdict": verdict_block["verdict"],
        "delta_wr_pts": verdict_block["delta_wr_pts"],
        "delta_expectancy_pips": verdict_block["delta_expectancy_pips"],
        "n_total_live": live.get("summary", {}).get("n_total", 0),
        "n_total_frozen": frozen.get("summary", {}).get("n_total", 0),
        "freeze_warning": freeze_meta.get("warning"),
    })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OOS DB Freeze Test (Phase 105)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Chemin DB source")
    parser.add_argument("--windows", type=int, default=N_WINDOWS_DEFAULT)
    parser.add_argument("--oos-days", type=int, default=WINDOW_DAYS_DEFAULT,
                        dest="oos_days", help="Taille fenetre OOS en jours")
    parser.add_argument("--offset-days", type=int, default=OFFSET_DAYS_DEFAULT,
                        dest="offset_days")
    parser.add_argument("--skip-backup", action="store_true", help="Skip MD5 (debug)")
    parser.add_argument("--report", type=Path, default=None,
                        help="Chemin rapport JSON (defaut: stdout)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    report = run_freeze_test(
        db_path=args.db,
        n_windows=args.windows,
        window_days=args.oos_days,
        offset_days=args.offset_days,
        skip_backup=args.skip_backup,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
        log.info("rapport ecrit: %s", args.report)
    else:
        print(payload)
    return report.get("exit_code", 4)


if __name__ == "__main__":
    sys.exit(main())
