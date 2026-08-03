# PROMPT ZCode — Phase 128 L12 (corrélation inter-paires × régime)

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

## MISSION — Phase 128 : L12 Filtre corrélation inter-paires × régime

**Hypothèse** : 2 paires corrélées > 0.7 → sizing ×0.5 (PRM câblé mais
générique). Affiner par **régime** (CASSURE, EXTENSION, DISTRIBUTION, REJET,
RETOUR_EQUILIBRE) — la corrélation monte en risk-on/off et baisse en
trending.

**Audit SQL live attendu** (à faire toi-même, R14 strict — JAMAIS inventer) :
```bash
cd C:/projet/V9
.venv/Scripts/python -c "
import sqlite3
con = sqlite3.connect('data/v9_forces.db', timeout=30)
# Audit correlation inter-paires par regime
# Table : paper_trades + regime_snapshots
# Croiser : symbole1, symbole2, regime, WR/pips
"
```

**Gain projeté** : 80-150 pips (réduction exposition sur fenêtres corrélées).
**Effort** : 2-3 jours. **Risque** : faible (R2 additif, R6 fail-open).

## TRAVAIL DEMANDÉ

### 1. Créer ta branche
```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode-l12-correlation
```

### 2. Créer le module NEW (R2 additif)
**Fichier** : `core/v9/v9_correlation_filter.py`

API attendue :
```python
def correlation_filter_enabled() -> bool:
    """Kill switch V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED (defaut OFF, R25')."""

def evaluate_correlation_filter(
    symbol: str,
    regime: str,
    open_positions: list[dict],  # [{symbol, regime, side}, ...]
    correlation_matrix: dict[tuple[str, str], float] | None = None,
) -> dict:
    """Retourne {"go": bool, "sizing_multiplier": float, "reason": str, "leviers": list[str]}.

    Logique :
    - Si correlation(symbol, open_pos.symbol) > V9_L12_CORR_THRESHOLD (defaut 0.7)
      ET regime(open_pos) == regime(symbol) -> sizing_multiplier = 0.5
    - Si 2+ positions deja ouvertes sur paires correlees (meme regime) -> go = False
    - Sinon pass-through.
    """
```

### 3. Ajouter le kill switch (R25' strict)
**Fichier** : `core/v9/kill_switches.py` — ajouter en fin de fichier :
```python
def correlation_filter_enabled() -> bool:
    """Kill switch V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED — Phase 128.

    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    """
    return get("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "0") == "1"
```

### 4. Ajouter dans config/v9_kill_switches.env
```bash
# === Phase 128 L12 Correlation inter-paires × regime (2026-08-03) ===
# Motion CEO « go max plein pouvoir » 03/08 : audit SQL a confirmer.
# Code : core/v9/v9_correlation_filter.py (NEW).
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED=0
```

### 5. Tests (R7 strict — obligatoire AVANT commit)
**Fichier** : `tests/test_v9_correlation_filter.py`

Cas à couvrir (minimum 5 tests) :
1. Pas de corrélation (seule position) → go=True, sizing=1.0
2. 1 position GBPUSD haussière, nouvelle entrée GBPUSD haussière → pass-through
3. 2 paires corrélées > 0.7 même régime → sizing=0.5
4. 2 paires corrélées mais régimes DIFFÉRENTS → sizing=1.0
5. Kill switch OFF → pass-through systématique
6. R6 fail-open : correlation_matrix=None → pass-through

### 6. Commit atomique (R26 strict, R22 sous-unité unique)
```bash
cd C:/projet/V9
git add core/v9/v9_correlation_filter.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_correlation_filter.py
git commit -m "feat(v9): Phase 128 L12 correlation filter inter-paires × regime

Context: Motion CEO 03/08 'go max plein pouvoir'. Plan quantique L11+
Phase 128 = extension du PRM (Portfolio Risk Manager) par regime.

[...suite du message avec audit SQL reel...]"
```

### 7. Vérification finale
```bash
cd C:/projet/V9
.venv/Scripts/python -m pytest tests/test_v9_correlation_filter.py -v
```
**Tous les tests doivent être verts.**

## RÈGLES DOCTRINE (RAPPEL)

- **R2 additif** : ne pas modifier `v9_mega_edge_filter.py` (R2 strict).
  Si intégration nécessaire, ajouter une fonction dans ton module NEW.
- **R6 fail-open** : JAMAIS d'exception non capturée. Kill switch défauts OFF.
- **R7 tests verts** : minimum 5 tests, tous verts AVANT commit.
- **R14 git vérité** : audit SQL réel avec la DB live, JAMAIS inventer.
- **R22 sous-unité** : 1 module NEW + 1 test + 1 commit = 1 phase.
- **R25' motion CEO** : kill switch défaut OFF, activation CEO explicite.
- **R26 DECISIONS_LOG** : ajouter une entrée dans le fichier (ne pas
  toucher si tu n'es pas sûr, juste reporter la branche à Hermes).
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
1. **Branche** : `feat/v9-zcode-l12-correlation`
2. **Commits atomiques** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode-l12-correlation`
3. **Tests verts** : sortie pytest complète
4. **Diff résumée** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode-l12-correlation`
5. **Audit SQL réel** : nombres mesurés (n, WR, PNL, corrélation max)

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