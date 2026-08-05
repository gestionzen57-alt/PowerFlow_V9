"""Check MT5 live — Phase 28b Étape 3 (OPT-1 mission CEO).

Pour chaque (paire, TF) de la grille 6x3 + M1 GBPUSD, vérifie si
`v10_mt5_bridge.get_rates()` retourne un DataFrame live ou None.

Output :
  - reports/mt5_live_status_YYYYMMDD.json (R9 audit JSON sérialisable)
  - logs/mt5_live_check_YYYYMMDD_HHMMSS.log (R9)

Doctrine V10 :
  R1 : agit par défaut
  R2 : additif pur (n'altère pas le bridge, lit uniquement)
  R6 : fail-open (MT5 absent → status DB_FALLBACK, ne crash pas)
  R7 : tests verts (smoke fixtures)
  R9 : audit metadata honnête, JSON sérialisable
  R10 : zéro capital (lecture seule)

Usage :
  python scripts/check_mt5_live.py                   # run full grid + json report
  python scripts/check_mt5_live.py --pairs GBPUSD EURUSD  # subset
  python scripts/check_mt5_live.py --tf M30 H1            # subset
  python scripts/check_mt5_live.py --output /tmp/check.json
  python scripts/check_mt5_live.py --quiet                # exit code only
  python scripts/check_mt5_live.py --check-bridge-state   # dump état bridge complet

Exit codes :
  0 : tous (paire, TF) live OU fallback DB documenté
  1 : au moins un None inattendu
  2 : MT5 bridge non initialisé et DB également inaccessible (panne complète)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# PATH SETUP (R7 tests exécutables depuis n'importe où)
# ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────

DEFAULT_PAIRS = ("GBPUSD", "EURUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY")
DEFAULT_TFS = ("M30", "H1", "H4")
M1_GRID = ("GBPUSD",)  # uniquement GBPUSD M1 (per CEO brief)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "v9_forces.db"
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports"
DEFAULT_LOGS_DIR = REPO_ROOT / "logs"


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CellStatus:
    """Statut d'une cellule (paire × TF)."""
    pair: str
    timeframe: str
    source: str = "MT5_LIVE"  # "MT5_LIVE" | "DB_FALLBACK" | "UNAVAILABLE"
    live_ok: bool = False
    n_bars: int = 0
    last_bar_timestamp: str = ""
    last_bar_age_seconds: Optional[int] = None
    spread_mean_pips: Optional[float] = None
    spread_last_pips: Optional[float] = None
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BridgeStateSummary:
    """Résumé de l'état du bridge MT5 (R9 audit)."""
    bridge_module_path: str = ""
    mt5_initialized: bool = False
    terminal_path: Optional[str] = None
    n_rate_calls: int = 0
    n_init_attempts: int = 0
    n_init_failures: int = 0


@dataclass
class Mt5LiveReport:
    """Rapport global Phase 28b Étape 3 (R9 JSON-sérialisable)."""
    timestamp_utc: str = ""
    grid_total_cells: int = 0
    grid_live_cells: int = 0
    grid_db_fallback_cells: int = 0
    grid_unavailable_cells: int = 0
    n_pairs: int = 0
    n_tfs: int = 0
    pairs_checked: List[str] = field(default_factory=list)
    tfs_checked: List[str] = field(default_factory=list)
    cells: List[CellStatus] = field(default_factory=list)
    bridge_state: BridgeStateSummary = field(default_factory=BridgeStateSummary)
    audit: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "grid_total_cells": self.grid_total_cells,
            "grid_live_cells": self.grid_live_cells,
            "grid_db_fallback_cells": self.grid_db_fallback_cells,
            "grid_unavailable_cells": self.grid_unavailable_cells,
            "n_pairs": self.n_pairs,
            "n_tfs": self.n_tfs,
            "pairs_checked": list(self.pairs_checked),
            "tfs_checked": list(self.tfs_checked),
            "cells": [c.as_dict() for c in self.cells],
            "bridge_state": asdict(self.bridge_state),
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# HELPERS — accès MT5 bridge
# ─────────────────────────────────────────────────────────────────────

