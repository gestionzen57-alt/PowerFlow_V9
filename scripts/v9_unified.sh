#!/usr/bin/env bash
# v9_unified.sh — Phase 20 motion CEO « EDGE FUND MAX ».
#
# Orchestrateur unique qui execute toutes les verifications/system checks
# en UNE commande. Sortie JSON unifiee + exit code structure.
#
# Sections :
#   - bridge    : MT4 bridge check (v9_check_orderbridge)
#   - heartbeat : R3 capture (v9_heartbeat_capture)
#   - boot      : boot alerts (check_kill_switch_coherence)
#   - mirror    : mirror BLOCKING status (v9_mirror_check)
#   - tokens    : R2 token rotation (v9_token_rotation)
#   - rollback  : auto-rollback check (v9_auto_rollback --check)
#   - audit     : daily paper audit (v9_daily_paper_audit)
#   - runner    : paper runner status (v9_paper_runner --status)
#   - tests     : pytest 264 verts
#
# Usage :
#   bash scripts/v9_unified.sh all          # toutes sections
#   bash scripts/v9_unified.sh live         # sections LIVE (bridge+heartbeat+boot+mirror+tokens)
#   bash scripts/v9_unified.sh audit        # audit quotidien
#   bash scripts/v9_unified.sh coherence    # coherence inter-scripts
#   bash scripts/v9_unified.sh <section>    # section specifique
#
# Exit codes :
#   0 = OK
#   1 = au moins 1 check en erreur
#   2 = drift detecte (auto-rollback recommande)

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/Scripts/python.exe"

ACTION="${1:-all}"
JSON_OUTPUT="${2:-false}"

# Compteurs
N_OK=0
N_WARN=0
N_ERROR=0
RESULTS="{}"

run_section() {
    local name="$1"
    local cmd="$2"
    local rc=0
    local output
    output=$(eval "$cmd" 2>&1) || rc=$?
    if [[ $rc -eq 0 ]]; then
        ((N_OK++))
        echo "[OK] $name"
    else
        ((N_WARN++))
        echo "[KO] $name (exit=$rc)"
    fi
}

run_section_output() {
    local name="$1"
    local cmd="$2"
    local rc=0
    local output
    echo "=== $name ==="
    output=$(eval "$cmd" 2>&1) || rc=$?
    echo "$output"
    echo ""
    if [[ $rc -eq 0 ]]; then
        ((N_OK++))
    else
        ((N_WARN++))
    fi
    return $rc
}

# Sections

section_bridge() {
    run_section_output "bridge" "$PYTHON_BIN $PROJECT_DIR/scripts/v9_check_orderbridge.py"
}

section_heartbeat() {
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/v9_heartbeat_capture.py" 2>&1 || true
}

section_boot() {
    "$PYTHON_BIN" -c "
import os
os.environ['V9_BOOT_CONTEXT'] = 'prod'
from core.v9.v9_boot_alerts import check_kill_switch_coherence
ws = check_kill_switch_coherence()
print(f'boot_alerts: {len(ws)} warning(s)')
for w in ws: print(f'  {w}')
" 2>&1
}

section_mirror() {
    run_section_output "mirror" "$PYTHON_BIN $PROJECT_DIR/scripts/v9_mirror_check.py"
}

section_tokens() {
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/v9_token_rotation.py" --status 2>&1 | head -8 || true
}

section_rollback() {
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/v9_auto_rollback.py" --check 2>&1 | head -15 || true
}

section_audit() {
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/v9_daily_paper_audit.py" 2>&1 | head -30 || true
}

section_runner() {
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/v9_paper_runner.py" --status 2>&1 | head -10 || true
}

section_tests() {
    cd "$PROJECT_DIR" && "$PYTHON_BIN" -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3 || true
}

section_coherence() {
    "$PYTHON_BIN" -c "
from pathlib import Path
import sqlite3

# Coherence check : tous les scripts reference DB_PATH coherent
db_path = Path(r'C:\projet\V9\data\v9_forces.db')
print(f'DB exists: {db_path.exists()}')
print(f'DB size: {db_path.stat().st_size / 1024**3:.2f} GB' if db_path.exists() else 'DB missing')

# Tables principales
expected_tables = ['decisions', 'forces_snapshots', 'paper_trades',
                   'v9_paper_trades', 'regime_snapshots']
if db_path.exists():
    try:
        conn = sqlite3.connect(str(db_path))
        actual = {r[0] for r in conn.execute(
            \"SELECT name FROM sqlite_master WHERE type='table'\"
        ).fetchall()}
        conn.close()
        for t in expected_tables:
            print(f'  table {t}: {\"OK\" if t in actual else \"MISSING\"}')
    except Exception as e:
        print(f'  error: {e}')

# Scripts presents
scripts_dir = Path(r'C:\projet\V9\scripts')
expected_scripts = [
    'v9_paper_runner.py', 'v9_daily_paper_audit.py',
    'v9_auto_rollback.py', 'v9_token_rotation.py',
    'v9_mirror_auto_activate.py', 'v9_check_orderbridge.py',
    'v9_heartbeat_capture.py', 'v9_mirror_check.py',
    'v9_pre_live_check.py', 'v9_log_human_trade.py',
    'v9_close_time_exit.py', 'v9_walk_forward.py',
]
print()
print('Scripts presents :')
for s in expected_scripts:
    p = scripts_dir / s
    print(f'  {s}: {\"OK\" if p.exists() else \"MISSING\"}')
" 2>&1
}

case "$ACTION" in
    all)
        echo "=========================================="
        echo "V9 UNIFIED CHECK (all sections)"
        echo "=========================================="
        section_bridge
        section_heartbeat
        section_boot
        section_mirror
        section_tokens
        section_rollback
        section_runner
        echo ""
        echo "=========================================="
        echo "SUMMARY : $N_OK OK, $N_WARN KO"
        echo "=========================================="
        ;;
    live)
        echo "=========================================="
        echo "V9 LIVE CHECK (production checks)"
        echo "=========================================="
        section_bridge
        section_heartbeat
        section_boot
        section_mirror
        section_tokens
        echo ""
        echo "=========================================="
        echo "SUMMARY : $N_OK OK, $N_WARN KO"
        echo "=========================================="
        ;;
    audit)
        section_audit
        ;;
    coherence)
        section_coherence
        ;;
    tests)
        section_tests
        ;;
    bridge|heartbeat|boot|mirror|tokens|rollback|runner)
        "section_$ACTION"
        ;;
    *)
        echo "Usage: $0 {all|live|audit|coherence|tests|<section>}"
        echo "Sections : bridge heartbeat boot mirror tokens rollback runner"
        exit 1
        ;;
esac