# ZCODE — Phase 13 : Wyckoff câblé dans decide_entry
**Branch** : `feat/v9-foundation-clean`
**Prérequis** : M4 (S23-A→D) ✅
**R10 IRON** : zéro ordre réel — `V9_EXECUTION_ENABLED` reste commenté
**Levier** : +WR direct — MARKUP/DISTRIBUTION non exploités dans le live

---

## Contexte

`v10_wyckoff_consolidated.py` est codé, testé (8 tests verts), exporté dans
`core/v10/__init__.py`, mais **jamais appelé** dans `v10_decision_pipeline.py`
ni dans `decide_entry`. Le système décide en aveugle sur la phase Wyckoff.

States possibles : `MARKUP` / `MARKDOWN` / `ACCUMULATION` / `DISTRIBUTION` / `UNKNOWN`

- **MARKUP** : marché en expansion haussière → renforcer BUY, résister SELL
- **MARKDOWN** : expansion baissière → renforcer SELL, résister BUY
- **ACCUMULATION** : compression avant hausse → BUY préféré, attente confirmée
- **DISTRIBUTION** : compression avant baisse → SELL préféré, attente confirmée
- **UNKNOWN** : R6 fail-open → signal inchangé

---

## Fichier cible

`core/v10/v10_decision_pipeline.py` — fonction `decide_entry(signal, candles, ...)`

---

## Action exacte

### Étape 1 — Import (en tête de fichier)
```python
from core.v10.v10_wyckoff_consolidated import get_wyckoff_state
```

### Étape 2 — Dans decide_entry(), après le bloc fractal, avant return
```python
# === WYCKOFF GATE (Phase 13) ===
try:
    wyckoff = get_wyckoff_state(candles)  # MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION/UNKNOWN
    action = _apply_wyckoff_gate(action, setup_level, wyckoff)
    cot["wyckoff_state"] = wyckoff
except Exception as e:
    logger.warning(f"[R6] wyckoff_gate failed: {e} — signal unchanged")
    cot["wyckoff_state"] = "UNKNOWN"
```

### Étape 3 — Ajouter la fonction helper dans le même fichier
```python
def _apply_wyckoff_gate(action: str, setup_level: str, wyckoff: str) -> str:
    """
    Wyckoff gate R6 fail-open.
    MARKUP   + SELL A2/A3 → downgrade A3 (WAIT)
    MARKDOWN + BUY  A2/A3 → downgrade A3 (WAIT)
    DISTRIBUTION    + BUY  A2/A3 → downgrade A3 (WAIT)
    ACCUMULATION    + SELL A2/A3 → downgrade A3 (WAIT)
    A1 jamais downgradé.
    UNKNOWN → signal inchangé (fail-open).
    """
    if wyckoff == "UNKNOWN" or setup_level == "A1":
        return action
    conflicts = {
        ("MARKUP",       "SELL"),
        ("MARKDOWN",     "BUY"),
        ("DISTRIBUTION", "BUY"),
        ("ACCUMULATION", "SELL"),
    }
    if (wyckoff, action) in conflicts and setup_level in ("A2", "A3"):
        return "WAIT"
    return action
```

---

## Tests à créer : `tests/test_v10_wyckoff_gate.py`

```python
# Minimum 6 tests :
# 1. MARKUP + SELL A2  → WAIT
# 2. MARKUP + SELL A1  → SELL (A1 protégé)
# 3. MARKDOWN + BUY A3 → WAIT
# 4. DISTRIBUTION + BUY A2 → WAIT
# 5. UNKNOWN + SELL A2 → SELL (fail-open)
# 6. exception get_wyckoff_state → signal original retourné (R6)
```

## Critères d'acceptation
- `pytest tests/test_v10_wyckoff_gate.py` → 6/6 verts
- `pytest core/v10/` → zéro régression
- `cot["wyckoff_state"]` présent dans chaque décision logguée

## Commit
```
feat(v10): Phase13 cable wyckoff_consolidated in decide_entry
```

---

## Règles absolues
- R6 fail-open : exception → signal inchangé, log WARNING
- A1 jamais downgradé par Wyckoff
- Aucun import core/v9/
- Tests verts avant push
