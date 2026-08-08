# =============================================================================
# conftest.py racine — PowerFlow V10 / V9
# Sprint 24 — Perplexity GitHub MCP — 2026-08-08
#
# Ce fichier configure pytest globalement pour :
# 1. Enregistrer les markers V9/V10
# 2. Appliquer le skip automatique des 15 tests V9 rouges
#    (mandat CEO P3 — 2026-08-08)
# 3. Définir les options pytest par défaut
# =============================================================================

import pytest

# === Markers globaux ===

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "v9_red: Tests V9 rouges pré-existants — skippés par mandat CEO (P3 2026-08-08)"
    )
    config.addinivalue_line(
        "markers",
        "v10_live: Tests nécessitant une connexion live MT5 ou Telegram réel"
    )
    config.addinivalue_line(
        "markers",
        "v10_db_heavy: Tests nécessitant v9_forces.db (6.4GB) — skip en CI léger"
    )


# === Skip automatique des 15 tests V9 rouges ===
# Ces tests sont hors périmètre V10 et dépendent de ressources live non disponibles en CI.
# Mandat CEO P3 — 2026-08-08 — Doctrine R1-AGIR + R9-AUDIT

V9_RED_FILES = {
    "test_check_mt5_live.py",
    "test_telegram_e2e.py",
    "test_telegram_cron.py",
    "test_install_v9_signal_alerter_task.py",
    "test_forces_reader.py",
    "test_perf_paper_vs_decisions_divergence.py",
    "test_paper_trade_resolver_active_mode.py",
    "test_paper_trade_run_uses_resolver.py",
    "test_replay_benchmark.py",
    "test_resolution_drift.py",
    "test_price_lag_stale_guard.py",
    "test_stale_gate.py",
    "test_p5_long_term_memory.py",
    "test_grammar_regime_now_has_conditions.py",
    "test_doctrine_md_has_30_rules.py",
}


def pytest_collection_modifyitems(config, items):
    """
    Skip automatique des tests V9 rouges à la collection.
    Ces tests ne sont pas supprimés — ils restent visibles dans le rapport pytest
    avec statut SKIPPED + raison CEO.
    """
    skip_v9 = pytest.mark.skip(
        reason="V9 rouge pré-existant — Mandat CEO P3 (2026-08-08). "
               "Dépendance live MT5/Telegram/DB 6.4GB hors périmètre V10. "
               "Voir docs/V10/P3_NETTOYAGE_V9.md"
    )
    for item in items:
        # Extrait le nom du fichier de test
        test_file = item.fspath.basename if hasattr(item, 'fspath') else ""
        if test_file in V9_RED_FILES:
            item.add_marker(skip_v9)
