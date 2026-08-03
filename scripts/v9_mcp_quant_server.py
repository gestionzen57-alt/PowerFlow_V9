"""v9_mcp_quant_server.py — Phase 40A motion CEO 48h autopilote.

Serveur MCP (Model Context Protocol) pour les outils quantiques V9.
Expose 6 tools : monte_carlo, kelly, bayesian, var, walk_forward_mc, regime.

Format : JSON-RPC 2.0 sur stdio (style MCP).

Auteur : Hermes (Phase 40A motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.mcp_quant")


def _db_query(db_path: Path, query: str) -> list[dict]:
    """Execute SQL query et retourne liste de dict."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


# === TOOLS ===

def tool_monte_carlo(args: dict) -> dict:
    """Monte Carlo bootstrap tool."""
    n_sims = int(args.get("n_sims", 1000))
    seed = int(args.get("seed", 42))
    from scripts.v9_monte_carlo import get_paper_trades_pips, monte_carlo_bootstrap
    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    return monte_carlo_bootstrap(pips, n_simulations=n_sims, seed=seed)


def tool_kelly(args: dict) -> dict:
    """Kelly criterion tool."""
    from scripts.v9_kelly_criterion import compute_kelly, compute_lot_size
    wr = float(args.get("wr", 0.946))
    tp = float(args.get("tp", 25.0))
    sl = float(args.get("sl", 8.0))
    capital = float(args.get("capital", 10000.0))
    fractional = float(args.get("fractional", 0.25))
    rr = tp / sl
    kelly = compute_kelly(wr, rr, fractional=fractional)
    lot = compute_lot_size(kelly.get("kelly_safe", 0), capital, sl)
    return {"kelly": kelly, "lot": lot}


def tool_bayesian(args: dict) -> dict:
    """Bayesian posterior tool."""
    threshold = float(args.get("threshold", 0.60))
    from scripts.v9_bayesian_posterior import get_paper_trades_results, bayesian_posterior
    from core.v9.config import DB_PATH
    n_wins, n_losses = get_paper_trades_results(DB_PATH)
    return bayesian_posterior(n_wins, n_losses, threshold=threshold)


def tool_var(args: dict) -> dict:
    """VaR live tool."""
    confidence = float(args.get("confidence", 0.95))
    from scripts.v9_var_live import get_paper_trades_pips, compute_var
    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    return compute_var(pips, confidence=confidence)


def tool_walk_forward_mc(args: dict) -> dict:
    """Walk-forward Monte Carlo tool."""
    n_sims = int(args.get("n_sims", 1000))
    train_ratio = float(args.get("train_ratio", 0.7))
    from scripts.v9_walk_forward_monte_carlo import (
        get_paper_trades_chrono, walk_forward_monte_carlo,
    )
    from core.v9.config import DB_PATH
    trades = get_paper_trades_chrono(DB_PATH)
    return walk_forward_monte_carlo(trades, n_sims=n_sims,
                                       train_ratio=train_ratio)


def tool_regime(args: dict) -> dict:
    """Regime detector tool."""
    days = int(args.get("days", 7))
    from scripts.v9_regime_detector import get_paper_trades_recent, detect_regime
    from core.v9.config import DB_PATH
    trades = get_paper_trades_recent(DB_PATH, days=days)
    return detect_regime(trades)


def tool_sentiment(args: dict) -> dict:
    """Market sentiment tool."""
    days = int(args.get("days", 7))
    from scripts.v9_market_sentiment import (
        get_paper_trades_directional, compute_sentiment,
    )
    from core.v9.config import DB_PATH
    directional = get_paper_trades_directional(DB_PATH, days=days)
    sentiment = compute_sentiment(directional)
    return {"directional": directional, "sentiment": sentiment}


def tool_gap_signaux_diagnostic(args: dict) -> dict:
    """Diagnostic gap signaux live (Phase 173+174).

    Args:
        hours: fenêtre de scan en heures (defaut 2).
        tail_lines: nb lignes du log capture_server a lire (defaut 100).

    Returns:
        dict avec : db_volume_per_min (HH:MM, count), max_ts, gap_min,
        now_utc, log_tail (ModuleNotFoundError/ImportError/Traceback extraits),
        verdict (OK/GAP/CRASH/COLD).
    """
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    hours = int(args.get("hours", 2))
    tail_lines = int(args.get("tail_lines", 100))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # 1) DB volume par minute
    rows = _db_query(
        _ROOT / "data" / "v9_forces.db",
        f"SELECT strftime('%H:%M', timestamp) as t, COUNT(*) as n "
        f"FROM signals WHERE timestamp > '{cutoff}' "
        f"GROUP BY strftime('%H:%M', timestamp) ORDER BY t DESC",
    )
    max_ts_row = _db_query(
        _ROOT / "data" / "v9_forces.db",
        "SELECT MAX(timestamp) as max_ts, COUNT(*) as total FROM signals",
    )
    max_ts = max_ts_row[0]["max_ts"] if max_ts_row else None
    total = max_ts_row[0]["total"] if max_ts_row else 0
    # 2) Calcul du gap
    now = datetime.now(timezone.utc)
    gap_min = None
    if max_ts:
        try:
            mt = datetime.fromisoformat(max_ts)
            gap_min = round((now - mt).total_seconds() / 60.0, 1)
        except (ValueError, TypeError):
            pass
    # 3) Tail log capture_server
    log_path = _ROOT / "logs" / "v9_capture.log"
    log_tail_raw = []
    log_crash_lines = []
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                log_tail_raw = [ln.rstrip() for ln in all_lines[-tail_lines:]]
            for ln in log_tail_raw:
                if any(marker in ln for marker in (
                    "ModuleNotFoundError", "ImportError",
                    "Traceback (most recent call last)", "FATAL",
                )):
                    log_crash_lines.append(ln)
        except OSError:
            pass
    # 4) Verdict
    if gap_min is None:
        verdict = "COLD"  # pas de signaux en DB
    elif gap_min < 5:
        verdict = "OK"
    elif gap_min < 30 and log_crash_lines:
        verdict = "CRASH"
    elif gap_min < 30:
        verdict = "GAP"
    else:
        verdict = "STALE"
    return {
        "now_utc": now.isoformat(),
        "max_ts": max_ts,
        "gap_min": gap_min,
        "total_signals": total,
        "db_volume_per_min": rows,
        "log_crash_count": len(log_crash_lines),
        "log_crash_sample": log_crash_lines[:5],
        "verdict": verdict,
    }


