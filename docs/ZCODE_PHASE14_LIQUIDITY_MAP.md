# ZCODE — Phase 14 : Liquidity Map intégrée dans compose_filters
**Branch** : `feat/v9-foundation-clean`
**Prérequis** : Phase 13 ✅
**R10 IRON** : zéro ordre réel — `V9_EXECUTION_ENABLED` reste commenté
**Levier** : précision d'entrée — éviter les pièges institutionnels

---

## Contexte

`v10_liquidity_map.py` (37KB, le plus grand module du repo) détecte :
- **Equal Highs/Lows** : zones où les stops retail sont concentrés
- **Order Blocks institutionnels** : dernière bougie avant un mouvement fort
- **Liquidity Voids** : zones de prix non testées (magnétiques)
- **BSL/SSL** : Buy-Side Liquidity / Sell-Side Liquidity

Il est **complètement orphelin** — aucun caller dans le pipeline.
L'objectif : éviter les entrées devant une zone de liquidité majeure
(le marché va la tester AVANT de continuer dans notre sens).

---

## Fichier cible

`core/v10/v10_filter_compositor.py` — fonction `compose_filters(signal, candles, pair)`

---

## Action exacte

### Étape 1 — Lire l'API de v10_liquidity_map.py
Avant de coder, lire les fonctions exportées de `v10_liquidity_map.py`.
Identifier la fonction principale — probablement `compute_liquidity_map(candles)`
ou `get_liquidity_context(candles, price)` — et ses champs de retour.

### Étape 2 — Import dans filter_compositor.py
```python
try:
    from core.v10.v10_liquidity_map import get_liquidity_context
    _LIQUIDITY_MAP_AVAILABLE = True
except ImportError:
    _LIQUIDITY_MAP_AVAILABLE = False
```

### Étape 3 — Ajouter après le bloc SMC dans compose_filters()
```python
# === LIQUIDITY MAP FILTER (Phase 14) ===
if _LIQUIDITY_MAP_AVAILABLE:
    try:
        liq = get_liquidity_context(candles, current_price)
        signal = _apply_liquidity_filter(signal, liq)
        signal["liquidity_context"] = liq.get("summary", "UNKNOWN")
    except Exception as e:
        logger.warning(f"[R6] liquidity_map failed: {e} — signal unchanged")
        signal["liquidity_context"] = "UNAVAILABLE"
```

### Étape 4 — Helper filter
```python
def _apply_liquidity_filter(signal: dict, liq: dict) -> dict:
    """
    Liquidity filter R6 fail-open.
    Si le prix actuel est DEVANT une zone BSL/SSL majeure (distance < threshold) :
      → BUY devant BSL  : downgrade A2→A3 (le marché va purger les stops avant)
      → SELL devant SSL : downgrade A2→A3
    A1 jamais downgradé.
    """
    if not liq or signal.get("setup_level") == "A1":
        return signal
    # Adapter selon l'API réelle de get_liquidity_context
    in_liquidity_trap = liq.get("in_bsl_zone") or liq.get("in_ssl_zone", False)
    if in_liquidity_trap and signal.get("setup_level") in ("A2", "A3"):
        signal["setup_level"] = "A3"  # downgrade
        signal["liquidity_trap"] = True
    return signal
```

> ⚠️ **Important** : adapter l'API selon ce que tu trouves dans v10_liquidity_map.py.
> Si les noms de champs diffèrent, utiliser les vrais noms. Ne pas inventer.

---

## Tests à créer : `tests/test_v10_liquidity_filter.py`

```python
# Minimum 5 tests :
# 1. Prix devant BSL + BUY A2  → A3 (downgrade)
# 2. Prix devant SSL + SELL A2 → A3 (downgrade)
# 3. BUY A1 devant BSL         → A1 (protégé)
# 4. Prix hors zone             → signal inchangé
# 5. exception get_liquidity_context → signal inchangé (R6)
```

## Critères d'acceptation
- `pytest tests/test_v10_liquidity_filter.py` → 5/5 verts
- `pytest core/v10/` → zéro régression
- `signal["liquidity_context"]` présent dans chaque décision
- `grep "liquidity_trap" reports/v10_live_decision_latest.json` → visible après 1 run

## Commit
```
feat(v10): Phase14 integrate liquidity_map in compose_filters
```

---

## Règles absolues
- Adapter l'API aux vrais champs de v10_liquidity_map.py — lire avant de coder
- R6 fail-open : exception → signal inchangé
- A1 jamais downgradé
- Aucun import core/v9/
- Tests verts avant push
