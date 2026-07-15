---
name: powerflow-autopilot-ceo
description: "Mode CEO autopilot pour PowerFlow V8 — orchestration de 4 daemons + bus + learning + paper-trade en boucle continue. Compatible R7/R22/R25'/R28 assouplis 2026-07-14."
version: 1.1.0
author: powerflow-m3-align
tags: [powerflow, autopilot, ceo-mode, paper-trade, daemon-loop, r7-assoupli, r25-assoupli, r28-assoupli]
statut: legacy-v8 (transférable en v9)
derniere_maj: 2026-07-14
note_chantier: aligne au HEAD 080fb3f (1277 verts + 2 skipped + 0 fail, 4 règles assouplies 2026-07-14)
---

# Powerflow Autopilot Ceo

# PowerFlow Autopilot CEO

## Rôle
Mode CEO où l'agent (toi) prend les décisions en autonomie sans validation humaine. Délégation totale, exécution immédiate.

## Compatibilité 2026-07-14 — 4 règles assouplies (DOCTRINE.md)

Le mode CEO autopilot est directement impacté par les 4 assouplissements
doctrinaux de la motion CEO Søn du 2026-07-14 :

- **R7** (zéro régression) : assoupli en « zéro régression **non
  justifiée** ». Toute régression de comportement doit être tracée
  dans DECISIONS_LOG. En mode autopilot, chaque décision de l'agent
  qui modifie un comportement doit être justifiée (template R7 dans
  `powerflow-doctrine-evolution`).

- **R25'** (promotion SHADOW→ACTIVE) : assoupli « sauf mandat CEO
  explicite contraire ». En mode CEO autopilot, quand Søn dit « go
  global » (ex: « go activer tous », « go r28 », « go la suite »),
  les promotions SHADOW→ACTIVE dans le périmètre autorisé sont
  automatiques. C'est précisément ce qui s'est passé dans le commit
  `5049d48` du 14/07 09:43.

- **R22** (1 session = 1 périmètre) : assoupli « sauf chantier complexe
  découpé en sous-unités ». En mode autopilot, les chantiers longs
  (P3-CONSUME 6-10h) peuvent être livrés en plusieurs commits
  atomiques sous-unités.

- **R28** (Hermes opérateur git unique) : assoupli « sauf instruction
  directe et explicite de Søn ». En mode CEO autopilot, le push direct
  est la norme (motion CEO « go r28 » = délégation explicite).

Référence : `docs/DOCTRINE.md` (c560506) + DECISIONS_LOG §2026-07-14.

## Quand charger
- Søn dit "tu es CEO, fait au mieux" (style CEO-pragmatique).
- Session paper-trade en boucle (cf. `autopilot_paper_trade` MCP 3001).
- Run continu autopilot (`autopilot_full_pipeline_tick`).
- Søn donne un "go" global sur un périmètre de chantiers.

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

Note 2026-07-14 : ces 3 blocages sont des **garde-fous opérationnels**,
pas des règles doctrinales. Ils ne sont pas affectés par les
assouplissements R7/R22/R25'/R28. Le trade réel reste un geste
fondateur séparé (Phase 12, V9_EXECUTION_ENABLED=0 par défaut).

## Bridge M3 critique
`core/pf_hermes_dispatcher.py --loop --poll 2.0` doit tourner en background pour que l'autopilot reçoive les bus events. Vérifier à chaque reprise.

## Pièges
- Oublier le keep-alive `run_bridge_feeders_loop.py` → bridge mort, bus vide.
- Paper-trade sans confidence_threshold=0.7 → trop de trades fantômes.
- Lancer learning_cycle sur <50 décisions → overfit (min 200).
- R25' assoupli : ne pas abuser des promotions automatiques. Une motion
  « go global » couvre un périmètre explicite, pas tout. Toujours
  tracer dans DECISIONS_LOG.
- R7 assoupli : toute régression non documentée = violation. Si un
  comportement autopilot change sans entrée DECISIONS_LOG explicative,
  c'est une régression silencieuse interdite.
