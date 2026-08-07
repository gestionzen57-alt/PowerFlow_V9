# ZCODE — M4 : Sprint 23 Quant Upgrade
**Branch** : `feat/v9-foundation-clean`  
**HEAD actuel** : `390a815`  
**Tests actuels** : 1270 verts / 5793 collected  
**Prérequis** : M1 ✅ M2 ✅ M3 ✅  
**R10 IRON** : zéro ordre réel — `V9_EXECUTION_ENABLED` reste commenté  

---

## Contexte Sprint 23

Les Sprints 2–4 sont **déjà livrés** dans le repo (v10_regime_hmm, v10_smc, v10_ict_ote,
v10_filter_compositor, v10_vol_forecast, v10_wyckoff_consolidated).  
**Ce qui manque** (Sprint 23 = câblage + intégration orchestrateur) :

1. Le `v10_filter_compositor.py` n'est pas encore appelé par l'orchestrateur principal
2. Le `v10_vol_forecast.py` n'est pas encore utilisé pour dimensionner SL/TP live
3. Le backtest `v10_public_strategy_backtest.py` tourne en script standalone → à connecter au dashboard API (endpoint `/api/v1/backtest/summary`)
4. `CACHE_BOARD.md` et `DEBT_TRACKER.md` doivent être mis à jour post-Sprint-23

---

## DÉCOUPAGE M4 — 4 sous-tâches atomiques pour Nemotron

> ⚡ **Règle Nemotron** : une sous-tâche = une requête = 1-2 fichiers max modifiés.  
> Ne pas regrouper S23-A + S23-B dans la même requête.

---

### S23-A — Câbler `v10_filter_compositor` dans l'orchestrateur

**Fichier cible** : `core/v10/v10_orchestrator.py` (ou équivalent orchestrateur principal)  
**Action** :
```python
# AVANT (pseudocode actuel) :
signal = base_signal_builder(candles, pair)

# APRÈS — insérer après construction du signal de base :
from core.v10.v10_filter_compositor import apply_filter_chain
signal = apply_filter_chain(signal, candles, pair)
# apply_filter_chain : session + ICT OTE + SMC + regime → modifie setup_level + trace R9
```

**Règles** :
- R6 fail-open : si `apply_filter_chain` lève une exception → log WARNING, retourner signal original inchangé
- Ne jamais bloquer l'émission d'un signal A1
- Ajouter champ `filter_trace: dict` dans l'objet signal retourné (pour R9 audit)

**Tests à créer** : `tests/test_v10_orchestrator_filter.py`
```python
# Minimum 4 tests :
# 1. signal A2 LONDON → upgrade possible via SMC/OTE
# 2. signal A3 OUTSIDE → downgrade bloqué si A1
# 3. exception dans filter_chain → signal original retourné (fail-open)
# 4. champ filter_trace présent dans output
```

**Critères d'acceptation** :
- `pytest tests/test_v10_orchestrator_filter.py` → 4/4 verts
- `pytest core/v10/` → zéro régression
- Aucun import circulaire

---

### S23-B — Intégrer `v10_vol_forecast` pour SL/TP dynamiques

**Fichier cible** : `core/v10/v10_risk_manager.py` (ou module risk existant)  
**Action** :
```python
from core.v10.v10_vol_forecast import sl_tp_from_vol, forecast_vol_garch

# Dans compute_sl_tp(signal, candles) :
vol = forecast_vol_garch(candles)           # GARCH → fallback EWMA si arch absent
sl, tp = sl_tp_from_vol(signal, vol)        # dimensionnement dynamique
# Remplace les SL/TP statiques actuels
```

**Règles** :
- Si `arch` non installé → fallback EWMA silencieux (R6)
- Conserver les anciens SL/TP comme fallback ultime si vol_forecast retourne None
- Logger le mode utilisé : GARCH / EWMA / STATIC

**Tests à créer** : `tests/test_v10_risk_vol_integration.py`
```python
# Minimum 3 tests :
# 1. SL/TP dynamiques calculés avec GARCH (mock arch si non dispo)
# 2. fallback EWMA si arch absent → SL/TP non-None
# 3. fallback STATIC si tout échoue → SL/TP non-None
```

**Critères d'acceptation** :
- `pytest tests/test_v10_risk_vol_integration.py` → 3/3 verts
- `pytest core/v10/` → zéro régression
- `grep "STATIC" logs/` → 0 occurrences en mode normal (GARCH ou EWMA attendu)

