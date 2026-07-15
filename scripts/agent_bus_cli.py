#!/usr/bin/env python
"""agent_bus_cli.py — wrapper CLI pour les subagents IA (ZCode/Hermes/Claude CLI).

Usage depuis un subagent :
  python scripts/agent_bus_cli.py poll <profile> [--source zcode|hermes|claude-cli]
  python scripts/agent_bus_cli.py publish <profile> <event_type> <json_payload>
  python scripts/agent_bus_cli.py pending [--limit 20]
  python scripts/agent_bus_cli.py stats [--hours 24]
  python scripts/agent_bus_cli.py setup-all

Exemples :
  # capture-ops vérifie les alertes du pipeline
  python scripts/agent_bus_cli.py poll capture-ops --source zcode

  # calib-analyst publie une proposition de seuil
  python scripts/agent_bus_cli.py publish calib-analyst threshold_proposed '{"metric":"ANTAGONISM","value":0.15}'

  # Voir tous les événements en attente
  python scripts/agent_bus_cli.py pending

  # Stats du bus
  python scripts/agent_bus_cli.py stats
"""
import sys
import os

# Ajoute le root du projet au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.v9.agent_bus_bridge import main

if __name__ == "__main__":
    main()