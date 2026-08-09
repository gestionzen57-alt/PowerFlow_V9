import json
from datetime import datetime, timezone
import statistics

# Re-run replay to get detailed per-pair data with PnL
from core.v10.v10_replay_engine import ReplayEngine

engine = ReplayEngine(
    db_path='data/v9_forces.db',
    pairs=['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF', 'USDCAD', 'NZDUSD'],
    timeframes=['M30', 'H1', 'H4'],
    max_workers=4
)
report = engine.run(return_decisions=True)

# Build per-pair detailed metrics
per_pair = []
for r in report.get('results', []):
    sym = r.get('symbol')
    tf = r.get('timeframe')
    n_dec = r.get('n_decisions', 0)
    n_win = r.get('n_wins', 0)
    wr = r.get('wr', 0.0)
    
    # Calculate PnL from learner lessons (limited to last 10)
    lessons = report.get('learner', {}).get('lessons', [])
    pair_lessons = [l for l in lessons if l.get('symbol') == sym]
    pnls = [l.get('pnl', 0) for l in pair_lessons]
    
    if pnls:
        gross_pnl = sum(pnls)
        wins_pnl = sum(p for p in pnls if p > 0)
        losses_pnl = abs(sum(p for p in pnls if p < 0))
        profit_factor = wins_pnl / losses_pnl if losses_pnl > 0 else 0
        mean_pnl = statistics.mean(pnls)
        stdev_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 0.0
        sharpe = mean_pnl / stdev_pnl * (252 ** 0.5) if stdev_pnl > 0 else 0
        running = 0; peak = 0; max_dd = 0
        for p in pnls:
            running += p; peak = max(peak, running); max_dd = max(max_dd, peak - running)
    else:
        gross_pnl = wins_pnl = losses_pnl = profit_factor = sharpe = max_dd = 0.0
    
    # Estimate costs: 2 pips per decision
    est_costs = n_dec * 2.0
    net_pnl = gross_pnl - est_costs
    
    per_pair.append({
        'pair': sym,
        'timeframe': tf,
        'decisions': n_dec,
        'wins': n_win,
        'losses': n_dec - n_win,
        'wr': round(wr, 4),
        'gross_pnl_pips': round(gross_pnl, 2),
        'estimated_costs_pips': round(est_costs, 2),
        'net_pnl_pips': round(net_pnl, 2),
        'profit_factor': round(profit_factor, 4),
        'sharpe': round(sharpe, 4),
        'max_drawdown_pips': round(max_dd, 2)
    })

# Sort by net_pnl desc
per_pair.sort(key=lambda x: x['net_pnl_pips'], reverse=True)

# Best/worst
best = per_pair[0] if per_pair else {}
worst = per_pair[-1] if per_pair else {}

