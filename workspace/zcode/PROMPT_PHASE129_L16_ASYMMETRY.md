# PROMPT ZCode — Phase 129 L16 (asymétrie WR par direction)

> **Copy-paste ce prompt dans ta session Z.ai (ZCode CLI)**
> Chantier git-indépendant, branche propre, **0 push sur origin**.

---

## CONTEXTE (lire en premier)

Tu travailles sur le projet **PowerFlow V9** (chemin : `C:/projet/V9`).
HEAD actuel : `b4d6c3b` (déjà pushé origin/feat/v9-foundation-clean).

**Lire avant de commencer** : `workspace/zcode/CONTEXT_HANDBOOK.md` (doctrine,
patterns, anti-patterns, modules à connaître).

**Sprint CEO 03/08 en parallèle** : 9 leviers quantiques L7-L11 ON, Phase 12
FTMO Challenge ACTIVE, bénéfice mesuré +758.5 pips L7+L8 walk-forward.

## MISSION — Phase 129 : L16 Asymétrie WR par direction

**Hypothèse** : WR baissier < WR haussier structurellement (historique 1108
trades haussiers favorisés). Forcer l'asymétrie dans le **sizing** :
- **Direction haussière** : multiplier sizing ×1.3 (edge haussier dominant)
- **Direction baissière** : multiplier sizing ×0.7 (edge baissier plus faible,
  lié à V9_NO_BAISSIERE mais adaptable par contexte)

**Audit SQL live attendu** (à faire toi-même, R14 strict — JAMAIS inventer) :
```bash
cd C:/projet/V9
.venv/Scripts/python -c "
import sqlite3
con = sqlite3.connect('data/v9_forces.db', timeout=30)
# Audit WR/PNL par direction
# Table : paper_trades.direction, paper_trades.is_win, paper_trades.pips_simulated
# Mesurer : WR haussier vs WR baissier, n, PNL cumulé, par paire/regime
"
```

**Gain projeté** : 100-250 pips (amplification edge haussier, atténuation
edge baissier).
**Effort** : 2-3 jours. **Risque** : faible (R2 additif, R6 fail-open,
réversible via kill switch).

## TRAVAIL DEMANDÉ

### 1. Créer ta branche
```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode-l16-asymmetry
```

### 2. Créer le module NEW (R2 additif)
**Fichier** : `core/v9/v9_direction_asymmetry.py`

API attendue :
```python
def direction_asymmetry_enabled() -> bool:
    """Kill switch V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED (defaut OFF, R25')."""

def compute_asymmetry_multiplier(direction: str, regime: str | None = None) -> float:
    """Retourne le multiplicateur de sizing selon direction et regime.

    Logique :
    - haussiere : 1.3 (sauf si regime=RETOUR_EQUILIBRE -> 1.0)
    - baissiere : 0.7 (sauf si regime=CASSURE -> 1.0, edge baissier confirmé)
    - Defaut : 1.0 si kill switch OFF.
    """

def apply_direction_asymmetry(
    sizing_base: float,
    direction: str,
    regime: str | None = None,
) -> dict:
    """Applique l'asymétrie au sizing de base.

    Retourne {"sizing_final": float, "leviers": list[str], "multiplier": float}.
    Si kill switch OFF -> sizing_final = sizing_base, leviers = [].
    """
```

### 3. Ajouter le kill switch (R25' strict)
**Fichier** : `core/v9/kill_switches.py` — ajouter en fin de fichier :
```python
def direction_asymmetry_enabled() -> bool:
    """Kill switch V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED — Phase 129.

    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    """
    return get("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "0") == "1"
```

### 4. Ajouter dans config/v9_kill_switches.env
```bash
# === Phase 129 L16 Asymetrie WR par direction (2026-08-03) ===
# Motion CEO « go max plein pouvoir » 03/08 : audit SQL a confirmer.
# Code : core/v9/v9_direction_asymmetry.py (NEW).
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED=0
```

### 5. Tests (R7 strict — obligatoire AVANT commit)
**Fichier** : `tests/test_v9_direction_asymmetry.py`

