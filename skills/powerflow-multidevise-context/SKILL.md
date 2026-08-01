---
name: powerflow-multidevise-context
description: "Trade mono-symbole, study multi-device — pattern pour calculer un contexte synthétique live à partir de N forces devises (ou N data points d'un même snapshot). Charge quand Søn parle de multidevise, leader/follower devise, risk_on/risk_off, risk_regime, AUD/NZD forts, contexte macro, qui mène le marché, ou 'trade GBPUSD en étudiant les autres devises'. Couvre la classe de modules qui prennent un snapshot (M1/M5/etc) de N forces, dérivent des indicateurs synthétiques (leader, spread, regime), et les exposent via MCP live."
version: 1.0.0
author: Minimax-M3
tags: [powerflow, multidevise, leader, follower, risk-regime, macro-context, trade-mono-study-multi, 8-devises, AUD-NZD, context-synthesis, live-mcp]
related_skills: [powerflow-window-anchor, powerflow-auto-doc]
statut: actif-v9
derniere_maj: 2026-07-31
---
# PowerFlow Multidevise Context — Pattern "trade mono, study multi"

Skill à levier pour la classe de modules qui calculent un **contexte synthétique live** à partir d'un snapshot de **N forces** (8 devises dans le cas canonique). Le pattern est générique — il marche pour N'importe quel N (8 devises, 6 secteurs, 10 indices, etc.) tant qu'on a un snapshot en DB.

## Quand s'activer

- Mots-clés : "multidevise", "leader devise", "follower", "qui mène le marché", "risk_on", "risk_off", "safe_haven", "AUD fort", "USD faible", "8 devises", "macro context", "trade GBPUSD en étudiant les autres devises", "contexte de décision"
- Contexte : chantier qui trade **un seul actif** mais a besoin du **contexte macro** pour décider
- Action attendue : ajouter un champ `multidevise_context` (ou similaire) à un snapshot MCP existant

## Doctrine fondamentale

> *"Trade mono-symbole, study multi-device."*

Søn 25/06 : *"il y a toute les force de devise mais on trade que le GBPUSD en etudiant les autres devises !"*

- **Trade** : UNIQUEMENT l'actif ciblé (GBPUSD dans le cas canonique)
- **Contexte** : les N devises (8) ou N secteurs sont étudiés comme **input de décision**, pas comme actifs tradés
- **Implémentation** : le module `core/pf_multidevise_context.py` lit `force_snapshots_v2` (8 colonnes force_*) sur M1 GBPUSD, expose `multidevise_context` via `mcp_powerflow_hot.get_live_snapshot`

**Anti-pattern** : "le chantier doit trader plusieurs paires pour utiliser les 8 forces" → NON. Le trade reste mono, le contexte est multi.

## Architecture type du module

```
Table source (DB powerflow_fresh.db)
  - 1 ligne par bougie
  - N colonnes "force_X" (X ∈ {usd, gbp, eur, jpy, cad, chf, aud, nzd})
  - Filtre saturation artefact : BETWEEN 2 AND 98
        ↓
Module core/pf_<nom>_context.py (200-300 lignes, stdlib only)
  - _load_latest_snapshot() → Dict[dev, force_value]
  - _compute_synthetic_indicators(forces) → leader, follower, spread, regime
  - _compute_freshness(ts, now) → LIVE/STALE/MISSING + age
  - _build_narrative(snapshot) → phrase courte 1 ligne
  - get_<nom>_context() → dict compact
        ↓
Branchement MCP live
  - Patch mcp_powerflow_hot.get_live_snapshot (ou autre) → bloc "<nom>_context" ajouté
  - Smoke test live → valider exposition
        ↓
Tests pytest
  - test_returns_required_fields (8-12 tests)
  - test_<chaque indicateur>_logique_métier
  - test_freshness_enum
  - test_idempotence_run_once (si wrapper CLI)
```

