#!/usr/bin/env bash
# v9_cron_48h.sh — Phase 38 motion CEO 48h autopilote.
#
# Installe un cron 48h pour la boucle de perfectionnement continu.
# Execute en boucle : quick_audit + alert_engine + auto_rollback check + post_mortem.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_DIR}/.venv/Scripts/python.exe"

CRON_TAG="V9_48H_PERFECTION"

echo "=========================================="
echo "PHASE 38 — CRON 48H AUTO-INSTALL"
echo "=========================================="
echo "Project dir : ${PROJECT_DIR}"
echo "Python      : ${PYTHON}"

# Fonction pour executer le daily perfection loop
DAILY_CRON="${CRON_TAG}_DAILY"
DAILY_CMD="${PYTHON} ${PROJECT_DIR}/scripts/v9_self_improving_loop.py --iterations 1 --no-tests"

# Fonction pour executer l'audit quotidien
AUDIT_CRON="${CRON_TAG}_AUDIT"
AUDIT_CMD="${PYTHON} ${PROJECT_DIR}/scripts/v9_quick_audit.py"

# Fonction pour les alertes
ALERT_CRON="${CRON_TAG}_ALERT"
ALERT_CMD="${PYTHON} ${PROJECT_DIR}/scripts/v9_alert_engine.py"

# Fonction post-mortem quotidien
POSTMORTEM_CRON="${CRON_TAG}_POSTMORTEM"
POSTMORTEM_CMD="${PYTHON} ${PROJECT_DIR}/scripts/v9_post_mortem.py"

# Installation cron Linux/Mac/WSL
if command -v crontab >/dev/null 2>&1; then
    echo ""
    echo "Installation cron Linux..."
    TMP_CRON=$(mktemp)
    crontab -l > "$TMP_CRON" 2>/dev/null || true
    # Supprimer anciennes entrees
    grep -v "${CRON_TAG}" "$TMP_CRON" > "${TMP_CRON}.new" || true
    mv "${TMP_CRON}.new" "$TMP_CRON"
    # Ajouter nouvelles
    echo "0 8 * * * ${DAILY_CRON} ${DAILY_CMD}" >> "$TMP_CRON"
    echo "0 23 * * * ${AUDIT_CRON} ${AUDIT_CMD}" >> "$TMP_CRON"
    echo "*/15 * * * * ${ALERT_CRON} ${ALERT_CMD}" >> "$TMP_CRON"
    echo "0 23 * * * ${POSTMORTEM_CRON} ${POSTMORTEM_CMD}" >> "$TMP_CRON"
    crontab "$TMP_CRON"
    rm "$TMP_CRON"
    echo "Cron Linux installé :"
    crontab -l | grep "${CRON_TAG}"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    echo ""
    echo "Installation cron Windows (Task Scheduler)..."
    # Planifier les taches via schtasks (single slash pour MSYS bash)
    # Daily perfection 8h
    schtasks /create /tn "${DAILY_CRON}" /tr "${DAILY_CMD}" /sc daily /st 08:00 /f
    # Audit 23h
    schtasks /create /tn "${AUDIT_CRON}" /tr "${AUDIT_CMD}" /sc daily /st 23:00 /f
    # Alert 15min
    schtasks /create /tn "${ALERT_CRON}" /tr "${ALERT_CMD}" /sc minute /mo 15 /f
    # Post-mortem 23h
    schtasks /create /tn "${POSTMORTEM_CRON}" /tr "${POSTMORTEM_CMD}" /sc daily /st 23:00 /f
    echo "Taches Windows installees."
    schtasks /query | grep "${CRON_TAG}" || true
else
    echo "OS non supporte pour cron."
    exit 1
fi

echo ""
echo "=========================================="
echo "CRON 48H INSTALLÉ"
echo "=========================================="
echo ""
echo "Pour desinstaller :"
echo "  crontab -l | grep -v '${CRON_TAG}' | crontab -"
echo "OU"
echo "  schtasks //delete //tn '${DAILY_CRON}' //f"
echo "  schtasks //delete //tn '${AUDIT_CRON}' //f"
echo "  schtasks //delete //tn '${ALERT_CRON}' //f"
echo "  schtasks //delete //tn '${POSTMORTEM_CRON}' //f"