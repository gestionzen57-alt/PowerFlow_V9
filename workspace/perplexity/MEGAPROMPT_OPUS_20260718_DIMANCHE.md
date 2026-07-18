# MEGAPROMPT OPUS — SESSION DIMANCHE 2026-07-19 22h UTC
# Objectif : activation live + migration CVD + câblage final trade_engine

═══════════════════════════════════════════════════════════════════
   POWERFLOW V9 — SESSION CLAUDE CODE OPUS — 2026-07-19
   MISSION   : ACTIVATION LIVE + CVD MIGRATION + CÂBLAGE FINAL
   Branche   : feat/v9-foundation-clean
   CEO       : Søn | Orchestrateur git : Hermes (R28)
   Marché    : Forex ouvre dimanche 22h00 UTC — deadline absolue
═══════════════════════════════════════════════════════════════════

## CONTEXTE — ÉTAT AU 2026-07-18 23h (confirmé git)

### Ce qui est livré et commité
✅ Chantier A — Regime gate (V9_REGIME_GATE_ENABLED=0 — à activer)
   - get_current_regime() mapping 6→3 états (trending/ranging/volatile)
   - exploitability_evaluator gate : refuse si volatile & conf>0.7
   - scene['regime_gate'] propagé, lecture N-1, ordre pipeline intact

✅ Chantier B — CVaR/Kelly sizing (V9_KELLY_CVAR_ENABLED=0 — à activer)
   - cvar_95() + cvar_position_cap() dans risk_manager
   - Câblé dans trade_engine après PRM
   - Kelly existant (2x) non dupliqué — plafonnement CVaR ajouté

✅ Chantier C — CVD MQL4 (V9_CVD_ENABLED=0 — activation après migration)
   - EA V9_Sonde_M1.mq4 émet cvd_delta/cvd_cumul (MQL4 pur)
   - forces_reader parse les nouvelles colonnes
   - scene_builder expose cvd_cumul + cvd_divergence
   - Migration DB standalone : scripts/v9_migrate_cvd.py (idempotente)
   - ⚠️ capture_server ARRÊTÉ depuis hier — à redémarrer après migration

✅ Loop Breaker ACTIF — V9_LOOP_BREAKER_ENABLED=1
✅ TP/SL Dynamiques ACTIFS — V9_DYNAMIC_TP_SL_ENABLED=1
✅ 2258 tests passed, 0 régression

### Kill switches en attente d'activation (motion CEO = toi)
⏸️ V9_REGIME_GATE_ENABLED=0      ← activer aujourd'hui
⏸️ V9_KELLY_CVAR_ENABLED=0       ← activer aujourd'hui
⏸️ V9_CVD_ENABLED=0              ← activer APRÈS migration + restart
⏸️ V9_POSITION_MANAGER_ENABLED=0 ← décision CEO séparée
⏸️ V9_MARKET_REGIME_GLOBAL_ENABLED=0 ← décision CEO séparée

### Seuils calibrés — INTOUCHABLES
  ANTAGONISM_THRESHOLD = 31.39
  PLIURE_THRESHOLD     = 1.7
  COALITION_THRESHOLD  = 5.38

---

## TON RÔLE

Tu es Claude Code, IA d'implémentation dans PowerFlow V9.
Tu travailles SOUS les ordres de Søn (CEO).
Hermes est l'UNIQUE orchestrateur git — tu ne fais JAMAIS de git.
Tu prépares le code, les tests, et le HANDOFF structuré pour Hermes.
MT4 UNIQUEMENT — jamais de syntaxe MQL5.

---

## RITUEL DE DÉMARRAGE (obligatoire — ordre strict)

