# Makefile V10 — PowerFlow Sprint 24
# Audit senior 2026-08-08 — Plateforme : Windows (Git Bash / PowerShell)
# Nouvelles cibles : loop, migrate, mt5, archive, backup-db

.PHONY: help test lint batch shadow walkforward fail_analysis thompson gate loop migrate mt5 report cron archive backup-db clean

help:
	@echo "V10 PowerFlow — Makefile Sprint 24 (Windows)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make test          — Tests V10 (skip V9 rouges)"
	@echo "  make lint          — Lint ruff core/v10 + scripts"
	@echo "  make batch         — Batch CEO S24 (rerun+walkfwd+dashboard)"
	@echo "  make shadow        — RL Shadow rerun EURUSD+USDJPY"
	@echo "  make walkforward   — Walk-forward 30j EURUSD M30"
	@echo "  make fail_analysis — Analyse patterns échec shadow"
	@echo "  make thompson      — Tuning Thompson Sampling sessions"
	@echo "  make gate          — Gate adaptatif SHADOW->ACTIVE"
	@echo "  make loop          — Closed loop adaptatif complet"
	@echo "  make migrate       — Apply migrations SQL (dry-run)"
	@echo "  make migrate-apply — Apply migrations SQL (REEL)"
	@echo "  make migrate-status— Status migrations SQL"
	@echo "  make mt5           — Check connexion MT5 Windows"
	@echo "  make report        — Sprint report Telegram"
	@echo "  make cron          — Cron nocturne S24 (13 etapes)"
	@echo "  make archive       — Lister scripts archives"
	@echo "  make backup-db     — Backup MD5 base de donnees"
	@echo "  make clean         — Nettoyage .pyc / __pycache__"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
