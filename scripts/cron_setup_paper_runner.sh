#!/usr/bin/env bash
# cron_setup_paper_runner.sh — Phase 17 motion CEO « EDGE FUND MAX ».
# Installe la tache cron Windows ou cron Linux pour v9_paper_runner.
#
# Usage :
#   bash scripts/cron_setup_paper_runner.sh install    # installe
#   bash scripts/cron_setup_paper_runner.sh status     # etat
#   bash scripts/cron_setup_paper_runner.sh remove     # supprime
#
# Cycle : 1 cycle toutes les 5 minutes (300s).
# Audit quotidien : 1 fois/jour a 23h55 UTC.

set -euo pipefail

ACTION="${1:-status}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/Scripts/python.exe"
RUNNER="$PROJECT_DIR/scripts/v9_paper_runner.py"
AUDIT="$PROJECT_DIR/scripts/v9_daily_paper_audit.py"
LOG_DIR="$PROJECT_DIR/data/logs"

mkdir -p "$LOG_DIR"

case "$ACTION" in
    install)
        echo "[install] Configuration du cron pour v9_paper_runner..."
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
            # Windows : utiliser schtasks
            TASK_NAME="V9PaperRunner"
            RUNNER_CMD="\"$PYTHON_BIN\" \"$RUNNER\" --loop 300"
            schtasks //create //tn "$TASK_NAME" //tr "$RUNNER_CMD" //sc minute //mo 5 //f \
                && echo "[install] Windows Task Scheduler OK : $TASK_NAME" \
                || echo "[install] ERREUR schtasks (lancer en admin)"

            # Audit quotidien 23h55
            AUDIT_CMD="\"$PYTHON_BIN\" \"$AUDIT\""
            schtasks //create //tn "V9DailyPaperAudit" //tr "$AUDIT_CMD" //sc daily //st 23:55 //f \
                && echo "[install] Daily audit OK : V9DailyPaperAudit 23:55" \
                || echo "[install] ERREUR schtasks audit"
        else
            # Linux/Mac : crontab
            CRON_LINE_5MIN="*/5 * * * * cd $PROJECT_DIR && $PYTHON_BIN $RUNNER --loop 300 >> $LOG_DIR/paper_runner.log 2>&1"
            CRON_LINE_DAILY="55 23 * * * cd $PROJECT_DIR && $PYTHON_BIN $AUDIT >> $LOG_DIR/paper_audit.log 2>&1"
            ( crontab -l 2>/dev/null | grep -v "v9_paper_runner"; echo "$CRON_LINE_5MIN"; echo "$CRON_LINE_DAILY" ) | crontab -
            echo "[install] crontab mis a jour :"
            crontab -l | grep v9_paper
        fi
        ;;
    status)
        echo "[status] V9 paper_runner cron status"
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
            schtasks //query //tn "V9PaperRunner" 2>&1 | head -5 || echo "  V9PaperRunner : non installe"
            schtasks //query //tn "V9DailyPaperAudit" 2>&1 | head -5 || echo "  V9DailyPaperAudit : non installe"
        else
            echo "  crontab :"
            crontab -l 2>/dev/null | grep v9_paper || echo "  aucune entree v9_paper"
        fi
        echo ""
        echo "[status] v9_paper_runner status live :"
        "$PYTHON_BIN" "$RUNNER" --status | head -10
        ;;
    remove)
        echo "[remove] Suppression du cron v9_paper_runner..."
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
            schtasks //delete //tn "V9PaperRunner" //f 2>&1 || true
            schtasks //delete //tn "V9DailyPaperAudit" //f 2>&1 || true
            echo "[remove] Windows Task Scheduler nettoye"
        else
            crontab -l 2>/dev/null | grep -v "v9_paper" | crontab -
            echo "[remove] crontab nettoye"
        fi
        ;;
    *)
        echo "Usage: $0 {install|status|remove}"
        exit 1
        ;;
esac