## Pattern de code — fonctions critiques

### 1. Chargement dernière snapshot

```python
def _load_latest_8forces() -> Optional[Dict[str, float]]:
    c = sqlite3.connect(str(DB_FRESH), timeout=5)
    row = c.execute("""
        SELECT force_aud, force_gbp, force_jpy, force_usd,
               force_cad, force_eur, force_chf, force_nzd,
               bar_time, datetime(bar_time, 'unixepoch') as bt_iso
        FROM force_snapshots_v2
        WHERE symbol='GBPUSD' AND timeframe=1
          AND force_usd IS NOT NULL AND force_usd BETWEEN 2 AND 98
        ORDER BY bar_time DESC LIMIT 1
    """).fetchone()
    if not row: return None
    return {
        "usd": row["force_usd"], "gbp": row["force_gbp"], "eur": row["force_eur"],
        "jpy": row["force_jpy"], "cad": row["force_cad"], "chf": row["force_chf"],
        "aud": row["force_aud"], "nzd": row["force_nzd"],
        "_bar_time": row["bar_time"], "_bar_time_iso": row["bt_iso"],
    }
```

**Détail critique** : **toujours** `WHERE force_X IS NOT NULL AND force_X BETWEEN 2 AND 98` (filtre saturation artefact 0.0/100.0). Cf. doctrine §8 de `powerflow-window-anchor`.

### 2. Conversion timestamp broker → UTC

⚠️ **Piège #1** : `bar_time` dans `force_snapshots_v2` est en **epoch broker UTC+3** (convention PowerFlow), pas en epoch UTC réel. **Toujours** soustraire 3h avant de comparer avec `now()` :

```python
def _compute_freshness(ts_epoch_broker, now_utc):
    ts_utc = datetime.fromtimestamp(ts_epoch_broker - 3*3600, tz=timezone.utc)
    age_min = (now_utc - ts_utc).total_seconds() / 60.0
    if age_min < 5: return "LIVE", age_min
    if age_min < 60: return "STALE", age_min
    return "MISSING", age_min
```

### 3. Classifier risk_regime (heuristique tradeable)

```python
def _classify_risk_regime(forces: Dict[str, float]) -> tuple:
    """Returns (regime_name, is_risk_on, is_safe_haven)."""
    aud = forces.get("aud", 50)
    nzd = forces.get("nzd", 50)
    jpy = forces.get("jpy", 50)
    chf = forces.get("chf", 50)
    is_risk_on = aud > 65 and nzd > 65       # cycliques (AUD/NZD) forts
    is_safe_haven = jpy > 65 and chf > 65   # refuges (JPY/CHF) forts
    if is_risk_on and not is_safe_haven: return "RISK_ON", True, False
    if is_safe_haven and not is_risk_on: return "SAFE_HAVEN", False, True
    if is_risk_on and is_safe_haven: return "MIXED", True, True       # ← contradiction
    return "NEUTRAL", False, False
```

**Piège #2** : MIXED exige que **les 2** flags soient True (AUD+NZD > 65 ET JPY+CHF > 65). Un seul flag = un seul régime. Tester ce cas explicitement dans `test_risk_regime_mixed`.

### 4. Output compact

```python
def get_multidevise_context(symbol: str = "GBPUSD") -> dict:
    forces = _load_latest_8forces()
    freshness, age = _compute_freshness(forces["_bar_time"], datetime.now(timezone.utc))
    risk_regime, is_risk_on, is_safe_haven = _classify_risk_regime(forces)
    # Leader = devise avec force max (exclure _bar_time / _bar_time_iso)
    dev_only = {k: v for k, v in forces.items() if k in {"usd","gbp","eur","jpy","cad","chf","aud","nzd"}}
    leader = max(dev_only, key=dev_only.get).upper()
    follower = min(dev_only, key=dev_only.get).upper()
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "leader": leader, "leader_strength": round(dev_only[leader.lower()], 1),
        "follower": follower,
        "spread_8dev": round(max(dev_only.values()) - min(dev_only.values()), 1),
        "forces_8devises": dev_only,
        "risk_regime": risk_regime,
        "is_risk_on": is_risk_on, "is_safe_haven": is_safe_haven,
        "data_freshness": freshness, "data_age_min": round(age, 1),
        "narrative_short": f"{leader} leader ({dev_only[leader.lower()]:.0f}) | {risk_regime.lower()}",
    }
```

