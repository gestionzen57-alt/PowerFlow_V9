"""V10 Grammar V9 Extra Live — évalue les concepts V9 extra sur données live (Phase R).

Évalue les concepts de grammaire V9 extra (ADAPTIVE_VOL_GATE, ELASTIC_BREATH,
EXHAUSTION, VELOCITY_CLIMAX_GUARD, NODE_BIRTH) sur les données live
(forces_snapshots) et produit un rapport JSON. Additif R2, ne touche pas
au fichier partagé v10_live_decision (ZCode actif en parallèle).

R6 fail-open : données indisponibles → concepts non détectés, pas de crash.
R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_grammar_v9_extra import evaluate_grammar_v9_extra  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]


def load_snapshot(db_path: Path, symbol: str, timeframe: str) -> dict:
    """Charge le dernier snapshot forces pour (symbol, tf)."""
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT compression_extension_etat, compression_extension_intensite, "
        "vitesse, timestamp FROM forces_snapshots WHERE symbol=? AND timeframe=? "
        "AND is_closed_bar=1 ORDER BY bar_time DESC LIMIT 1",
        (symbol, timeframe)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "compression_etat": row[0] or "",
        "compression_intensite": row[1] or 0.0,
        "vitesse": row[2] or 0.0,
        "timestamp": row[3] or "",
    }


def evaluate_pair(db_path: Path, symbol: str, tf: str) -> dict:
    """Évalue les concepts V9 extra pour une paire."""
    snap = load_snapshot(db_path, symbol, tf)
    if not snap:
        return {"symbol": symbol, "tf": tf, "error": "no_snapshot"}

    # Mapper les états V9 depuis les données V10
    state = "NEUTRAL"
    ce = snap.get("compression_etat", "").upper()
    if ce == "COMPRESSION":
        state = "ACCUMULATING"
    elif ce == "EXTENSION":
        state = "RUPTURE"

    res = evaluate_grammar_v9_extra(
        vol_regime="HIGH" if snap.get("compression_intensite", 0) > 0.5 else "NORMAL",
        state=state,
        absorbed_pullbacks=1 if ce == "COMPRESSION" else 0,
        z_current=snap.get("compression_intensite", 0.0),
        velocite_moyenne=snap.get("vitesse", 0.0),
        session_marche=True,
    )
    return {
        "symbol": symbol, "tf": tf,
        "snapshot": snap,
        "grammar": res,
        "n_detected": res["n_detected"],
        "best": res["best"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--timeframe", default="H1")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    results = []
    for symbol in PAIRS:
        try:
            results.append(evaluate_pair(db, symbol, args.timeframe))
        except Exception as exc:
            log.warning("Évaluation %s échouée (R6): %s", symbol, type(exc).__name__)
            results.append({"symbol": symbol, "tf": args.timeframe,
                            "error": type(exc).__name__})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": args.timeframe,
        "results": results,
        "n_detected_total": sum(r.get("n_detected", 0) for r in results),
        "audit": {"r10": "compute only, zero order real"},
    }

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_grammar_v9_extra_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