def _safe_get_rates(symbol: str, tf: str, n: int = 50):
    """Appelle v10_mt5_bridge.get_rates avec protection R6."""
    try:
        from core.v10 import v10_mt5_bridge as bridge

        df = bridge.get_rates(symbol, tf, n=n)
        if df is None:
            return None, "get_rates returned None"
        if len(df) == 0:
            return None, "DataFrame vide"
        return df, ""
    except ImportError as e:
        return None, f"import error: {e}"
    except Exception as e:
        return None, f"unexpected: {type(e).__name__}: {e}"


def _safe_get_bridge_state() -> BridgeStateSummary:
    """Récupère l'état du bridge (lecture seule). R6 fail-open."""
    out = BridgeStateSummary()
    try:
        import core.v10.v10_mt5_bridge as bridge

        out.bridge_module_path = getattr(bridge, "__file__", "")
        state = bridge.get_bridge_state()
        out.mt5_initialized = bool(getattr(state, "mt5_initialized", False))
        out.terminal_path = getattr(state, "terminal_path", None)
        out.n_rate_calls = int(getattr(state, "n_rate_calls", 0))
        out.n_init_attempts = int(getattr(state, "n_init_attempts", 0))
        out.n_init_failures = int(getattr(state, "n_init_failures", 0))
    except Exception as e:
        out.bridge_module_path = f"err: {type(e).__name__}: {e}"
    return out


