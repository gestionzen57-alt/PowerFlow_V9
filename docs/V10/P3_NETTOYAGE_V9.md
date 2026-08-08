# P3 — Nettoyage V9 : 15 Tests Rouges

**Mandat CEO levé :** 2026-08-08 20:30 CEST  
**Statut :** 🟢 EXÉCUTÉ — skip appliqué, audit conservé  
**Branche :** `feat/v9-foundation-clean`  
**Commit :** P3-Nettoyage V9 mandat CEO  

---

## 📋 Décision

Les 15 tests V9 ci-dessous étaient **rouges pré-existants** et déclarés hors périmètre V10 dans le CACHE_BOARD.
Suite au mandat CEO du 2026-08-08, ils sont désormais **skippés officiellement** (non supprimés — audit historique conservé).

**Doctrine appliquée :** R1-AGIR (action directe) + R9-AUDIT (traçabilité complète)

---

## 🔴 → ⏭️ Les 15 Tests V9 Skippés

| # | Fichier | Raison du Skip |
|---|---------|----------------|
| 1 | `test_check_mt5_live.py` | Dépendance MT5 live (non disponible CI) |
| 2 | `test_telegram_e2e.py` | Dépendance Telegram réel |
| 3 | `test_telegram_cron.py` | Dépendance Telegram réel |
| 4 | `test_install_v9_signal_alerter_task.py` | Dépendance service OS |
| 5 | `test_forces_reader.py` | Dépendance v9_forces.db (6.4 GB) |
| 6 | `test_perf_paper_vs_decisions_divergence.py` | Dépendance DB live |
| 7 | `test_paper_trade_resolver_active_mode.py` | Dépendance MT5 live |
| 8 | `test_paper_trade_run_uses_resolver.py` | Dépendance MT5 live |
| 9 | `test_replay_benchmark.py` | Dépendance DB volumineuse |
| 10 | `test_resolution_drift.py` | Dépendance DB live |
| 11 | `test_price_lag_stale_guard.py` | Dépendance DB live |
| 12 | `test_stale_gate.py` | Dépendance DB live |
| 13 | `test_p5_long_term_memory.py` | Dépendance fichier mémoire |
| 14 | `test_grammar_regime_now_has_conditions.py` | YAML non migré V10 |
| 15 | `test_doctrine_md_has_30_rules.py` | Doctrine MD non à jour V10 |

---

## ✅ Impact

- **Suite V10 :** 1310/1310 verts — **INCHANGÉ**
- **Suite complète hors V9 rouges :** 5778/5778 verts (5793 - 15 skips)
- **Aucune régression V10 introduite**
- **Tests V9 non supprimés** : accessibles pour audit historique

---

## 🔄 Réactivation

Pour réactiver un test V9 skip : supprimer son entrée dans `tests/conftest_v9_skip.py`  
ou émettre un nouveau mandat CEO avec scope défini.

---

*Généré automatiquement par Perplexity GitHub MCP — P3 Mandat CEO 2026-08-08*
