#!/usr/bin/env bash
# PowerFlow V9 — VPS bootstrap
#
# Démarre la chaîne de capture V9 sur un VPS frais. Suppose que le dépôt est
# cloné sur ${V9_ROOT:-/opt/v9} et que les dépendances Python 3.11+ (stdlib
# uniquement, voir docs/deployment/VPS_RUNBOOK.md) sont disponibles.
#
# Ne démarre PAS core.v9.agent_bus : ce module est une bibliothèque pure
# (publish/subscribe/poll sur data/v9_forces.db), pas un service — aucun
# `if __name__ == "__main__"`. Il est appelé en-process par les futurs
# consommateurs du bus (meta-agent, autres agents), pas exécuté à part.
set -euo pipefail

V9_ROOT="${V9_ROOT:-/opt/v9}"
cd "$V9_ROOT"

echo "=== V9 BOOTSTRAP ==="

echo "1. Vérification DB..."
ls -lh data/v9_forces.db

echo "2. Démarrage capture_server (port 31685)..."
mkdir -p logs
nohup python -m core.v9.capture_server >> logs/v9_capture.log 2>&1 &
echo $! > logs/v9_capture.pid
echo "   capture_server PID $(cat logs/v9_capture.pid)"

echo "3. Démarrage meta-agent (scan/10min, learn/60min)..."
nohup python scripts/v9_meta_agent.py --watch >> logs/v9_meta_agent.log 2>&1 &
echo $! > logs/v9_meta_agent.pid
echo "   meta-agent PID $(cat logs/v9_meta_agent.pid)"

echo "4. Crons actifs (Hermes) :"
hermes cron list || echo "   ATTENTION: CLI hermes indisponible ou aucun profil actif"

echo "=== V9 READY ==="