## Branchement MCP live (template)

Dans `core/mcp_powerflow_hot.py::get_live_snapshot` (ou autre tool pertinent) :

```python
@mcp.tool()
def get_live_snapshot(symbol: str = "GBPUSD") -> dict:
    # ... existing logic ...
    
    # Multidevise context (P2 CEO 25/06)
    try:
        from core.pf_multidevise_context import get_multidevise_context as _gmc
        multidevise_ctx = _gmc(symbol)
    except Exception as _e:
        multidevise_ctx = {"error": f"multidevise_ctx unavailable: {_e}"}
    
    return {..., "multidevise_context": multidevise_ctx}
```

**Piège #3** : ne PAS utiliser `import sys; sys.path.insert(...)` localement dans le tool — `core/` est déjà dans le path au chargement du module (cf. ligne `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`). L'import direct suffit.

**Piège #4** : ne PAS référencer `_HERE` ou toute variable non-définie dans le module. Le module MCP `core/mcp_powerflow_hot.py` n'a que `BASE_DIR`, `DB_FRESH`, etc. Voir patch 25/06 où `_HERE` causait `NameError`.

## Tests pytest (5 classes, ~12 tests)

```python
def test_returns_required_fields():  # Tous les champs obligatoires
def test_symbol_default_gbpusd():   # Mono-symbole invariant
def test_forces_8devises_keys():    # 8 devises présentes
def test_forces_8devises_values():  # 0-100 (filtre saturation)
def test_leader_is_max_force():     # leader = force max
def test_follower_is_min_force():   # follower = force min
def test_spread_8dev_range():       # spread = max - min
def test_risk_regime_risk_on():      # AUD>65 + NZD>65
def test_risk_regime_safe_haven():   # JPY>65 + CHF>65
def test_risk_regime_mixed():       # 4 flags True
def test_risk_regime_neutral():     # toutes forces autour de 50
def test_data_freshness_live():     # LIVE/STALE/MISSING enum
```

Voir `scripts/test_pf_multidevise_context.py` (13/13 OK 25/06) pour le squelette.

## Insights opérationnels (validés 25/06 live)

1. **Trade freiné par microstructure, pas par le macro** : bridge GBPUSD en WAIT (conf 0.012) mais `multidevise_context` montrait risk-on confirmé (AUD+NZD > 65). Le trade est freiné par `vol=NEWS_SPIKE` (texture), pas par le contexte devises.

2. **AUD/NZD leaders = signal fort** : leader=NZD(72) AUD=70 = risk-on établi. Si leader=USD et AUD<30, c'est risk-off.

3. **spread_8dev > 30 = divergence forte** : les 8 devises ne convergent pas, c'est un signal d'incertitude (opposition probable). < 15 = consensus (les devises bougent ensemble = signal faible).

4. **Freshness LIVE critique** : si data_age > 5min, le multidevise_context est STALE → ne pas prendre de décision basée dessus. Le bridge heartbeat (`ea/.daemon/bridge_loop_heartbeat.txt`) doit être < 60s pour considérer les 8 forces comme fiables.

5. **Trade avec risk_regime = WAIT** : leader+follower ne suffisent pas. Si leader=USD(80) follower=AUD(35) MAIS AUD+NZD<65, c'est pas un risk-on établi — c'est juste USD fort. Le classifier `risk_on` regarde spécifiquement les 2 paires cycliques.

