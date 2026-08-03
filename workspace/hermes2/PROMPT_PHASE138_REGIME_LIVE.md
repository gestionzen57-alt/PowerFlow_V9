# PROMPT Hermes2 — Phase 138 Regime Live Detector (DOW × regime × vol)

> **Copy-paste ce prompt dans ta session Hermes (M3)**

---

## MISSION — Phase 138 : Regime Live Detector

**Hypothèse** : Le régime actuel est détecté uniquement via le pipeline.
Ajouter un détecteur **live** qui combine DOW + regime + volatilité pour
prédire le régime de la prochaine heure (utilisé pour pré-décision).

**Logique** :
- DOW influence le régime (mardi = baissier, mercredi = haussier GBPUSD, etc.)
- Vol spike → régime EXTENSION probable
- Vol calme → régime RETOUR_EQUILIBRE probable

**API** :
```python
def regime_live_detector_enabled() -> bool:
    """Kill switch V9_REGIME_LIVE_DETECTOR_ENABLED (defaut OFF)."""

def predict_next_regime(
    current_regime: str,
    utc_hour: int,
    utc_dow: int,
    vol_ratio: float,
    symbol: str = "GBPUSD",
) -> dict:
    """Predit le regime probable pour la prochaine heure.

    Returns:
      dict avec "predicted_regime", "confidence", "leviers", "factors".
    """
```

**Gain projeté** : 40-80 pips (pré-décision adaptative).

**Effort** : 1-2 jours.

## TRAVAIL

### 1. Module
**Fichier** : `core/v9/v9_regime_live_detector.py`

### 2. Kill switch dans kill_switches.py
```python
def regime_live_detector_enabled() -> bool:
    """Kill switch V9_REGIME_LIVE_DETECTOR_ENABLED — Phase 138.

    Defaut OFF (R25' strict motion CEO). R6 fail-open.
    """
    return get("V9_REGIME_LIVE_DETECTOR_ENABLED", "0") == "1"
```

### 3. .env
```bash
# === Phase 138 Regime Live Detector (2026-08-03) ===
# Code : core/v9/v9_regime_live_detector.py (NEW).
V9_REGIME_LIVE_DETECTOR_ENABLED=0
```

### 4. Tests
**Fichier** : `tests/test_v9_regime_live_detector.py` (min 6 tests)

Cas : Kill switch OFF, vol spike → EXTENSION, vol calme → RETOUR_EQUILIBRE,
DOW mardi GBPUSD → baissier, DOW mercredi GBPUSD → haussier, R6 fail-open.

### 5. Commit + push
```bash
cd C:/projet/V9
git add core/v9/v9_regime_live_detector.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_regime_live_detector.py
git commit -m "feat(v9): Phase 138 Regime Live Detector (DOW × regime × vol)"
git push origin feat/v9-foundation-clean
```

---

**Go. Tu as 1-2 jours. Sprint CEO mode « plein pouvoir » V4.**

*Prompt préparé par Hermes le 2026-08-03 07:30 UTC.*