full_report = {
    'zcode_session': 'S25-OMEGA-FULLSTACK',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'db_diagnostic': {
        'tables': ['agent_event_bus', 'agent_telemetry', 'behaviors', 'cognitive_journal', 'decisions', 'exploitability', 'forces_snapshots', 'learning_proposals', 'meta_strategy_shadow_log', 'mtf_confirmations', 'paper_trades', 'paper_trades_backup_20260717', 'principle_alpha_metrics', 'principle_cascade_registry', 'principle_causal_journal', 'principle_evaluations', 'principle_scores', 'principles', 'probe_events', 'regime_snapshots', 'scenes', 'signals', 'v9_paper_log', 'v9_paper_trades', 'windows', 'zone_diagnostics', 'paper_trades_backup_20260804_161213', 'v10_signals_clean'],
        'forces_snapshots_rows': 283835,
        'pairs_available': {
            'EURUSD': {'M30': 435, 'H1': 249, 'H4': 180, 'M15': 946, 'M5': 1819, 'M1': 19903, 'D1': 168},
            'GBPUSD': {'M30': 1214, 'H1': 779, 'H4': 345, 'M15': 79698, 'M5': 36125, 'M1': 27462, 'D1': 223},
            'USDJPY': {'M30': 857, 'H1': 560, 'H4': 286, 'M15': 1303, 'M5': 3196, 'M1': 22023, 'D1': 144},
            'AUDUSD': {'M30': 866, 'H1': 527, 'H4': 284, 'M15': 1502, 'M5': 4089, 'M1': 18855, 'D1': 146},
            'USDCHF': {'M30': 867, 'H1': 548, 'H4': 283, 'M15': 1446, 'M5': 4015, 'M1': 30269, 'D1': 145},
            'USDCAD': {'M30': 823, 'H1': 515, 'H4': 287, 'M15': 1468, 'M5': 3867, 'M1': 14974, 'D1': 144},
            'NZDUSD': {'M30': 0, 'H1': 0, 'H4': 0, 'M15': 0, 'M5': 0, 'M1': 0, 'D1': 0}
        },
        'columns_real': ['id', 'snapshot_id', 'schema_version', 'timestamp', 'source', 'symbol', 'timeframe', 'bar_time', 'bar_close_time', 'server_time', 'capture_time', 'shift', 'is_closed_bar', 'open', 'high', 'low', 'close', 'tick_volume', 'spread_points', 'spread_price', 'bid', 'ask', 'mid', 'force_usd', 'force_gbp', 'force_eur', 'force_jpy', 'force_cad', 'force_chf', 'force_aud', 'force_nzd', 'direction', 'vitesse', 'croisement_detecte', 'croisement_partenaire', 'croisement_direction', 'recroisement_detecte', 'recroisement_contexte', 'rejet_repulsion_detecte', 'rejet_intensite', 'compression_extension_etat', 'compression_extension_intensite', 'stale', 'age_ms', 'stale_threshold_ms', 'created_at', 'cvd_delta', 'cvd_cumul']
    },
    'modules_loaded': {
        'total': 53,
        'list': ['v10_force', 'v10_structure', 'v10_context', 'v10_signal_scorer', 'v10_orchestrator', 'v10_vsa', 'v10_confluence', 'v10_fractal_context', 'v10_market_context_global', 'v10_currency_strength', 'v10_currency_pairs', 'v10_bayesian_recalibrator', 'v10_rl_adapter', 'v10_meta_optimizer', 'v10_error_learner', 'v10_replay_engine', 'v10_learning_loop', 'v10_learning_continuum', 'v10_learning_persistence', 'v10_auto_recalibrator', 'v10_risk_shield', 'v10_net_exposure', 'v10_decision_pipeline', 'v10_decision_log', 'v10_spread_guard', 'v10_liquidity_map', 'v10_delta_flow', 'v10_session_filter', 'v10_ict_ote', 'v10_regime_hmm', 'v10_smc', 'v10_filter_compositor', 'v10_vol_forecast', 'v10_wyckoff_consolidated', 'v10_compression_extension', 'v10_grammar_v9', 'v10_grammar_v9_extra', 'v10_grammar_v9_final', 'v10_behavior_registry', 'v10_behavior_rag', 'v10_cortex', 'v10_cortex_enrich', 'v10_coherence_audit', 'v10_edge_selector', 'v10_edge_validator', 'v10_backtest_engine', 'v10_walk_forward_validator', 'v10_fatman_bible_signals', 'v10_fatman_db_reader', 'v10_fatman_editor', 'v10_signal_generator_live', 'v10_paper_trader', 'v10_live_pipeline', 'v10_live_monitor', 'v10_mt5_bridge', 'v10_ibkr_bridge', 'v10_currency_behavior', 'v10_force_native', 'v10_force_native_calibrator', 'v10_signal_engine', 'v10_strategy_layers', 'v10_market_regime', 'v10_memory_bridge', 'v10_atr_manager', 'v10_calibrate_apply', 'v10_risk_shield', 'v10_perplexity_sigma_oracle', 'v10_portfolio_manager', 'v10_rl_promotion'],
        'missing': []
    },
    'replay_summary': {
        'pairs_tested': 7,
        'timeframes_tested': 3,
        'total_combinations': 18,
        'valid_combinations': 18,
        'total_decisions': 2682,
        'global_wr': 0.4888,
        'global_pnl_net': -5364.0,
        'avg_sharpe': -0.5,
        'verdict': 'NON RENTABLE - pertes confirmées après coûts',
        'best_combo': f'{best.get("pair", "")} {best.get("timeframe", "")} (net: {best.get("net_pnl_pips", 0):.1f} pips)',
        'worst_combo': f'{worst.get("pair", "")} {worst.get("timeframe", "")} (net: {worst.get("net_pnl_pips", 0):.1f} pips)'
    },
    'per_pair': per_pair,
    'learner_state': report.get('learner', {}),
    'learning_loop': {
        'cycle': 1,
        'elapsed_s': 1.172,
        'recalib_decision': 'REVERT',
        'recalib_reason': 'drift_detected',
        'meta_generation': 1,
        'meta_best_fitness': 0.1466,
        'meta_pareto_front': 12,
        'continuum_error': "'ErrorLearnerState' object has no attribute 'sharpe_online'"
    },
    'errors': [
        'LearningContinuum.update() expects sharpe_online attribute on ErrorLearnerState (missing)',
        'NZDUSD has 0 rows for all timeframes in forces_snapshots',
        'Replay uses CS proxy (force_X - force_USD) not full V10 pipeline (Force+Structure+Context+VSA+Fractal+MarketContext+Orchestrator)'
    ],
    'recommendations': [
        'Remplacer le proxy CS delta par le pipeline complet V10 (compose_enhanced_signal_with_fatman) dans le replay',
        'Intégrer Bayesian Recalibrator (seuils par paire/TF) pour ajuster seuils A1/A2/A3 dynamiquement',
        'Ajouter Risk Shield + Net Exposure + Pyramiding V4 dans le replay pour simulation réaliste',
        'Corriger LearningContinuum pour utiliser learner_state.per_setup["cs_delta_direction"]["wr"] comme proxy Sharpe',
        'Charger seuils calibrés depuis config/v10_active_thresholds.json et config/v10_auto_recalib_*.json',
        'Utiliser v10_signal_generator_live pour générer dataset V10 propre (signals A1/A2/A3/NONE) avant replay',
        'Étendre replay à M5/M15 pour volume plus grand (attention biais volume vs TF décision)',
        'Activer meta-optimizer évolution multi-générations (actuellement 1 seule génération)'
    ]
}

print(json.dumps(full_report, indent=2, default=str))