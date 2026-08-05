"""Test live RL promotion Phase 24+."""
import sys
sys.path.insert(0, ".")

from core.v10.v10_paper_trader import run_paper_trader
from core.v10.v10_rl_promotion import decide_rl_promotion

# Phase 23+ paper report
rep = run_paper_trader(
    "data/v9_forces.db",
    pairs=("AUDUSD", "GBPUSD", "USDCAD", "USDCHF"),
    n_trades_per_pair=30,
    timestamp="2026-08-05T09:30:00Z",
    rng_seed=42,
    thresholds_pair_tf_path="config/v10_bayesian_thresholds_pair_tf_v2.json",
)

print("=== PHASE 23+ PAPER KPIs ===")
print(f"Global WR      = {rep.global_kpis['wr_pct']:.2f}%")
print(f"Global Sharpe  = {rep.global_kpis['sharpe_ratio']:.4f}")
print(f"Global max_dd  = {rep.global_kpis['max_dd_pips']:.2f}p")
print()

# Phase 24+ promotion decision
decision = decide_rl_promotion(rep, timestamp="2026-08-05T10:00:00Z")

print("=== PHASE 24+ PROMOTION DECISION ===")
print(f"Pairs evaluated     = {decision.pairs_evaluated}")
print(f"Pairs gate passed   = {decision.pairs_gate_passed}")
print(f"Consistency ratio   = {decision.consistency_ratio*100:.1f}%")
print()
print("GATE RESULTS:")
for k, v in decision.gate_results.items():
    status = "✅ PASS" if v else "❌ FAIL"
    print(f"  {k:20} = {status}")
print()
print(f"PROMOTE_TO_ACTIVE   = {decision.promote_to_active}")
print(f"PROMOTE_MODE        = {decision.promote_mode}")
print(f"PROMOTE_REASON      = {decision.promote_reason}")