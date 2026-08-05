"""V10 Replay Batch — replay profondeur complète + carte des edges + persistance (Phase R).

Rejoue TOUTE la profondeur historique disponible (M30: 4559, H1: 2925, H4: 1597
bars) par paire×TF pour produire :
  - la carte complète des edges (WR par paire×TF×direction),
  - le modèle d'apprentissage PERSISTÉ (rechargé + enrichi à chaque run),
  - la recommandation de calibration R8.

L'apprentissage est CONTINU : le modèle est chargé depuis v10_learning_state.db,
enrichi par ce replay, puis re-persisté. Aucune perte entre les runs.

R9 honnête : pnl proxy forward. R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_error_learner import ErrorLearner, TradeOutcome  # noqa: E402
from core.v10.v10_learning_persistence import (  # noqa: E402
    LearningPersistence, learner_to_dict, dict_to_learner,
)
from scripts.v10_replay_engine import replay_pair  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
TFS = ["H1", "M30", "H4"]
MODEL_KEY = "v10_learning_model"


def build_edge_map(results: list) -> dict:
    """Carte des edges par paire×TF (WR, n, direction dominante)."""
    edges = {}
    for r in results:
        sym, tf = r.get("symbol"), r.get("tf")
        n = r.get("n_decisions", 0)
        wr = r.get("wr", 0.0)
        if n >= 20:  # seuil minimal de confiance
            n_buys = r.get("n_buys", 0)
            n_sells = r.get("n_sells", 0)
            dom_dir = "BUY" if n_buys >= n_sells else "SELL"
            edges[f"{sym}|{tf}"] = {
                "n": n, "wr": wr,
                "direction": dom_dir,
                "edge": "YES" if wr >= 0.50 else "NO",
                "delta_pts": round((wr - 0.50) * 100.0, 1),
            }
    return dict(sorted(edges.items(), key=lambda kv: -kv[1]["wr"]))


def run_batch(db: Path, persist: bool = True) -> dict:
    """Replay complet + persistance du modèle d'apprentissage."""
    # Charger le modèle existant (apprentissage continu)
    persistence = LearningPersistence() if persist else None
    learner = ErrorLearner()
    if persistence:
        model = persistence.load_state(MODEL_KEY)
        if model:
            learner = dict_to_learner(model)
            log.info("Modèle chargé: %d trades historiques", learner.state.n_trades)

    results = []
    for symbol in PAIRS:
        for tf in TFS:
            try:
                res = replay_pair(db, symbol, tf, limit=5000)
                results.append(res)
                # Enrichir le learner persistant avec les outcomes du replay
                for d in res.get("decisions", []):
                    learner.record(TradeOutcome(
                        symbol=symbol, setup=d.get("level", "A2"),
                        kill_zone=f"REPLAY_{tf}", win=d["is_win"],
                        pnl=d["pnl_pips"], timestamp=d["timestamp"],
                    ))
                log.info("Replay %s %s: %d décisions, WR=%.2f",
                         symbol, tf, res["n_decisions"], res["wr"])
            except Exception as exc:
                log.warning("Replay %s %s échoué (R6): %s", symbol, tf,
                            type(exc).__name__)
                results.append({"symbol": symbol, "tf": tf, "error": type(exc).__name__})

    edge_map = build_edge_map(results)

    # Persister le modèle enrichi
    model_saved = False
    if persistence:
        persistence.save_state(MODEL_KEY, learner_to_dict(learner))
        model_saved = True
        persistence.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_pairs_tf": len(results),
        "edge_map": edge_map,
        "n_edges_yes": sum(1 for v in edge_map.values() if v["edge"] == "YES"),
        "learning_model": {
            "n_trades_total": learner.state.n_trades,
            "wr": round(learner.state.n_wins / max(1, learner.state.n_trades), 4),
            "drift_detected": learner.state.drift_detected,
            "recalibrate_recommended": learner.state.recalibrate_recommended,
            "persisted": model_saved,
        },
        "per_pair_tf": results,
        "audit": {
            "r9_honest": "pnl proxy forward, pas PnL Fatman",
            "r10": "compute only, zero order real",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    report = run_batch(db, persist=not args.no_persist)

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_replay_batch_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    # Résumé lisible
    lm = report["learning_model"]
    print(f"REPLAY BATCH: {report['n_pairs_tf']} paires-TF, "
          f"{lm['n_trades_total']} trades appris, WR={lm['wr']:.3f}, "
          f"edges={report['n_edges_yes']}, drift={lm['drift_detected']}, "
          f"persisté={lm['persisted']}")
    print("=== Edge map (WR ≥ 50%) ===")
    for k, v in report["edge_map"].items():
        if v["edge"] == "YES":
            print(f"  {k}: WR={v['wr']:.2f} ({v['n']} trades, {v['direction']})")
    log.info("Rapport replay batch écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