---

### S23-C — Endpoint `/api/v1/backtest/summary` dans le dashboard API

**Fichier cible** : `scripts/v10_dashboard_api.py`  
**Action** : Ajouter un endpoint FastAPI qui lit `reports/v10_public_strategy_backtest_20260805.json`

```python
@app.get("/api/v1/backtest/summary")
async def backtest_summary():
    """Résultats backtest public strategies — Kill Zones edge."""
    path = Path("reports/v10_public_strategy_backtest_20260805.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backtest report not found")
    data = json.loads(path.read_text())
    return {
        "source": "v10_public_strategy_backtest",
        "date": "2026-08-05",
        "base_wr": data.get("base_wr", 0.332),
        "kill_zone_results": data.get("kill_zone_results", []),
        "signals_total": data.get("n_signals", 8822)
    }
```

**Ajouter aussi** dans `/dashboard/v10` : section "Kill Zone Edge" avec tableau HTML
(NY +20pts, LONDON +11.5pts, ASIAN +6.7pts, OUTSIDE −9.8pts) — statique si endpoint absent.

**Tests à créer** : `tests/test_v10_dashboard_backtest.py`
```python
# Minimum 2 tests (TestClient FastAPI) :
# 1. GET /api/v1/backtest/summary → 200, champ kill_zone_results présent
# 2. GET /api/v1/backtest/summary (fichier absent) → 404
```

**Critères d'acceptation** :
- `pytest tests/test_v10_dashboard_backtest.py` → 2/2 verts
- Endpoint répond en < 200ms

---

### S23-D — Mise à jour CACHE_BOARD.md + DEBT_TRACKER.md post-Sprint-23

**Fichier cible 1** : `docs/V10/CACHE_BOARD.md`  
**Fichier cible 2** : `docs/V10/DEBT_TRACKER.md` (ou chemin équivalent)  

**Action CACHE_BOARD.md** — Mettre à jour :
```markdown
## État courant — Sprint 23
- HEAD : <nouveau SHA après commit S23>
- Tests : <nouveau total> verts
- Modules actifs : v10_filter_compositor ✅ câblé orchestrateur
- Modules actifs : v10_vol_forecast ✅ SL/TP dynamiques
- Endpoint backtest : /api/v1/backtest/summary ✅
- Kill Zone edge NY : +20.0 pts WR vs base 33.2%
- RL Shadow gates CEO : GBPUSD ✅ AUDUSD ✅ (2/4)
- Sigma Oracle M30 : 53% recovery (8/15 signaux)
```

**Action DEBT_TRACKER.md** — Ajouter/clore :
```markdown
| D07 | filter_compositor non câblé orchestrateur | ✅ RÉSOLUE (S23-A) |
| D08 | SL/TP statiques (vol_forecast non intégré) | ✅ RÉSOLUE (S23-B) |
| D09 | Endpoint backtest absent dashboard          | ✅ RÉSOLUE (S23-C) |
```

**Critère d'acceptation** :
- `grep "S23-A\|S23-B\|S23-C" docs/V10/DEBT_TRACKER.md` → 3 lignes RÉSOLUES
- SHA dans CACHE_BOARD.md = SHA réel du commit

---

## Ordre d'exécution pour Zcode

```
S23-A → S23-B → S23-C → S23-D
```

Chaque sous-tâche = 1 commit séparé avec message :
- `feat(v10): S23-A cable filter_compositor in orchestrator`
- `feat(v10): S23-B integrate vol_forecast for dynamic SL/TP`
- `feat(v10): S23-C add /api/v1/backtest/summary endpoint`
- `docs: S23-D update CACHE_BOARD and DEBT_TRACKER post-Sprint23`

---

## Commande de vérification finale

```bash
pytest core/v10/ tests/test_v10_orchestrator_filter.py \
       tests/test_v10_risk_vol_integration.py \
       tests/test_v10_dashboard_backtest.py -v --tb=short
# Attendu : 1270 + 9 nouveaux = ~1279 verts, 0 échecs
```

---

## Règles absolues (rappel R10)

- `V9_EXECUTION_ENABLED` reste commenté — aucun ordre réel
- R6 fail-open sur tous les nouveaux modules
- Aucun import circulaire dans core/v10/
- Tests avant push — jamais de code non testé sur feat/v9-foundation-clean
