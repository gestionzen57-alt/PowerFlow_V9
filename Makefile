# Makefile V10 — PowerFlow Sprint 25 LIVE
# Windows (Git Bash / PowerShell) — Senior audit 2026-08-08
# 22 cibles opérationnelles

.PHONY: help test lint batch shadow walkforward fail_analysis thompson gate loop \
        live-gate breaker breaker-status breaker-reset paper2live monitor \
        migrate migrate-apply migrate-status mt5 report cron archive backup-db clean

help:
	@echo "V10 PowerFlow — Makefile S25 LIVE (Windows)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "=== PIPELINE VALIDATION ==="
	@echo "  make test           — Tests V10 (skip V9 rouges)"
	@echo "  make lint           — Lint ruff"
	@echo "  make thompson       — Thompson Sampling sessions ICT"
	@echo "  make shadow         — RL Shadow rerun EURUSD+USDJPY"
	@echo "  make gate           — Gate adaptatif SHADOW->ACTIVE"
	@echo "  make loop           — Closed loop adaptatif complet"
	@echo "  make walkforward    — Walk-forward 30j"
	@echo "  make fail_analysis  — Analyse patterns echec shadow"
	@echo "=== PROMOTION LIVE ==="
	@echo "  make live-gate      — Validation GO/NO-GO G1-G4 toutes paires"
	@echo "  make breaker        — Check circuit-breaker (check seul)"
	@echo "  make breaker-status — Status circuit-breaker"
	@echo "  make breaker-reset  — Reset breaker (CEO only)"
	@echo "  make paper2live     — Bascule paires LIVE_READY en live"
	@echo "  make monitor        — Monitoring temps reel LIVE (loop 300s)"
	@echo "=== INFRA ==="
	@echo "  make migrate        — Dry-run migrations SQL"
	@echo "  make migrate-apply  — Apply migrations SQL"
	@echo "  make migrate-status — Status migrations SQL"
	@echo "  make mt5            — Check connexion MT5"
	@echo "  make cron           — Cron nuit S24 (13 etapes)"
	@echo "  make report         — Sprint report Telegram"
	@echo "  make batch          — Batch CEO S24"
	@echo "  make backup-db      — Backup MD5 DB"
	@echo "  make archive        — Lister scripts archives"
	@echo "  make clean          — Nettoyage .pyc"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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

loop:
	python scripts/v10_closed_loop.py

live-gate:
	python scripts/v10_live_gate.py --promote

breaker:
	python scripts/v10_circuit_breaker.py --check

breaker-status:
	python scripts/v10_circuit_breaker.py --status

breaker-reset:
	python scripts/v10_circuit_breaker.py --reset

paper2live:
	python scripts/v10_paper2live.py --all

monitor:
	python scripts/v10_live_monitor.py --loop 300

migrate:
	python scripts/apply_migrations.py

migrate-apply:
	python scripts/apply_migrations.py --apply

migrate-status:
	python scripts/apply_migrations.py --status

mt5:
	python scripts/check_mt5_live.py

report:
	python scripts/v10_sprint_report.py

cron:
	bash scripts/v10_night_cron_s24.sh

archive:
	@echo "=== Scripts archives ==="
	@dir scripts\\_archived /B 2>nul || ls scripts/_archived/

backup-db:
	python scripts/_db_md5_backup.py

clean:
	@for /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul & exit 0
	@del /s /q *.pyc 2>nul & exit 0
	@echo Clean OK