```bash
# 1. État git (Hermes fait git pull avant toi)
git log --oneline -5

# 2. Tests baseline
.venv/Scripts/python.exe -m pytest tests/ -q --tb=no 2>&1 | tail -5

# 3. État pipeline
python -c "
import sqlite3, os
db = sqlite3.connect('data/v9_forces.db')
c = db.cursor()
for t in ['decisions','scenes','forces_snapshots','regime_snapshots']:
    c.execute(f'SELECT count(*) FROM {t}')
    print(f'{t}: {c.fetchone()[0]:,}')
db.close()
"

# 4. Kill switches actuels
python -c "
import os
keys = ['V9_REGIME_GATE_ENABLED','V9_KELLY_CVAR_ENABLED',
        'V9_CVD_ENABLED','V9_LOOP_BREAKER_ENABLED',
        'V9_DYNAMIC_TP_SL_ENABLED','V9_POSITION_MANAGER_ENABLED']
for k in keys:
    print(f'{k} = {os.getenv(k,\"0\")}')
"

# 5. Port capture_server
python -c "
import socket
s = socket.socket()
r = s.connect_ex(('127.0.0.1', 31685))
print('Port 31685:', 'OPEN' if r==0 else 'FERME')
s.close()
"
```

→ Affiche tout. Confirme : "Rituel OK — prêt pour Mission 1"

---

## ══ MISSION 1 — ACTIVATION REGIME GATE + CVaR (PRIORITÉ 1) ══

### Objectif
Activer V9_REGIME_GATE_ENABLED=1 et V9_KELLY_CVAR_ENABLED=1
avant l'ouverture du marché 22h UTC.

### Vérification AVANT activation
```bash
# Test regime gate
.venv/Scripts/python.exe -m pytest tests/test_regime_gate.py -v

# Test CVaR
.venv/Scripts/python.exe -m pytest tests/test_kelly_cvar.py -v

# Smoke test pipeline end-to-end (1 cycle)
python scripts/smoke_test_pipeline.py 2>/dev/null || \
python -c "
from core.v9.regime_detector import RegimeDetector
from core.v9.exploitability_evaluator import ExploitabilityEvaluator
rd = RegimeDetector('data/v9_forces.db')
r = rd.get_current_regime('GBPUSD')
print('Regime GBPUSD:', r)
"
```

### Activation (si tous tests verts)
Dans `config/v9_kill_switches.env` :
```env
V9_REGIME_GATE_ENABLED=1
V9_KELLY_CVAR_ENABLED=1
```

### Validation post-activation
```bash
# Lancer 1 cycle pipeline et vérifier les logs
python deploy_v9.py --cycle-once 2>&1 | grep -E "regime|cvar|kelly|gate|refuse" | head -20
```

Tu cherches :
- `[REGIME_GATE]` dans les logs → gate actif
- `[CVaR]` ou `[KELLY]` → sizing institutionnel actif
- Aucun crash / exception non gérée

### HANDOFF Hermes Mission 1
```
HANDOFF → HERMES — Mission 1
Fichiers modifiés : config/v9_kill_switches.env
Activation       : V9_REGIME_GATE_ENABLED=1 + V9_KELLY_CVAR_ENABLED=1
Tests            : regime_gate X/X verts, kelly_cvar X/X verts
Logs post-activ  : [joindre extrait]
Commit           : chore(v9): activer V9_REGIME_GATE + V9_KELLY_CVAR (motion CEO dimanche)
DECISIONS_LOG    : §2026-07-19 [heure] entrée activation
```

---

## ══ MISSION 2 — MIGRATION CVD + RESTART CAPTURE_SERVER (PRIORITÉ 2) ══

### Objectif
Exécuter la migration DB CVD, recompiler l'EA MT4, redémarrer capture_server.

### Étape 1 — Migration DB (idempotente, safe à relancer)
```bash
# Vérifier colonnes actuelles
python -c "
import sqlite3
db = sqlite3.connect('data/v9_forces.db')
c = db.cursor()
c.execute('PRAGMA table_info(forces_snapshots)')
cols = [r[1] for r in c.fetchall()]
print('Colonnes forces_snapshots:', cols)
print('cvd_delta présent:', 'cvd_delta' in cols)
print('cvd_cumul présent:', 'cvd_cumul' in cols)
db.close()
"

# Si colonnes absentes → lancer migration
python scripts/v9_migrate_cvd.py

# Vérifier après
python -c "
import sqlite3
db = sqlite3.connect('data/v9_forces.db')
c = db.cursor()
c.execute('PRAGMA table_info(forces_snapshots)')
cols = [r[1] for r in c.fetchall()]
print('Migration OK:', 'cvd_delta' in cols and 'cvd_cumul' in cols)
db.close()
"
```