def tool_venv_deps_audit(args: dict) -> dict:
    """Audit deps runtime vs pyproject.toml (anti-regression Phase 171+174).

    Compare la liste des packages installes dans .venv avec les
    dependencies declarees dans pyproject.toml. Retourne les manquants
    (cote runtime) et les non declares (cote pyproject).

    Args:
        venv_python: chemin du python.exe du venv (defaut .venv/Scripts/python.exe).
        pyproject: chemin du pyproject.toml (defaut racine du projet).

    Returns:
        dict avec : pyproject_deps (list), pip_installed (list),
        missing (in pyproject but NOT installed), undeclared (installed
        but not in pyproject), status (OK/DRIFT/MISSING/UNREACHABLE).
    """
    import subprocess
    import tomllib
    from pathlib import Path
    project_root = _ROOT
    venv_py = Path(args.get("venv_python",
                            str(project_root / ".venv" / "Scripts" / "python.exe")))
    pp_path = Path(args.get("pyproject", str(project_root / "pyproject.toml")))
    out = {
        "venv_python": str(venv_py),
        "pyproject": str(pp_path),
        "pyproject_deps": [],
        "pip_installed": [],
        "missing": [],
        "undeclared": [],
        "status": "UNREACHABLE",
        "error": None,
    }
    # 1) Lire pyproject.toml
    if not pp_path.exists():
        out["error"] = f"pyproject.toml introuvable: {pp_path}"
        return out
    try:
        with pp_path.open("rb") as f:
            data = tomllib.load(f)
        proj = data.get("project", {})
        deps_raw = proj.get("dependencies", [])
        # Normaliser (enlever version specifiers basiques)
        pp_deps = set()
        for d in deps_raw:
            name = d.split(">=")[0].split("==")[0].split("<")[0].split(">")[0].strip()
            if name:
                pp_deps.add(name.lower())
        out["pyproject_deps"] = sorted(pp_deps)
    except Exception as e:
        out["error"] = f"pyproject.toml parse: {e}"
        return out
    # 2) pip list depuis l'interpreteur du venv
    if not venv_py.exists():
        out["error"] = f"venv python introuvable: {venv_py}"
        return out
    try:
        proc = subprocess.run(
            [str(venv_py), "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            out["error"] = f"pip list failed: {proc.stderr[:200]}"
            return out
        pkgs = json.loads(proc.stdout)
        installed = {p["name"].lower() for p in pkgs}
        out["pip_installed"] = sorted(installed)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            json.JSONDecodeError, OSError) as e:
        out["error"] = f"pip list exec: {e}"
        return out
    # 3) Diff
    out["missing"] = sorted(pp_deps - installed)
    out["undeclared"] = sorted(installed - pp_deps)
    if not out["missing"] and not out["undeclared"]:
        out["status"] = "OK"
    elif out["missing"]:
        out["status"] = "MISSING"
    else:
        out["status"] = "DRIFT"
    return out


TOOLS = {
    "monte_carlo": tool_monte_carlo,
    "kelly": tool_kelly,
    "bayesian": tool_bayesian,
    "var": tool_var,
    "walk_forward_mc": tool_walk_forward_mc,
    "regime": tool_regime,
    "sentiment": tool_sentiment,
    "gap_signaux_diagnostic": tool_gap_signaux_diagnostic,
    "venv_deps_audit": tool_venv_deps_audit,
}


# === JSON-RPC 2.0 HANDLER ===

def handle_request(req: dict) -> dict:
    """Handle un JSON-RPC 2.0 request."""
    method = req.get("method")
    params = req.get("params", {})
    req_id = req.get("id")
    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "tools": [
                    {"name": name, "description": fn.__doc__ or ""}
                    for name, fn in TOOLS.items()
                ],
            },
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        try:
            result = TOOLS[tool_name](args)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "json", "data": result}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }
    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 MCP quant server (Phase 40A)",
    )
    parser.add_argument("--mode", choices=["stdio", "test"], default="test",
                        help="stdio = JSON-RPC loop, test = smoke test")
    parser.add_argument("--tool", default=None,
                        help="Tool a appeler (mode test)")
    parser.add_argument("--args", default="{}",
                        help="Args JSON (mode test)")
    args = parser.parse_args(argv)

    if args.mode == "test":
        # Mode test : appelle un tool et affiche resultat
        if not args.tool:
            print("Tools disponibles :")
            for name in TOOLS:
                print(f"  - {name}")
            return 0
        if args.tool not in TOOLS:
            print(f"Erreur : tool inconnu '{args.tool}'")
            return 1
        try:
            tool_args = json.loads(args.args)
        except json.JSONDecodeError as e:
            print(f"Erreur JSON : {e}")
            return 1
        result = TOOLS[args.tool](tool_args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    else:
        # Mode stdio : JSON-RPC loop
        print("V9 MCP quant server ready (stdio mode)", file=sys.stderr)
        for line in sys.stdin:
            try:
                req = json.loads(line.strip())
                resp = handle_request(req)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            except json.JSONDecodeError:
                continue
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())