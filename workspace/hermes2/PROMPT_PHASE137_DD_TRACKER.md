# PROMPT Hermes2 — Phase 137 Adaptive Drawdown Tracker

> **Copy-paste ce prompt dans ta session Hermes (M3)**
> Chantier Hermes2 = branche `feat/v9-foundation-clean` (push autorisé).

---

## CONTEXTE (lire en premier)

HEAD actuel : `83677a2`. **Lire** : `workspace/hermes2/CONTEXT_HANDBOOK.md`.

## MISSION — Phase 137 : Adaptive Drawdown Tracker

**Hypothèse** : Le DD portfolio actuel (via `v9_drawdown_protector.py`) est
uniforme. Affiner par **contexte** (vol × regime × session) : en haute
volatilité, le DD acceptable peut être plus large (bruit normal), en
basse volatilité un DD de -50pips doit être plus suspect.

**Logique adaptative** :
```python
dd_acceptable = DD_BASE * vol_multiplier * regime_multiplier * session_multiplier
```
- `vol_multiplier` : ×1.5 si vol spike (ratio ≥2.0), ×0.7 si calme
- `regime_multiplier` : ×1.2 si CASSURE (volatilité structurelle), ×0.8 si RETOUR_EQUILIBRE
- `session_multiplier` : ×0.5 si asie (liquidité basse), ×1.0 si overlap/london

**Audit SQL live attendu** : distribution DD par contexte (vol × regime × session).

**Gain projeté** : 80-150 pips (réduction faux positifs HALT).

**Effort** : 2 jours. **Risque** : faible (R2 additif, R6 fail-open).

## TRAVAIL DEMANDÉ

### 1. Module NEW (R2 additif)
**Fichier** : `core/v9/v9_adaptive_dd_tracker.py`

API :
```python
def adaptive_dd_tracker_enabled() -> bool:
    """Kill switch V9_ADAPTIVE_DD_TRACKER_ENABLED (defaut OFF, R25')."""

def compute_adaptive_dd_threshold(
    dd_base: float,
    vol_ratio: float = 1.0,
    regime: str = "RETOUR_EQUILIBRE",
    session: str = "overlap",
) -> dict:
    """Retourne le seuil DD adaptatif selon contexte.

    Returns:
      dict avec "dd_threshold", "vol_mult", "regime_mult", "session_mult",
      "active", "leviers".
    """

def track_drawdown(
    dd_current: float,
    vol_ratio: float,
    regime: str,
    session: str,
    dd_base: float = -100.0,
) -> dict:
    """Verifie si le DD actuel depasse le seuil adaptatif.

    Returns:
      dict avec "halt", "threshold", "current", "margin", "leviers".
    """
```

### 2. Kill switch dans core/v9/kill_switches.py
```python
def adaptive_dd_tracker_enabled() -> bool:
    """Kill switch V9_ADAPTIVE_DD_TRACKER_ENABLED — Phase 137.

    Active le tracker DD adaptatif par contexte (vol × regime × session).
    Defaut OFF (R25' strict motion CEO).
    """
    return get("V9_ADAPTIVE_DD_TRACKER_ENABLED", "0") == "1"
```

### 3. .env
```bash
# === Phase 137 Adaptive DD Tracker (2026-08-03) ===
# Code : core/v9/v9_adaptive_dd_tracker.py (NEW).
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_ADAPTIVE_DD_TRACKER_ENABLED=0
```

### 4. Tests
**Fichier** : `tests/test_v9_adaptive_dd_tracker.py`

Cas minimum 6 :
1. Kill switch OFF → pass-through
2. Vol spike × DD = adapt threshold ×1.5
3. Regime CASSURE → ×1.2
4. Session asie → ×0.5
5. Combinaison : spike × CASSURE × asie = ×1.5 × ×1.2 × ×0.5 = ×0.9
6. track_drawdown : halt True si dd_current < threshold

### 5. Commit atomique + push
```bash
cd C:/projet/V9
git add core/v9/v9_adaptive_dd_tracker.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_adaptive_dd_tracker.py
git commit -m "feat(v9): Phase 137 Adaptive DD Tracker (vol × regime × session)"
git push origin feat/v9-foundation-clean
```

## RÈGLES DOCTRINE (RAPPEL)

- R2 additif, R6 fail-open, R7 tests verts (min 6), R14 git verite,
  R22 sous-unite unique, R25' motion CEO, R26 DECISIONS_LOG,
  R28 Hermes2 push autorise.

## ANTI-PATTERNS

- ❌ Modifier `v9_drawdown_protector.py` (existant, R2 strict).
- ❌ Inventer des chiffres.
- ❌ Commit sans tests.

---

**Go. Tu as 2 jours. Sprint CEO mode « plein pouvoir » V4.**

*Prompt préparé par Hermes le 2026-08-03 07:30 UTC.*