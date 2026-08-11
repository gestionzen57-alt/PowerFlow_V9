#!/usr/bin/env bash
# v10_edge_shadow_live.sh — Mesure live de l'edge OVERLAP (résolution des trades
# ouverts + agrégation). Cron no_agent, stdout-only. Zéro ordre (R10).
set -uo pipefail
cd /c/projet/V9 || exit 2

# Rejouer l'edge (track record) + résoudre les signaux
python scripts/v10_shadow_edge_overlap.py --replay 2>/dev/null | tail -8