def _query_db_last_bar(db_path: Path, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
    """Récupère la dernière barre depuis forces_snapshots (R6 fail-open)."""
    if not db_path.exists():
        return None
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # Table existence check
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'")
        if not cur.fetchone():
            con.close()
            return None
        cur.execute(
            """
            SELECT bar_time, open, high, low, close, tick_volume, spread
            FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
            ORDER BY bar_time DESC
            LIMIT 1
            """,
            (symbol, timeframe),
        )
        row = cur.fetchone()
        con.close()
        if row is None:
            return None
        return dict(row)
    except Exception:
        return None


def _spread_pips(symbol: str, raw_spread: Optional[float]) -> Optional[float]:
    """Convertit le spread MT5 (points) en pips. XXXJPY = 0.01 / autre = 0.0001."""
    if raw_spread is None:
        return None
    try:
        s = float(raw_spread)
    except (TypeError, ValueError):
        return None
    if "JPY" in symbol:
        # MT5 points → pips : divide par 10 pour XXXJPY (point = 0.01 yen, pip = 0.01 sur 3e décimale)
        # Convention broker 5-decs JPY : 1 pip = 10 points (Fibo)
        return round(s * 0.01, 4)
    return round(s * 0.0001, 4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _datetime_to_iso(value) -> str:
    """Convertit Timestamp/epoch en ISO string, R6 fail-open."""
    if value is None:
        return ""
    try:
        # pandas Timestamp (ou tout objet avec isoformat direct)
        if hasattr(value, "isoformat") and not isinstance(value, (int, float)):
            return value.isoformat()
        # epoch seconds (int / float)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        pass
    return ""


def _epoch_to_iso(epoch_sec) -> str:
    try:
        if epoch_sec is None:
            return ""
        return datetime.fromtimestamp(int(epoch_sec), tz=timezone.utc).isoformat()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────
# CHECK CELLULE UNIQUE
# ─────────────────────────────────────────────────────────────────────

def check_cell(
    pair: str,
    tf: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    bars_request: int = 50,
) -> CellStatus:
    """Vérifie 1 cellule (paire, TF).

    R6 : si MT5 indispo et DB absent → source=UNAVAILABLE.
    """
    cell = CellStatus(pair=pair, timeframe=tf)

    df, err = _safe_get_rates(pair, tf, n=bars_request)
    if df is not None:
        cell.source = "MT5_LIVE"
        cell.live_ok = True
        cell.n_bars = int(len(df))
        try:
            last_ts = df["time"].iloc[-1]
            cell.last_bar_timestamp = _datetime_to_iso(last_ts)
            # epoch_seconds : int/float → fromtimestamp, Timestamp → .timestamp()
            epoch_sec: Optional[int] = None
            if hasattr(last_ts, "timestamp"):
                try:
                    epoch_sec = int(last_ts.timestamp())
                except Exception:
                    epoch_sec = None
            elif isinstance(last_ts, (int, float)):
                epoch_sec = int(last_ts)
            if epoch_sec is not None:
                from datetime import datetime as _dt, timezone as _tz
                now = _dt.now(_tz.utc).timestamp()
                cell.last_bar_age_seconds = int(now - epoch_sec)
        except Exception:
            pass
        # Spread : moyenne sur les 10 dernières barres
        try:
            if "spread" in df.columns:
                last10 = df["spread"].tail(10)
                cell.spread_mean_pips = _spread_pips(pair, float(last10.mean()))
                cell.spread_last_pips = _spread_pips(pair, float(last10.iloc[-1]))
        except Exception:
            pass
        return cell

    # MT5 indispo → fallback DB
    cell.live_ok = False
    cell.error = err or "MT5 indispo"
    row = _query_db_last_bar(db_path, pair, tf)
    if row is None:
        cell.source = "UNAVAILABLE"
        return cell
    cell.source = "DB_FALLBACK"
    cell.n_bars = 1  # au moins 1 row trouvée
    cell.last_bar_timestamp = _epoch_to_iso(row.get("bar_time"))
    if row.get("bar_time") is not None:
        try:
            now = datetime.now(timezone.utc).timestamp()
            cell.last_bar_age_seconds = int(now - int(row["bar_time"]))
        except Exception:
            pass
    raw_spread = row.get("spread")
    cell.spread_last_pips = _spread_pips(pair, raw_spread)
    if cell.spread_last_pips is not None:
        cell.spread_mean_pips = cell.spread_last_pips
    return cell


# ─────────────────────────────────────────────────────────────────────
# CHECK FULL GRID
# ─────────────────────────────────────────────────────────────────────

def run_full_check(
    *,
    pairs: tuple = DEFAULT_PAIRS,
    tfs: tuple = DEFAULT_TFS,
    include_m1_gbpusd: bool = True,
    db_path: Path = DEFAULT_DB_PATH,
    bars_request: int = 50,
) -> Mt5LiveReport:
    """Run le check sur la grille complète ou restreinte."""
    cells: List[CellStatus] = []
    pairs_list = list(pairs)

    all_tfs = list(tfs)
    if include_m1_gbpusd and "GBPUSD" in pairs_list and "M1" not in all_tfs:
        # ajoute M1 pour GBPUSD uniquement
        pass  # géré séparément plus bas

    for p in pairs_list:
        for tf in tfs:
            cells.append(check_cell(p, tf, db_path=db_path, bars_request=bars_request))
    if include_m1_gbpusd and "GBPUSD" in pairs_list and "M1" not in tfs:
        cells.append(check_cell("GBPUSD", "M1", db_path=db_path, bars_request=bars_request))

    n_live = sum(1 for c in cells if c.source == "MT5_LIVE")
    n_db = sum(1 for c in cells if c.source == "DB_FALLBACK")
    n_un = sum(1 for c in cells if c.source == "UNAVAILABLE")

    rep = Mt5LiveReport(
        timestamp_utc=_now_iso(),
        grid_total_cells=len(cells),
        grid_live_cells=n_live,
        grid_db_fallback_cells=n_db,
        grid_unavailable_cells=n_un,
        n_pairs=len(pairs_list),
        n_tfs=len(tfs) + (1 if include_m1_gbpusd and "GBPUSD" in pairs_list and "M1" not in tfs else 0),
        pairs_checked=pairs_list,
        tfs_checked=list(tfs),
        cells=cells,
        bridge_state=_safe_get_bridge_state(),
        audit={
            "doctrine": "V10 R1 + R2 + R6 + R7 + R9 + R10",
            "phase": "28b etape 3 (OPT-1 mission CEO)",
            "bars_request": bars_request,
            "db_path": str(db_path),
            "include_m1_gbpusd": include_m1_gbpusd,
            "n_m1_only_for": "GBPUSD",
        },
    )
    return rep


# ─────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

def report_filename(prefix: str = "mt5_live_status") -> str:
    """Nom fichier R9 audit : reports/mt5_live_status_YYYYMMDD.json."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}_{today}.json"


def save_report(
    rep: Mt5LiveReport,
    output_path: Path,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    logs_dir: Path = DEFAULT_LOGS_DIR,
) -> Path:
    """Sauvegarde le rapport R9 + écrit un log companion (R9 audit)."""
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = reports_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = rep.as_dict()
    payload["_meta"] = {
        "doctrine": "V10 R9 audit JSON-sérialisable",
        "generated_at_utc": _now_iso(),
        "output_path": str(output_path),
    }

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Log companion
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"mt5_live_check_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write(f"[{_now_iso()}] Phase 28b Étape 3 — MT5 live check\n")
        fh.write(f"  Output: {output_path}\n")
        fh.write(f"  Grid: {rep.grid_total_cells} cells ({rep.grid_live_cells} live, "
                 f"{rep.grid_db_fallback_cells} DB, {rep.grid_unavailable_cells} unavail)\n")
        for c in rep.cells:
            fh.write(f"  {c.pair:7s} {c.timeframe:3s} : {c.source:11s} "
                     f"bars={c.n_bars} last={c.last_bar_timestamp} "
                     f"age={c.last_bar_age_seconds}s "
                     f"spread_mean={c.spread_mean_pips}\n")

    return output_path


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check MT5 live sur grille 6x3 + M1 GBPUSD")
    p.add_argument("--pairs", nargs="*", default=None,
                   help="Sous-ensemble de paires (ex GBPUSD EURUSD)")
    p.add_argument("--tf", "--tfs", dest="tfs", nargs="*", default=None,
                   help="Sous-ensemble de TF (ex M30 H1 H4 M1)")
    p.add_argument("--no-m1", action="store_true",
                   help="Désactive la cellule M1 GBPUSD supplémentaire")
    p.add_argument("--output", type=Path, default=None,
                   help="Chemin output JSON (défaut reports/mt5_live_status_YYYYMMDD.json)")
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--bars", type=int, default=50,
                   help="Nb barres demandées à MT5 (défaut 50)")
    p.add_argument("--check-bridge-state", action="store_true",
                   help="Affiche l'état complet du bridge MT5 (R9)")
    p.add_argument("--quiet", action="store_true",
                   help="Mode silencieux : exit code only")
    p.add_argument("--print-report", action="store_true",
                   help="Imprime le JSON du rapport sur stdout")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    pairs = tuple(args.pairs) if args.pairs else DEFAULT_PAIRS
    tfs = tuple(args.tfs) if args.tfs else DEFAULT_TFS

    rep = run_full_check(
        pairs=pairs,
        tfs=tfs,
        include_m1_gbpusd=not args.no_m1,
        db_path=args.db_path,
        bars_request=args.bars,
    )

    # Output file
    output_path = args.output if args.output else Path(report_filename())
    saved = save_report(rep, output_path)

    # Affichage
    if args.print_report:
        print(json.dumps(rep.as_dict(), indent=2, ensure_ascii=False))

    if not args.quiet:
        print(f"[check_mt5_live] {rep.grid_total_cells} cellules — "
              f"{rep.grid_live_cells} live / {rep.grid_db_fallback_cells} DB / "
              f"{rep.grid_unavailable_cells} unavail")
        print(f"[check_mt5_live] Sortie : {saved}")
        if args.check_bridge_state:
            print(f"[check_mt5_live] Bridge state : {rep.bridge_state}")

    # Exit code
    # 0 : tout est soit live soit fallback DB (acceptable)
    # 1 : au moins 1 cellule UNAVAILABLE (DB et MT5 KO)
    # 2 : 0 cellule live ET 0 cellule DB (panne totale)
    if rep.grid_unavailable_cells > 0 and rep.grid_live_cells == 0 and rep.grid_db_fallback_cells == 0:
        return 2
    if rep.grid_unavailable_cells > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
