# ZCODE — Phase 15 : behavior_context → orchestrateur signal
**Branch** : `feat/v9-foundation-clean`
**Prérequis** : Phase 14 ✅
**R10 IRON** : zéro ordre réel — `V9_EXECUTION_ENABLED` reste commenté
**Levier** : cognitif — 78 652 comportements appris non exploités en temps réel

---

## Contexte

Le registre `v10_behavior_registry.py` contient **78 652 comportements** appris
(Phase Cognitive Continuum). Chaque comportement encode :
- paire + timeframe + régime
- fidélité observée (linéaire + extrême P90/P10)
- WR historique par contexte
- drift détecté

Ces données sont utilisées par le Cortex et le learning_continuum, mais
**jamais injectées dans `v10_orchestrator.compute_signal_level()`** au moment
de décider du setup_level. C'est le levier cognitif le plus puissant
non encore exploité : le système a de la mémoire mais ne la consulte pas
quand il décide.

---

## Fichier cible principal

`core/v10/v10_orchestrator.py` — méthode `compute_signal_level(pair, tf, bars)`

---

## Action exacte

### Étape 1 — Import
```python
from core.v10.v10_behavior_registry import BehaviorRegistry
```

### Étape 2 — Initialisation lazy dans l'orchestrateur
```python
# Dans __init__ de l'orchestrateur (ou au niveau module) :
try:
    _behavior_registry = BehaviorRegistry()
    _BEHAVIOR_REGISTRY_AVAILABLE = True
except Exception:
    _behavior_registry = None
    _BEHAVIOR_REGISTRY_AVAILABLE = False
```

### Étape 3 — Dans compute_signal_level(), après le calcul du setup_level initial
```python
# === BEHAVIOR CONTEXT GATE (Phase 15) ===
if _BEHAVIOR_REGISTRY_AVAILABLE and _behavior_registry:
    try:
        ctx = _behavior_registry.query_coherence(
            pair=pair,
            timeframe=tf,
            timeframes=["M30", "H1", "H4"]  # filtrer M5/M15 (biais volume)
        )
        setup_level = _apply_behavior_gate(setup_level, ctx)
        signal_meta["behavior_context"] = ctx.get("summary", "UNKNOWN")
        signal_meta["behavior_wr"]      = ctx.get("win_rate", None)
    except Exception as e:
        logger.warning(f"[R6] behavior_gate failed: {e} — signal unchanged")
        signal_meta["behavior_context"] = "UNAVAILABLE"
```

### Étape 4 — Helper gate
```python
def _apply_behavior_gate(setup_level: str, ctx: dict) -> str:
    """
    Behavior context gate R6 fail-open.
    Règles :
    - WR historique < 0.35 sur paire+TF → downgrade A2→A3
    - Drift détecté (ctx["drift"] == True) + setup A2 → downgrade A3
    - WR >= 0.55 + setup A3 → upgrade A3→A2 (bonus cognitif)
    - A1 jamais modifié.
    - ctx None ou "UNKNOWN" → fail-open, signal inchangé.
    """
    if not ctx or setup_level == "A1":
        return setup_level
    wr  = ctx.get("win_rate")
    drift = ctx.get("drift", False)
    if wr is None:
        return setup_level
    if drift and setup_level == "A2":
        return "A3"
    if wr < 0.35 and setup_level in ("A2", "A3"):
        return "A3"
    if wr >= 0.55 and setup_level == "A3":
        return "A2"  # upgrade cognitif
    return setup_level
```

> ⚠️ **Adapter** : lire l'API réelle de `query_coherence` dans
> `v10_behavior_registry.py` avant de coder. Les champs `win_rate`, `drift`,
> `summary` doivent correspondre aux vrais champs retournés.

---

## Tests à créer : `tests/test_v10_behavior_gate.py`

```python
# Minimum 7 tests :
# 1. WR 0.28 + A2           → A3 (downgrade)
# 2. WR 0.28 + A1           → A1 (protégé)
# 3. drift=True + A2        → A3
# 4. WR 0.60 + A3           → A2 (upgrade cognitif)
# 5. WR 0.45 + A2           → A2 (zone neutre, inchangé)
# 6. ctx=None               → signal inchangé (fail-open)
# 7. exception query_coherence → signal inchangé (R6)
```

## Critères d'acceptation
- `pytest tests/test_v10_behavior_gate.py` → 7/7 verts
- `pytest core/v10/` → zéro régression
- `signal_meta["behavior_context"]` présent dans les décisions logguées
- `signal_meta["behavior_wr"]` non-None sur au moins EURUSD/GBPUSD M30 et H1
  (paires avec historique suffisant)

## Commit
```
feat(v10): Phase15 inject behavior_context in orchestrator signal
```

---

## Vérification finale (après Phase 15)

```bash
pytest core/v10/ tests/test_v10_wyckoff_gate.py \
       tests/test_v10_liquidity_filter.py \
       tests/test_v10_behavior_gate.py -v --tb=short
# Attendu : ~1279 (M4) + 18 nouveaux = ~1297 verts, 0 échecs
```

---

## Vision architecturale post-Phase 15

Après les 3 phases, le pipeline de décision live sera :

```
Bars live (7 TF)
    ↓
Force + Structure + Context
    ↓
Orchestrator compute_signal_level
    ├── [NEW P15] behavior_context gate (78K patterns)
    ↓
compose_filters (filter_compositor)
    ├── session filter
    ├── ICT OTE (Kill Zones + Fibonacci)
    ├── SMC (BOS/MSS/OB/FVG)
    ├── HMM Regime (5 états)
    └── [NEW P14] liquidity_map filter
    ↓
decide_entry
    ├── fractal_context (Phase 12)
    ├── [NEW P13] wyckoff_gate
    ├── risk_shield R10
    └── edge_selector (WR≥50%, n≥30)
    ↓
Decision BUY/SELL/WAIT + lot
    ↓
Telegram + decision_log + paper_trader
```

**Résultat attendu** : chaque décision live passera par
6 couches de filtrage contextualisé au lieu de 3 actuellement.
Le système ne fera plus une seule entrée sans avoir consulté :
la structure de marché (SMC), le régime (HMM), la session (ICT),
la liquidité institutionnelle (LiqMap), la phase Wyckoff,
et ses propres 78K comportements mémorisés.

---

## Règles absolues
- Lire l'API réelle avant de coder (ne pas inventer les champs)
- R6 fail-open sur tout nouveau gate
- A1 jamais downgradé
- timeframes=["M30","H1","H4"] dans query_coherence (jamais M5/M15)
- Tests verts avant push
- Aucun import core/v9/
