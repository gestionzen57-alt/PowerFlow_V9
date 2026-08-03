# PROMPT Hermes2 — Phase 136 Pyramid Engine V4 (zones_state boost)

> **Copy-paste ce prompt dans ta session Hermes (M3)**
> Chantier Hermes2 = branche `feat/v9-foundation-clean` (push autorisé).

---

## CONTEXTE (lire en premier)

Tu travailles sur le projet **PowerFlow V9** (chemin : `C:/projet/V9`).
HEAD actuel : `83677a2` (déjà pushé sur `origin/feat/v9-foundation-clean`).

**Lire avant de commencer** : `workspace/hermes2/CONTEXT_HANDBOOK.md` (doctrine,
patterns, anti-patterns, modules à connaître).

**Sprint CEO 03/08 finalisé** : 22 commits pushés, 12 leviers L7-L17 quantiques
ON, 167 tests verts cumulés. ZCode a livré Phase 128 L12 + Phase 129 L16.

## MISSION — Phase 136 : Pyramid Engine V4 (zones_state boost)

**Hypothèse** : V3 (MTF boost ×1.2 si ≥3 TF alignés) + boost zones_state
supplémentaire selon l'état de la zone (naissance/2e_jambe/retest/range).

**Logique** :
- Zone `naissance` (zone qui vient de naître) : boost ×1.2 (edge plus fort)
- Zone `2e_jambe` (deuxième jambe après cassure) : boost ×1.1
- Zone `retest` (retest d'une zone cassée) : boost ×1.0 (pass-through)
- Zone `range` (range plat) : boost ×0.8 (edge plus faible)

**Composition multiplicative V3 × V4** :
`final = V2_multiplier × V3_MTF × V4_zones_state`

**Audit SQL live attendu** : distribution zone_state × WR/PNL
```bash
cd C:/projet/V9
.venv/Scripts/python -c "
import sqlite3
con = sqlite3.connect('data/v9_forces.db', timeout=30)
# Audit zone_state × WR
"
```

**Gain projeté** : 50-100 pips (extension V3 + zones_state).

**Effort** : 2-3 jours. **Risque** : faible (R2 additif, R6 fail-open).

## TRAVAIL DEMANDÉ

### 1. Vérifier la branche
```bash
cd C:/projet/V9
git checkout feat/v9-foundation-clean
git pull origin feat/v9-foundation-clean
```

### 2. Créer le module NEW (R2 additif)
**Fichier** : `core/v9/v9_pyramiding_engine_v4.py`

API attendue :
```python
def pyramiding_v4_zones_state_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V4_ZONES_STATE_ENABLED (defaut OFF, R25')."""

def compute_zones_state_multiplier(zone_state: str) -> float:
    """Retourne le multiplicateur selon zone_state.

    Logique :
    - naissance : ×1.2
    - 2e_jambe : ×1.1
    - retest : ×1.0
    - range : ×0.8
    - autre (defaut) : ×1.0
    """

class PyramidingEngineV4(PyramidingEngineV3):
    """V4 = V3 + zones_state boost.

    Herite de PyramidingEngineV3 (STARS/SUPER_STARS + MTF boost).
    Ajoute le boost zones_state (naissance/2e_jambe/retest/range).
    """

    def evaluate_v4(
        self,
        signal: dict,
        aligned_timeframes: Sequence[str] | None = None,
        zone_state: str | None = None,
        context: dict | None = None,
    ) -> dict:
        """Composition V2 × V3 MTF × V4 zones_state."""
```

### 3. Ajouter le kill switch (R25' strict)
**Fichier** : `core/v9/kill_switches.py` — ajouter en fin de fichier :
```python
def pyramiding_v4_zones_state_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V4_ZONES_STATE_ENABLED — Phase 136.

    Active le boost zones_state (naissance ×1.2, 2e_jambe ×1.1, retest ×1.0,
    range ×0.8). Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    """
    return get("V9_PYRAMIDING_V4_ZONES_STATE_ENABLED", "0") == "1"
```

### 4. Ajouter dans config/v9_kill_switches.env
```bash
# === Phase 136 V4 Zones State boost (2026-08-03) ===
# Motion CEO « go max plein pouvoir » 03/08 sprint +1 : extension V3
# (MTF boost ×1.2 si >=3 TF alignes) avec boost zones_state additif.
# Code : core/v9/v9_pyramiding_engine_v4.py (NEW, herite PyramidingEngineV3).
# Composition : final = V2 × V3_MTF × V4_zones_state.
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_PYRAMIDING_V4_ZONES_STATE_ENABLED=0
```

### 5. Tests (R7 strict — obligatoire AVANT commit)
**Fichier** : `tests/test_v9_pyramiding_engine_v4.py`

Cas à couvrir (minimum 8 tests) :
1. Kill switch OFF → multiplier = 1.0 systématique
2. zone_state "naissance" → ×1.2
3. zone_state "2e_jambe" → ×1.1
4. zone_state "retest" → ×1.0 (pass-through)
5. zone_state "range" → ×0.8
6. zone_state inconnue → ×1.0 (R6 fail-open)
7. Composition cumulative : V2 stars (1.8) × V3 MTF (1.2) × V4 naissance (1.2) = 2.592
8. zone_state None → pass-through ×1.0

### 6. Commit atomique (R26 strict, R22 sous-unité unique)
```bash
cd C:/projet/V9
git add core/v9/v9_pyramiding_engine_v4.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_pyramiding_engine_v4.py
git commit -m "feat(v9): Phase 136 V4 zones_state boost (herite Pyramiding V3)

Context: Sprint CEO 03/08+1 V4 - Hermes2 chantier H2-1.
[...suite du message avec audit SQL reel...]"
```

### 7. Vérification finale
```bash
cd C:/projet/V9
.venv/Scripts/python -m pytest tests/test_v9_pyramiding_engine_v4.py -v
```
**Tous les tests doivent être verts.**

### 8. Push (Hermes2 = orchestrateur, push autorisé)
```bash
cd C:/projet/V9
git push origin feat/v9-foundation-clean
```

## RÈGLES DOCTRINE (RAPPEL)

- **R2 additif** : ne pas modifier `v9_pyramiding_engine_v3.py` (héritage).
- **R6 fail-open** : JAMAIS d'exception non capturée. Kill switch défauts OFF.
- **R7 tests verts** : minimum 8 tests, tous verts AVANT commit.
- **R14 git vérité** : audit SQL réel, JAMAIS inventer.
- **R22 sous-unité** : 1 module + 1 test + 1 commit = 1 phase.
- **R25' motion CEO** : kill switch défaut OFF, activation CEO.
- **R26 DECISIONS_LOG** : ajouter une entrée dans le fichier.
- **R28 Hermes2 = push autorisé** : tu peux push (contrairement à ZCode2).

## ANTI-PATTERNS (À ÉVITER)

- ❌ Modifier `v9_pyramiding_engine_v3.py` (héritage).
- ❌ Toucher aux fichiers ZCode (Phase 128/129).
- ❌ Commit sans tests verts (R7).
- ❌ Inventer des chiffres (R14).
- ❌ Mélanger plusieurs phases (R22).

## REPORT (à la fin)

Hermes2 push direct sur origin = SUCCESS. Pas besoin de reporter à un autre agent.

---

**Go. Tu as 2-3 jours. Sprint CEO mode « plein pouvoir » V4. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes2 orchestre. ZCode2 implémente en parallèle. CEO Søn valide.

—

*Prompt préparé par Hermes le 2026-08-03 07:30 UTC dans le cadre du
sprint CEO no-stop « optimisation max, plein pouvoir » V4 (session +1).*