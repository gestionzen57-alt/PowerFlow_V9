#!/usr/bin/env bash
# v10_night_cron_s24.sh — Cron nocturne V10 étendu Sprint 24
# Perplexity GitHub MCP — 2026-08-08 20:45 CEST
# 11 étapes : pipeline S23 + sprint_report + rl_fail_analysis
# Doctrine : R1-AGIR, R9-AUDIT, R10-CAPITAL

set -euo pipefail
CD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
cd "$CD"

TS=$(date -u +"%Y%m%d_%H%M%S")
LOG="logs/v10_night_s24_${TS}.log"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1

echo "=== V10 NIGHT CRON S24 — $TS ==="

_step() {
  local n="$1" label="$2"; shift 2
  echo "--- [Étape $n] $label ---"
  python "$@" && echo "[Étape $n] OK" || echo "[Étape $n] WARN (fail-open R6)"
}

_step  1  "night_report"         scripts/v10_night_report.py
_step  2  "closed_loop"          scripts/v10_closed_loop.py
_step  3  "shadow_promotion"     scripts/v10_shadow_promotion.py
_step  4  "risk_dashboard"       scripts/v10_risk_dashboard.py
_step  5  "weekly_summary"       scripts/v10_weekly_summary.py
_step  6  "r8_telegram_alert"    scripts/v10_r8_telegram_alert.py
_step  7  "r8_apply"             scripts/v10_learning_loop.py
_step  8  "resolve_outcomes"     scripts/v10_resolve_outcomes.py
_step  9  "daily_bilan"          scripts/v10_daily_bilan.py
_step 10  "sprint_report"        scripts/v10_sprint_report.py
_step 11  "rl_fail_analysis"     scripts/v10_rl_fail_analysis.py

echo "=== CRON S24 TERMINÉ ==="