### Étape 2 — Recompiler EA MT4
Instructions pour Søn (action manuelle) :
1. Ouvrir MetaTrader 4
2. Menu Outils → Éditeur MetaEditor (F4)
3. Ouvrir `ea/V9_Sonde_M1.mq4`
4. Compiler (F7) → 0 erreur attendu
5. Attacher l'EA sur GBPUSD M1 (remplacer l'ancien)

### Étape 3 — Activer CVD
```env
# Dans config/v9_kill_switches.env
V9_CVD_ENABLED=1
```

### Étape 4 — Redémarrer capture_server
```bash
# Arrêter l'ancien (si tournait encore)
python deploy_v9.py --stop-capture 2>/dev/null || echo "déjà arrêté"

# Redémarrer
python deploy_v9.py --start-capture

# Vérifier port
python -c "
import socket, time
time.sleep(3)
s = socket.socket()
r = s.connect_ex(('127.0.0.1', 31685))
print('Port 31685:', 'OPEN ✅' if r==0 else 'FERMÉ ❌')
s.close()
"
```

### Validation CVD live
Après 5 min de données MT4 :
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/v9_forces.db')
c = db.cursor()
c.execute('SELECT cvd_delta, cvd_cumul FROM forces_snapshots ORDER BY id DESC LIMIT 5')
rows = c.fetchall()
print('CVD dernières 5 lignes:', rows)
has_data = any(r[0] is not None for r in rows)
print('CVD reçu:', '✅' if has_data else '❌ attendre MT4')
db.close()
"
```

### HANDOFF Hermes Mission 2
```
HANDOFF → HERMES — Mission 2
Fichiers modifiés : config/v9_kill_switches.env
Migration DB      : v9_migrate_cvd.py exécutée — colonnes cvd_delta/cvd_cumul ✅
CVD actif         : V9_CVD_ENABLED=1
capture_server    : port 31685 OPEN ✅
EA recompilé      : Søn a recompilé V9_Sonde_M1.mq4 ✅ (ou ⏸️ en attente)
Commit            : chore(v9): activer V9_CVD_ENABLED + migration confirmée
DECISIONS_LOG     : §2026-07-19 [heure] entrée CVD live
```

---

## ══ MISSION 3 — BACKTEST TP/SL DYNAMIQUE (PRIORITÉ 3) ══

### Objectif
Valider que V9_DYNAMIC_TP_SL_ENABLED=1 (déjà actif) améliore le WR
sur les 8 771 décisions post-17/07. Critère GO : ≥ +5pts WR.

### Exécution backtest
```bash
python -c "
import sqlite3
from core.v9.v9_dynamic_tp_sl import compute_dynamic_tp_sl
from core.v9.v9_bayesian_predictor import fit_from_decisions_db

db = sqlite3.connect('data/v9_forces.db')
c = db.cursor()

# Décisions post-catastrophe (hors 17/07)
c.execute('''
    SELECT symbol, direction, resolved_pnl_pips, resolved_at
    FROM decisions
    WHERE resolved_at IS NOT NULL
    AND date(resolved_at) != '2026-07-17'
    ORDER BY resolved_at DESC
    LIMIT 8771
''')
rows = c.fetchall()

total = len(rows)
wins  = sum(1 for r in rows if (r[2] or 0) > 0)
wr_baseline = wins / total * 100 if total else 0
print(f'Baseline WR (hors 17/07): {wr_baseline:.1f}% sur {total} décisions')

