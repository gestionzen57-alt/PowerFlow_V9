# Phase 13 Readiness — 14 SHADOW audités

- **Date** : généré par `v9_phase13_readiness.py`
- **Verdict global** : **PHASE_13_PARTIAL_NO_PROMOTABLE**
- **WIN/LOSS résolus** : 8321 wins / 49 losses / 20 open
- **Seuils R30** : ≥50 triggers, ≥60% hit_rate
- **Filtre pips** : |pips| ≥ 5.0 (HR filtré actif)

## Verdict par principe

| Principe | kind | Conditions | Eval | Triggers | Résolus | Hit rate | Hit rate filtré | Verdict |
|---|---|---|---|---|---|---|---|---|
| GRAMMAR_ABSORPTION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_ANTAGONISME | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_BREAK | grammar | OUI | 62772 | 1 | 0 | — | — (0) | EARLY_TRIGGERS |
| GRAMMAR_COALITION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_CROISEMENT | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_EXHAUSTION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_EXTENSION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_LEADER_FOLLOWER | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_LOCK | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_OPPOSITION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_PULLBACK | grammar | OUI | 62772 | 0 | 0 | — | — (0) | BLOCKED_NO_TRIGGER |
| GRAMMAR_RESPIRATION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_SQUEEZE | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |
| GRAMMAR_TENSION | grammar | non | 62772 | 0 | 0 | — | — (0) | INERT_NO_CONDITIONS |

## Compteurs verdict

- **INERT_NO_CONDITIONS** : 12
- **EARLY_TRIGGERS** : 1
- **BLOCKED_NO_TRIGGER** : 1

## Légende

- `INERT_NO_CONDITIONS` : YAML conditions vides (classe C R30)
- `BLOCKED_NO_TRIGGER` : jamais déclenché, refactor YAML nécessaire
- `EARLY_TRIGGERS` : <50 triggers, attendre accumulation
- `READY_STRUCTURAL` : ≥50 triggers mais 0 WIN/LOSS résolu (bloqué data)
- `READY_FULL` : ≥50 triggers + hit_rate ≥ 60% (promotion possible)
- `READY_LOW_HIT_RATE` : ≥50 triggers + hit_rate < 60% (à analyser)

