# Phase 13 Readiness — 15 SHADOW audités

- **Date** : généré par `v9_phase13_readiness.py`
- **Verdict global** : **PHASE_13_BLOCKED_NO_WINLOSS**
- **WIN/LOSS résolus** : 0 wins / 0 losses / 8365 open
- **Seuils R30** : ≥50 triggers, ≥60% hit_rate

## Verdict par principe

| Principe | kind | Conditions | Eval | Triggers | Résolus | Hit rate | Verdict |
|---|---|---|---|---|---|---|---|
| GRAMMAR_ABSORPTION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_ANTAGONISME | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_BREAK | grammar | OUI | 61589 | 0 | 0 | — | BLOCKED_NO_TRIGGER |
| GRAMMAR_COALITION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_CONTEXTE | grammar | OUI | 61589 | 707 | 0 | — | READY_STRUCTURAL |
| GRAMMAR_CROISEMENT | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_EXHAUSTION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_EXTENSION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_LEADER_FOLLOWER | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_LOCK | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_OPPOSITION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_PULLBACK | grammar | OUI | 61589 | 0 | 0 | — | BLOCKED_NO_TRIGGER |
| GRAMMAR_RESPIRATION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_SQUEEZE | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_TENSION | grammar | non | 61589 | 0 | 0 | — | INERT_NO_CONDITIONS |

## Compteurs verdict

- **INERT_NO_CONDITIONS** : 12
- **BLOCKED_NO_TRIGGER** : 2
- **READY_STRUCTURAL** : 1

## Légende

- `INERT_NO_CONDITIONS` : YAML conditions vides (classe C R30)
- `BLOCKED_NO_TRIGGER` : jamais déclenché, refactor YAML nécessaire
- `EARLY_TRIGGERS` : <50 triggers, attendre accumulation
- `READY_STRUCTURAL` : ≥50 triggers mais 0 WIN/LOSS résolu (bloqué data)
- `READY_FULL` : ≥50 triggers + hit_rate ≥ 60% (promotion possible)
- `READY_LOW_HIT_RATE` : ≥50 triggers + hit_rate < 60% (à analyser)

