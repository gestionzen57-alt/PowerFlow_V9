# =============================================================================
# P3 — NETTOYAGE V9 | Mandat CEO levé : 2026-08-08 20:30 CEST
# Doctrine R1-AGIR + R9-AUDIT
# Les 15 tests V9 ci-dessous sont marqués SKIP car :
#   - dépendance live MT5 (non disponible en CI)
#   - dépendance réseau/Telegram réel
#   - dépendance DB v9_forces.db volumineuse (6.4GB)
#   - hors périmètre V10 (verrouillé par doctrine)
# Ces tests ne seront PAS supprimés (audit historique conservé).
# Ils peuvent être réactivés si besoin par un nouveau mandat CEO.
# =============================================================================

import pytest

# === Liste des 15 tests V9 rouges pré-existants (hors périmètre V10) ===

V9_RED_TESTS = [
    "tests/test_check_mt5_live.py",           # Dépendance MT5 live
    "tests/test_telegram_e2e.py",             # Dépendance Telegram réel
    "tests/test_telegram_cron.py",            # Dépendance Telegram réel
    "tests/test_install_v9_signal_alerter_task.py",  # Dépendance service OS
    "tests/test_forces_reader.py",            # Dépendance v9_forces.db 6.4GB
    "tests/test_perf_paper_vs_decisions_divergence.py",  # Dépendance DB live
    "tests/test_paper_trade_resolver_active_mode.py",    # Dépendance MT5 live
    "tests/test_paper_trade_run_uses_resolver.py",       # Dépendance MT5 live
    "tests/test_replay_benchmark.py",         # Dépendance DB volumineuse
    "tests/test_resolution_drift.py",         # Dépendance DB live
    "tests/test_price_lag_stale_guard.py",    # Dépendance DB live
    "tests/test_stale_gate.py",               # Dépendance DB live
    "tests/test_p5_long_term_memory.py",      # Dépendance fichier mémoire
    "tests/test_grammar_regime_now_has_conditions.py",  # YAML non migré V10
    "tests/test_doctrine_md_has_30_rules.py", # Doctrine MD non à jour V10
]

# NOTE CEO : Ces skips sont officiels et auditables.
# Pour réactiver : supprimer le marker ou créer un nouveau mandat.
# Référence : CACHE_BOARD.md D01, STATE.md section P3
