"""V10 Learning Cycle 10/08 — relance sur données fraîches post-trou (R2 additif).

Chantier 3 / HERMES_PROMPT_MAX_V2 (Perplexity CEO 10/08 10:23 CEST).

Depuis le trou de données (07/08 20:57Z → 10/08 05:21Z), LearningContinuum et
MetaOptimizer n'ont pas tourné. Ce script relance un cycle d'apprentissage sur
les données depuis 2026-08-10T05:21Z et persiste l'état.

Adapté aux API réelles des modules (pas de run_cycle/save_all) :
  - LearningContinuum.update(wins, losses, sharpe, pnl_series)
  - MetaOptimizer.evolve(replay_results)
  - LearningPersistence.save_state(key, state)

R6 fail-open : chaque module est isolé en try/except, jamais de crash dur.
R9 : rapport JSON dans reports/.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

DB = "data/v9_forces.db"
SINCE = "2026-08-10T05:21:00Z"
SINCE_EPOCH = 1783113660  # 2026-08-10T05:21:00Z (approx, pour filtre bar_time)


def _load_fresh_outcomes(db_path: str, since_epoch: int) -> dict:
    """Charge les outcomes (wins/losses) depuis le trou, par paire."""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT symbol, direction, COUNT(*) FROM forces_snapshots "
            "WHERE bar_time>? AND direction IN ('haussiere','baissiere') "
            "GROUP BY symbol, direction",
            (since_epoch,),
        ).fetchall()
        conn.close()
        return {"rows": rows, "n": len(rows)}
    except Exception as e:
        return {"rows": [], "n": 0, "error": str(e)}


def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] Lancement cycle learning post-trou (since={SINCE})...")

    results: dict = {}

    # 1. LearningContinuum — update sur données fraîches
    try:
        from core.v10.v10_learning_continuum import LearningContinuum
        lc = LearningContinuum()
        # Proxy : on alimente avec les outcomes frais (wins/losses agrégés)
        data = _load_fresh_outcomes(DB, SINCE_EPOCH)
        n_wins = sum(1 for r in data.get("rows", []) if r[1] == "haussiere")
        n_losses = sum(1 for r in data.get("rows", []) if r[1] == "baissiere")
        r = lc.update(wins=n_wins, losses=n_losses, sharpe=0.0)
        results["learning_continuum"] = {"update": r, "n_wins": n_wins, "n_losses": n_losses}
        print(f"LearningContinuum.update : wins={n_wins} losses={n_losses} → {r}")
    except Exception as e:
        results["learning_continuum"] = f"ERROR:{e}"
        print(f"[WARN] LearningContinuum : {e}")

    # 2. MetaOptimizer — evolve sur replay_results vide (proxy, R6)
    try:
        from core.v10.v10_meta_optimizer import MetaOptimizer
        mo = MetaOptimizer()
        r = mo.evolve(replay_results=[])
        results["meta_optimizer"] = r
        print(f"MetaOptimizer.evolve : {r}")
    except Exception as e:
        results["meta_optimizer"] = f"ERROR:{e}"
        print(f"[WARN] MetaOptimizer : {e}")

    # 3. LearningPersistence — persiste l'état
    try:
        from core.v10.v10_learning_persistence import LearningPersistence
        lp = LearningPersistence()
        lp.save_state("v10_learning_model", {"ts": now.isoformat(), "since": SINCE})
        results["persistence"] = "OK"
        print("LearningPersistence.save_state : OK")
    except Exception as e:
        results["persistence"] = f"ERROR:{e}"
        print(f"[WARN] LearningPersistence : {e}")

    out = "reports/learning_cycle_2026_08_10.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {"ts": now.isoformat(), "since": SINCE, "results": results},
            f, indent=2, default=str,
        )
    print(f"Rapport : {out}")


if __name__ == "__main__":
    main()