Cas à couvrir (minimum 5 tests) :
1. Kill switch OFF → multiplier = 1.0 systématique
2. Kill switch ON, direction haussière → multiplier = 1.3
3. Kill switch ON, direction baissière → multiplier = 0.7
4. Kill switch ON, direction haussière + regime RETOUR_EQUILIBRE → multiplier = 1.0
5. Kill switch ON, direction baissière + regime CASSURE → multiplier = 1.0
6. apply_direction_asymmetry(2.0, "haussiere") → sizing_final = 2.6, leviers = ["L16_asymmetry_×1.3"]
7. R6 fail-open : direction inconnue → multiplier = 1.0

### 6. Commit atomique (R26 strict, R22 sous-unité unique)
```bash
cd C:/projet/V9
git add core/v9/v9_direction_asymmetry.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_direction_asymmetry.py
git commit -m "feat(v9): Phase 129 L16 direction asymmetry (×1.3 haussier / ×0.7 baissier)

Context: Motion CEO 03/08 'go max plein pouvoir'. Plan quantique L11+
Phase 129 = asymetrie WR par direction.

[...suite du message avec audit SQL reel...]"
```

### 7. Vérification finale
```bash
cd C:/projet/V9
.venv/Scripts/python -m pytest tests/test_v9_direction_asymmetry.py -v
```
**Tous les tests doivent être verts.**

## RÈGLES DOCTRINE (RAPPEL)

- **R2 additif** : ne pas modifier `v9_mega_edge_filter.py` (R2 strict).
  Module NEW + intégration via DynamicRiskManager en lecture seule.
- **R6 fail-open** : JAMAIS d'exception non capturée. Kill switch défauts OFF.
- **R7 tests verts** : minimum 5 tests, tous verts AVANT commit.
- **R14 git vérité** : audit SQL réel avec la DB live, JAMAIS inventer.
- **R22 sous-unité** : 1 module NEW + 1 test + 1 commit = 1 phase.
- **R25' motion CEO** : kill switch défaut OFF, activation CEO explicite.
- **R26 DECISIONS_LOG** : reporter à Hermes (l'entrée sera ajoutée par lui).
- **R28 ZCode ≠ push** : **NE JAMAIS FAIRE `git push`**. Hermes agrège.

## ANTI-PATTERNS (À ÉVITER)

- ❌ Modifier `v9_mega_edge_filter.py` ou `dynamic_risk_manager.py`.
- ❌ Toucher à `core/v9/auto_calibrator.py` ou `core/v9/trade_engine.py`.
- ❌ `git push origin`.
- ❌ Commit sans tests verts (R7).
- ❌ Inventer des chiffres (R14).
- ❌ Mélanger L12 et L16 dans le même commit (R22 strict).

## REPORT À HERMES (à la fin)

Quand tu as fini, **reporte** à Hermes (l'orchestrateur) :
1. **Branche** : `feat/v9-zcode-l16-asymmetry`
2. **Commits atomiques** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode-l16-asymmetry`
3. **Tests verts** : sortie pytest complète
4. **Diff résumée** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode-l16-asymmetry`
5. **Audit SQL réel** : WR haussier vs baissier (n, WR, PNL)

Hermes va merger dans `feat/v9-foundation-clean`, ajouter l'entrée
DECISIONS_LOG, et pousser sur origin (R28 strict).

---

## AIDE — extrait de code V9 à suivre comme pattern

Regarde `core/v9/v9_mega_edge_filter.py` pour le pattern Phase 127 L11
(commentaire Phase XXX, audit SQL, doctrine rappelée). Adopte **exactement**
ce format.

Regarde `tests/test_v9_mega_edge_l11_dow.py` pour le pattern de test
(monkeypatch env, reload kill_switches, reset cache, signature str/bool).

---

**Go. Tu as 2-3 jours. Sprint CEO mode « plein pouvoir ». R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes orchestre. ZCode implémente. CEO valide.

—

*Prompt préparé par Hermes le 2026-08-03 06:30 UTC dans le cadre du
sprint CEO no-stop « optimisation max, plein pouvoir ».*