## 🚨 PITFALLS communs (catalog 25/06)

### PITFALL #1 — `PRAGMA table_info()` tronqué par terminal

**Symptôme** : conclusion erronée "il n'y a que OHLC, pas les forces" parce que les 15 premières colonnes affichées étaient OHLC.

**Fix** : toujours itérer sur **toutes** les colonnes du `PRAGMA` :

```python
cols = c.execute("PRAGMA table_info(force_snapshots_v2)").fetchall()
# Itérer sur cols, pas faire cols[:15]
```

### PITFALL #2 — `_HERE` variable inexistante

**Symptôme** : `NameError: name '_HERE' is not defined` au runtime quand on patche un tool MCP.

**Fix** : pas de `import sys as _sys; _sys.path.insert(0, os.path.join(_HERE, ".."))`. Le path est déjà configuré au chargement du module.

### PITFALL #3 — MIXED = 2 flags True (pas 1)

**Symptôme** : test pytest attend MIXED pour AUD=70, JPY=70, NZD=30, CHF=50 mais reçoit NEUTRAL.

**Root cause** : `is_risk_on = AUD>65 AND NZD>65` = False (NZD=30). `is_safe_haven = JPY>65 AND CHF>65` = False (CHF=50). → NEUTRAL.

**Fix** : MIXED exige les 2 flags True (AUD+NZD > 65 ET JPY+CHF > 65). Un seul flag = un seul régime.

### PITFALL #4 — `is_closed_bar=0` filtre les bougies live (learned 25/06 cf. `powerflow-window-anchor/references/scene-db-live-diagnostics-2026-06-25.md`)

**Symptôme** : l'EA ne ferme jamais les bougies M1. Si le module lit `WHERE is_closed_bar=1` pour optimiser, il rate les bougies du jour en cours.

**Fix** : choisir explicitement `is_closed_bar=0 OR 1` selon le besoin (live context → `OR 1`; backtest → `= 1`).

## Fichiers liés (référence canonique 25/06)

- `core/pf_multidevise_context.py` (260 lignes) — implémentation canonique
- `core/mcp_powerflow_hot.py` (patché `get_live_snapshot` + bloc `multidevise_context`)
- `scripts/test_pf_multidevise_context.py` (13/13 tests OK)
- `docs/checkpoints/CHECKPOINT_2026_06_25_SESSION_FLASH_SCENE_LIVE.md` (11.2KB, section #211)
- `docs/BORD_M3.md` (Décision #211 — 25/06)
- `docs/STATE.md` (Décision #211 — 25/06)
- `core/powerflow_fresh.db::force_snapshots_v2` (8 colonnes force_*, 32654 bougies M1 GBPUSD, 8 TF)
- `core/powerflow_fresh.db::bridge_forces_tick` (multidevise_ctx JSON legacy, souvent null)
- `core/powerflow_fresh.db::rotation_multidevise` (cron 1/h, leader+coalition, peut être vieux 2j)
- `powerflow-window-anchor/references/multidevise-context-pattern-2026-06-25.md` (ref détaillée)

## Extensions possibles (backlog)

- **Coalitions dynamiques** : détecter paires qui montent ensemble (ex. EUR+GBP corrélés > 0.7 sur 30min) → `coalition_strength` enrichi
- **Rotation inter-session** : `get_multidevise_context(session=NY)` pour exclure ASIAN/LONDON du calcul
- **Backtest risk_regime** : sur 7j de `force_snapshots_v2`, compter combien de fois `is_risk_on=True` correspond à GBPUSD hausse → calibrer le classifier
- **Multi-source freshness** : LIVE si M1 ET M5 ET bridge_forces_tick sont frais (3/3), STALE si 1/3, MISSING sinon
- **Volatility overlay** : ajouter `vol_regime` (CALM/NORMAL/EXPANSION/SPIKE) au multidevise_context pour combiner "qui mène" + "combien ça bouge"