# WR attendu avec TP/SL dynamique = validation log pipeline
# (TP/SL est déjà ACTIF — on vérifie l'uplift sur trades récents)
c.execute('''
    SELECT symbol, direction, resolved_pnl_pips, source
    FROM decisions
    WHERE resolved_at IS NOT NULL
    AND date(resolved_at) >= '2026-07-19'
    ORDER BY resolved_at DESC
''')
recent = c.fetchall()
if recent:
    w = sum(1 for r in recent if (r[2] or 0) > 0)
    print(f'WR live post-activation: {w/len(recent)*100:.1f}% sur {len(recent)} trades')
else:
    print('Pas encore de trades post-activation (marché fermé)')
db.close()
"
```

### Rapport
- Si WR live ≥ baseline + 5pts → **CONFIRMER** dans DECISIONS_LOG
- Si WR live < baseline → **ESCALADER** à Søn (désactivation possible)

---

## ══ MISSION 4 — DÉCISION P2/P3 (PRIORITÉ 4 — CEO ONLY) ══

Ces 2 switches attendent une décision Søn. Opus ne les active PAS
sans motion CEO explicite dans ce prompt.

```
⏸️ V9_POSITION_MANAGER_ENABLED=0
⏸️ V9_MARKET_REGIME_GLOBAL_ENABLED=0
```

Si Søn dit "go P2" → activer V9_POSITION_MANAGER_ENABLED=1
Si Søn dit "go P3" → activer V9_MARKET_REGIME_GLOBAL_ENABLED=1
Sinon → ignorer, passer à Mission suivante.

---

## SÉQUENCE D'EXÉCUTION

```
Rituel démarrage (5 min)
    ↓
Mission 1 : Regime Gate + CVaR ACTIFS avant 22h UTC
    → Tests verts ✅ → activation → log pipeline → HANDOFF Hermes
    ↓
Mission 2 : CVD migration + capture_server restart
    → Migration ✅ → EA recompilé → port 31685 OPEN → HANDOFF Hermes
    ↓
Mission 3 : Validation backtest TP/SL live
    → Rapport WR → entrée DECISIONS_LOG
    ↓
Mission 4 : P2/P3 (si motion CEO reçue)
```

---

## RÈGLES D'IMPLÉMENTATION

Tu DOIS :
  ✅ Rituel complet avant toute action
  ✅ Tests verts avant chaque activation
  ✅ Logs pipeline vérifiés après chaque activation
  ✅ HANDOFF Hermes après chaque mission
  ✅ DECISIONS_LOG entrée par activation
  ✅ STATE.md mis à jour en fin de session
  ✅ MT4 / MQL4 uniquement (jamais MQL5)

Tu NE DOIS PAS :
  ❌ Activer P2/P3 sans motion CEO explicite dans ce prompt
  ❌ Toucher DOCTRINE.md, config.py, orchestrator.py
  ❌ Ouvrir Phase 10 / Phase 12 / Phase 13 (gelées)
  ❌ Faire des commandes git (Hermes uniquement)
  ❌ Lancer la migration CVD sans vérifier les colonnes d'abord

---

## FORMAT HANDOFF HERMES

```
HANDOFF → HERMES
Date       : 2026-07-19 | Mission : [1 / 2 / 3 / 4]
Branche    : feat/v9-foundation-clean

Fichiers modifiés :
  - [fichier] : [changement]

Commit proposé :
  chore(v9): [message précis]

Tests      : X passed, 0 nouvelles régressions
Kill switch activé : [NOM]=1
Logs post-activation : [extrait 3-5 lignes]
DECISIONS_LOG : §2026-07-19 [heure] [entrée]
STATE.md   : [mis à jour / non touché]

Push : origin feat/v9-foundation-clean
```

---

## GO — LANCE LE RITUEL

Exécute les 5 bash du rituel → affiche résultats complets →
confirme à Søn :

  "Rituel OK.
   Tests baseline : X passed.
   Port 31685 : [OPEN/FERMÉ]
   Kill switches actifs : [liste]
   → Je démarre Mission 1 (Regime Gate + CVaR)."

Marché ouvre à 22h00 UTC — Mission 1 doit être faite AVANT.
Travail méthodique. Zéro régression. MT4 uniquement. Jamais de git.

═══════════════════════════════════════════════════════════════════
