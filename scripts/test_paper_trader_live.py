"""Test live paper trader."""
import sys
sys.path.insert(0, ".")

from core.v10.v10_paper_trader import run_paper_trader

rep = run_paper_trader(
    "data/v9_forces.db",
    pairs=("AUDUSD", "GBPUSD", "USDCAD", "USDCHF"),
    n_trades_per_pair=30,
    timestamp="2026-08-05T09:30:00Z",
    rng_seed=42,
    thresholds_pair_tf_path="config/v10_bayesian_thresholds_pair_tf_v2.json",
)
print(f"n_pairs_tested = {rep.n_pairs_tested}")
print(f"n_trades_total = {rep.n_pairs_tested * rep.n_trades_per_pair}")
print(f"paper_only     = {rep.paper_only}")
print(f"micro_lot      = {rep.micro_lot}")
print()
print("GLOBAL KPIs :")
for k, v in rep.global_kpis.items():
    print(f"  {k:18} = {v}")
print()
print("PER PAIR KPIs :")
for pair, kpis in rep.per_pair_kpis.items():
    wr = kpis["wr_pct"]
    pnl_pips = kpis["pnl_pips_total"]
    pnl_usd = kpis["pnl_usd_total"]
    sharpe = kpis["sharpe_ratio"]
    max_dd = kpis["max_dd_pips"]
    avg_pnl = kpis["avg_pnl_pips"]
    print(f"  {pair:7} vsa={kpis['vsa_signal']:8} baseline_wr={kpis['baseline_wr_m30']*100:.2f}% "
          f"WR={wr:.2f}% PnL={pnl_pips:+.2f}p PnL_USD=${pnl_usd:+.4f} "
          f"sharpe={sharpe:.2f} max_dd={max_dd:.2f}p avg_pnl={avg_pnl:+.3f}p")
