#!/usr/bin/env bash
# v10_night_cron_s24.sh — Cron nocturne UNIQUE Sprint 24
# Plateforme : Windows via Git Bash / WSL2
# Audit senior 2026-08-08 : ajout mt5_check + apply_migrations + closed_loop
# IMPORTANT : Ce fichier est le SEUL cron nocturne actif. v10_night_cron.sh = LEGACY ARCHIVÉ

set -euo pipefail
cd "$(dirname "$0")/.."

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "=== CRON NUIT S24 START $TIMESTAMP ==="

echo "[1/13] Apply migrations SQL"
python scripts/apply_migrations.py --apply || echo "[WARN] migrations — erreur non bloquante"

echo "[2/13] Check MT5 live (Windows)"
python scripts/check_mt5_live.py || echo "[WARN] MT5 check — non bloquant"

echo "[3/13] Thompson Sampling tuning"
python scripts/v10_thompson_tuner.py

echo "[4/13] Session filter ICT"
python scripts/v10_session_filter.py

echo "[5/13] Gate adaptatif"
python scripts/v10_gate_adaptive.py

echo "[6/13] Closed loop adaptatif"
python scripts/v10_closed_loop.py

echo "[7/13] RL Shadow rerun"
python scripts/v10_rl_shadow_rerun.py

echo "[8/13] Resolve outcomes (auto-detect mode)"
python scripts/v10_resolve_outcomes.py --mode auto

echo "[9/13] Walk-forward 30j"
python scripts/v10_walkforward_30d.py

echo "[10/13] Fail analysis"
python scripts/v10_rl_fail_analysis.py

echo "[11/13] Bilan journalier"
python scripts/v10_daily_bilan.py

echo "[12/13] Night report + summary"
python scripts/v10_night_report.py
python scripts/v10_night_summary.py

echo "[13/13] Telegram alert bilan"
python scripts/v10_bilan_telegram_alert.py

TIMESTAMP_END=$(date '+%Y-%m-%d %H:%M:%S')
echo "=== CRON NUIT S24 END $TIMESTAMP_END — 13 étapes OK ==="
