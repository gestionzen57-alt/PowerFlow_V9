# SKILL — Checkpoint Rapide V9

**Version** : 2026-07-18 (resync HEAD 26b0070)

---

## Template checkpoint post-session

```markdown
# CHECKPOINT — [DATE] [TITRE]

**HEAD** : [sha]
**Branche** : feat/v9-foundation-clean
**Tests** : [N]/[N] verts
**Date** : [ISO]

## Livré
- [liste des commits et modules]

## Kill switches actifs
- V9_GBPUSD_LONG_ONLY=1
- V9_BEAR_PERCEPTION_ENABLED=0 (SHADOW)
- V9_EXECUTION_ENABLED=0 (INTERDIT)

## Performance
- WR haussier GBPUSD : [%] ([N] trades)
- WR baissier GBPUSD : [%] → long_only actif

## Prochaine action
- [action P0]

## Gelé
- Phase 10 fédération
- Phase 12 exécution
```

## Checkpoint actuel (HEAD 26b0070 — 18/07/2026)

**HEAD** : `26b0070` — fix(telegram) + LLM OpenRouter + rate-limit HITL persistant
**Tests** : 250/250 verts
**Kill switches** : LONG_ONLY=1, BEAR_PERCEPTION=0 SHADOW, EXECUTION=0 INTERDIT
**WR haussier** : 100% (1088 trades)
**Prochaine action P0** : restart capture server dimanche 22h UTC (marché fermé weekend)
**Phase** : B — validation shadow, en attente réouverture marché
