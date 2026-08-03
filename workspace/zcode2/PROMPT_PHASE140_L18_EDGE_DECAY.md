# PROMPT ZCode2 — Phase 140 L18 Edge Decay Sentinel

> **Copy-paste ce prompt dans ta session Z.ai (ZCode CLI)**
> Chantier ZCode2 = branche `feat/v9-zcode2-l18-edge-decay` (0 push).

---

## CONTEXTE (lire en premier)

Tu travailles sur le projet **PowerFlow V9** (chemin : `C:/projet/V9`).
HEAD actuel : `83677a2` (déjà pushé origin/feat/v9-foundation-clean).

**Lire** : `workspace/zcode2/CONTEXT_HANDBOOK.md` (doctrine, modules à
connaître, branche de travail, anti-patterns, report à Hermes2).

**Sprint CEO 03/08 finalisé** : ZCode a livré Phase 128 L12 + Phase 129 L16.

## MISSION — Phase 140 : L18 Edge Decay Sentinel

**Hypothèse** : Un edge qui fonctionnait hier peut se dégrader aujourd'hui.
Le L18 Sentinel surveille en continu les principes et propose des actions
préventives (blacklist temporaire, demotion, observation) AVANT que le
WR chute significativement.

**Logique** :
- Détecte si WR d'un principe chute de >10% sur 20 derniers trades vs baseline
- Détecte si PNL cumulé devient <0 sur 30 derniers trades
- Détecte si win_rate decay slope < -0.05 (pente de dégradation)
- Propose actions : BLACKLIST_TEMP_24H, DEMOTION_ACTIVE_TO_DORMANT, OBSERVATION_ONLY

**Audit SQL live attendu** : win_rate decay par principe.

**Gain projeté** : 60-120 pips (prévention vs réactif).

**Effort** : 2-3 jours. **Risque** : faible (R2 additif, R6 fail-open, motion CEO).

## TRAVAIL

### 1. Branche
```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode2-l18-edge-decay
```

### 2. Module NEW (R2 additif)
**Fichier** : `core/v9/v9_edge_decay_sentinel.py`

API :
```python
def edge_decay_sentinel_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_SENTINEL_ENABLED (defaut OFF, R25')."""

def analyze_principle_decay(
    principle_id: str,
    n_recent_trades: int = 20,
    n_baseline_trades: int = 100,
) -> dict:
    """Analyse la degradation d'un principe.

    Returns:
      dict avec :
        - "principle_id", "n_recent", "n_baseline"
        - "wr_recent_pct", "wr_baseline_pct", "wr_delta"
        - "pnl_recent", "pnl_baseline", "pnl_delta"
        - "decay_detected", "decay_score", "recommended_action"
    """

def scan_all_principles_decay(
    n_recent: int = 20,
    n_baseline: int = 100,
) -> list[dict]:
    """Scan tous les principes et retourne ceux en degradation."""
```

### 3. Kill switch (R25' strict)
```python
# core/v9/kill_switches.py
def edge_decay_sentinel_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_SENTINEL_ENABLED — Phase 140.

    Active le sentinel de degradation edge (proactif vs reactif).
    Defaut OFF (R25' strict motion CEO). R6 fail-open.
    """
    return get("V9_EDGE_DECAY_SENTINEL_ENABLED", "0") == "1"
```

### 4. .env
```bash
# === Phase 140 L18 Edge Decay Sentinel (2026-08-03) ===
# Code : core/v9/v9_edge_decay_sentinel.py (NEW).
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_EDGE_DECAY_SENTINEL_ENABLED=0
```

### 5. Tests (R7 strict — min 6 tests)
**Fichier** : `tests/test_v9_edge_decay_sentinel.py`

Cas :
1. Kill switch OFF → pass-through
2. Principe stable (WR stable) → decay_detected = False
3. Principe en degradation (-15% WR) → decay_detected = True + action BLACKLIST_TEMP
4. PNL recent <0 sur 30 trades → action DEMOTION
5. scan_all_principles_decay → liste triée par decay_score desc
6. R6 fail-open : DB absente → []

### 6. Commit atomique (R26, R22)
```bash
cd C:/projet/V9
git add core/v9/v9_edge_decay_sentinel.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_edge_decay_sentinel.py
git commit -m "feat(v9): Phase 140 L18 Edge Decay Sentinel

Context: Sprint CEO 03/08+1 V4 - ZCode2 chantier C1 (parallele Hermes2).
[...suite du message avec audit SQL reel...]"
```

### 7. NE PAS push (R28 strict)
```bash
# NE PAS git push origin (R28 : Hermes2 seul merge + push)
```

### 8. Report à Hermes2

À la fin du chantier :
1. **Branche** : `feat/v9-zcode2-l18-edge-decay`
2. **Commits** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode2-l18-edge-decay`
3. **Tests verts** : sortie pytest complète
4. **Diff** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode2-l18-edge-decay`
5. **Audit SQL** : decay_score moyen, top 5 principes en degradation

Hermes2 merge + push origin.

## RÈGLES DOCTRINE (RAPPEL)

- **R2 additif** : NEW module, 0 modif core/ partagé.
- **R6 fail-open** : JAMAIS d'exception. Kill switch OFF.
- **R7 tests verts** : min 6, AVANT commit.
- **R14 git vérité** : SQL live.
- **R22 sous-unité** : 1 module + 1 test + 1 commit.
- **R25' motion CEO** : kill switch défaut OFF.
- **R26 DECISIONS_LOG** : reporter à Hermes2.
- **R28 ZCode2 ≠ push** : **NE JAMAIS FAIRE `git push`**.

## ANTI-PATTERNS

- ❌ Modifier `v9_edge_decay_monitor.py` (existant, R2 strict).
- ❌ `git push origin`.
- ❌ Commit sans tests.
- ❌ Inventer des chiffres.

---

**Go. Tu as 2-3 jours. Sprint CEO mode « plein pouvoir » V4. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes2 orchestre. ZCode2 implémente. CEO Søn valide.

—

*Prompt préparé par Hermes le 2026-08-03 07:30 UTC pour ZCode2 (session +1).*