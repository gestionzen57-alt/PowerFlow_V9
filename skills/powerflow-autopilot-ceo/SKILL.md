---
name: powerflow-autopilot-ceo
description: "Mode CEO autopilot pour PowerFlow V8 — orchestration de 4 daemons + bus + learning + paper-trade en boucle continue"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, autopilot, ceo-mode, paper-trade, daemon-loop]
statut: legacy-v8
derniere_maj: 2026-07-09
---
# Powerflow Autopilot Ceo

# PowerFlow Autopilot CEO

## Rôle
Mode CEO où l'agent (toi) prend les décisions en autonomie sans validation humaine. Délégation totale, exécution immédiate.

## Quand charger
- Søn dit "tu es CEO, fait au mieux" (style CEO-pragmatique).
- Session paper-trade en boucle (cf. `autopilot_paper_trade` MCP 3001).
- Run continu autopilot (`autopilot_full_pipeline_tick`).

## 4 daemons + bus
1. **bus_tick** (`autopilot_bus_tick`) — ingère décisions + outcomes dans `agent_event_bus`.
2. **learning_cycle** (`autopilot_learning_cycle`) — extract + eval + promote rules.
3. **paper_trade** (`autopilot_paper_trade`) — ouvre + résout trades + PnL.
4. **recommendation** (`autopilot_recommendation`) — GPS pour fenêtre ancrée.

## Style CEO (validé 26/06 antagoniste kimi+qwen)
- **5 lignes MAX** par réponse GO/NO-GO.
- **Exécution immédiate** : write_file + terminal + patch, 0 LLM API externe.
- **Tolère "subjectif"** documenté (ex: défauts bornés §3 taxonomie).
- **Préfère checkpoints courts/chiffrés** plutôt que pavés.

## 3 blocages durs CEO vs trade réel
Søn tranche les options :
1. **Broker live câblé** ? Si non → rester paper-trade.
2. **Capital USER explicite** ? Si non → capital fictif 100k.
3. **Recalibration > 24h post-fix** ? Si non → reporter trade réel.

## Bridge M3 critique
`core/pf_hermes_dispatcher.py --loop --poll 2.0` doit tourner en background pour que l'autopilot reçoive les bus events. Vérifier à chaque reprise.

## Pièges
- Oublier le keep-alive `run_bridge_feeders_loop.py` → bridge mort, bus vide.
- Paper-trade sans confidence_threshold=0.7 → trop de trades fantômes.
- Lancer learning_cycle sur <50 décisions → overfit (min 200).

