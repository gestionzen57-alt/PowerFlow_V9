# Makefile V10 — PowerFlow Sprint 24
# Perplexity GitHub MCP — 2026-08-08 20:51 CEST
# Doctrine : R1-AGIR, R10-CAPITAL (0 ordre réel)

.PHONY: help test lint batch shadow walkforward fail_analysis thompson gate report cron clean

help:
	@echo "V10 PowerFlow — Makefile Sprint 24"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make test          — Tests V10 (skip V9 rouges)"
	@echo "  make lint          — Lint ruff core/v10 + scripts"
	@echo "  make batch         — Batch CEO S24 (rerun+walkfwd+dashboard)"
	@echo "  make shadow        — RL Shadow rerun EURUSD+USDJPY"
	@echo "  make walkforward   — Walk-forward 30j EURUSD M30"
	@echo "  make fail_analysis — Analyse patterns échec shadow"
	@echo "  make thompson      — Tuning Thompson Sampling sessions"
	@echo "  make gate          — Gate adaptatif SHADOW→ACTIVE"
	@echo "  make report        — Sprint report Telegram"
	@echo "  make cron          — Cron nocturne S24 (11 étapes)"
	@echo "  make clean         — Nettoyage .pyc / __pycache__"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

test:
	python -m pytest tests/ -q --tb=short --no-header

lint:
	ruff check core/v10/ scripts/ --ignore E501,E402,F401 || true

batch:
	python scripts/v10_s24_batch.py

shadow:
	python scripts/v10_rl_shadow_rerun.py

walkforward:
	python scripts/v10_walkforward_30d.py

fail_analysis:
	python scripts/v10_rl_fail_analysis.py

thompson:
	python scripts/v10_thompson_tuner.py

gate:
	python scripts/v10_gate_adaptive.py

report:
	python scripts/v10_sprint_report.py

cron:
	bash scripts/v10_night_cron_s24.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "Clean OK"
