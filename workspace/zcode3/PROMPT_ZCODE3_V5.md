# PROMPT PUISSANT — ZCode3 (implémentation sprint V5, parallèle Hermes3)

> **Copy-paste ce prompt dans ta session Z.ai (ZCode CLI)**
> Tu es **ZCode3** = implémentation branche propre (0 push, R28 strict).

---

## 🎯 MISSION

Sprint CEO 03/08+2 (V5) : **2 phases ZCode3** parallélisées avec Hermes3.
Bénéfice projeté **+2800-3300 pips** (vs +2038-2788 V4 finalisé).

**Tu es responsable de** :
1. **Phase 141 L19 News Shock Attenuator** (ZCode3 C1, recommandé) — 1-2 j
2. **Phase 143 L20 News Heat Map (multi-news correlation)** (ZCode3 C2) — 2-3 j

**Tu dois** :
- Travailler sur branche propre (`feat/v9-zcode3-*`)
- **JAMAIS push origin** (R28 strict : Hermes3 seul merge + push)
- Coder + tester + commit + reporter à Hermes3

## 📊 CONTEXTE SPRINT CEO 03/08+1 (V4) — FINALISÉ

**HEAD actuel** : `858fc7c` (déjà pushé origin/feat/v9-foundation-clean).
**Sprint CEO V4 = SUCCESS** :
- 26 commits sprint CEO total (V3 + V4)
- 14 leviers quantiques ON
- 192 tests verts cumulés
- Bénéfice projeté 30j : +2038-2788 pips

**Tu hérites de** : `workspace/zcode2/CONTEXT_HANDBOOK.md` (toute la
doctrine, modules, patterns, anti-patterns, multi-IA R28).

## 🚀 PLAN SPRINT V5 — 2 PHASES ZCODE3

### Phase 141 — L19 News Shock Attenuator (ZCode3 C1, RECOMMANDÉ en premier)

**Hypothèse** : annonces économiques (NFP, CPI, FOMC) créent des spikes
de volatilité. Atténuer le sizing pendant les fenêtres news (15 min
avant/après) réduit les pertes.

**Logique** :
```python
def get_news_window_multiplier(minutes_to_news: int) -> tuple[float, str]:
    """
    Logique:
      - 15 <= minutes_to_news <= 60 : ×0.5 (pre_news)
      - 0 <= minutes_to_news < 15    : ×0.0 (imminent / HALT)
      - -15 <= minutes_to_news < 0   : ×0.5 (post_news)
      - -60 <= minutes_to_news < -15 : ×0.8 (normalisation)
      - autre                        : ×1.0 (normal)
    """
```

**Audit SQL live attendu** : trades pendant fenêtres news vs hors news.
**Gain projeté** : 40-80 pips.
**Effort** : 1-2 jours.

**Fichiers à créer** :
- `core/v9/v9_news_shock_attenuator.py` (NEW module R2 additif)
- `core/v9/kill_switches.py` (ajout `news_shock_attenuator_enabled()`)
- `config/v9_kill_switches.env` (V9_NEWS_SHOCK_ATTENUATOR_ENABLED=0)
- `tests/test_v9_news_shock_attenuator.py` (min 5 tests)

**Branche** : `feat/v9-zcode3-l19-news-shock`

### Phase 143 — L20 News Heat Map (ZCode3 C2, après Phase 141)

**Hypothèse** : Certaines paires réagissent plus fortement à certains types
de news. Heat map news × paire × type (NFP, CPI, FOMC) pour sizing adaptatif.

**Logique** :
```python
def compute_news_heat_multiplier(
    symbol: str,
    news_type: str,
    minutes_to_news: int,
) -> float:
    """
    Logique:
      - heat_map[(symbol, news_type)] = base_multiplier
      - ajuste par minutes_to_news (pre_news boost, post_news attenuation)
    """
```

**Audit SQL live attendu** : distribution news × paire × WR/PNL.
**Gain projeté** : 60-100 pips.
**Effort** : 2-3 jours.

**Fichiers à créer** :
- `core/v9/v9_news_heat_map.py` (NEW module R2 additif)
- `core/v9/kill_switches.py` (ajout `news_heat_map_enabled()`)
- `config/v9_kill_switches.env` (V9_NEWS_HEAT_MAP_ENABLED=0)
- `tests/test_v9_news_heat_map.py` (min 5 tests)

**Branche** : `feat/v9-zcode3-l20-news-heat`

## 🛡️ DOCTRINE (RAPPEL — NE PAS TRANSGRESSER)

| Règle | Application ZCode3 |
|---|---|
| **R2 additif** | NEW modules uniquement, 0 modif core/ partagé. |
| **R6 fail-open** | JAMAIS d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | Livrer 5-15 tests par module. Tests AVANT commit. |
| **R14 git vérité** | Audit SQL live, JAMAIS inventer de chiffres. |
| **R22 sous-unité unique** | 1 phase = 1 module + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO. |
| **R26 DECISIONS_LOG** | Reporter à Hermes3 (qui merge + ajoute entry). |
| **R28 multi-IA** | **ZCode3 = 0 push.** Hermes3 seul merge et push. |

## 🧠 MODULES CORE/ À NE PAS MODIFIER (sauf additif)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Ajouter fonction accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | NE PAS toucher (sauf si L19+ s'intègre, alors additif). |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |
| Modules V4 Hermes2 (V4 zones, DD tracker, regime live) | NE PAS toucher. |
| Modules ZCode2 (L18 edge decay sentinel) | NE PAS toucher. |

## ⚡ PLAN D'ACTION IMMÉDIAT (sprint V5 jour 1)

### Étape 1 : Branche Phase 141
```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode3-l19-news-shock
```

### Étape 2 : Audit SQL live (R14 strict)
```bash
cd C:/projet/V9
.venv/Scripts/python -c "
import sqlite3, time
con = sqlite3.connect('data/v9_forces.db', timeout=30)
# Audit trades pendant fenetres news vs hors news
# Note : pas de table news dans DB actuelle, utiliser timestamps NFP/CPI/FOMC 2026 connus
# OU utiliser high_vol_spike (vol_ratio > 2.0) comme proxy
t0 = time.time()
# Distribution vol_ratio × WR × PNL
r = con.execute('''
    SELECT
      CASE WHEN volatility_ratio >= 2.0 THEN 'spike' ELSE 'normal' END AS regime,
      COUNT(*) AS n,
      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
      SUM(pnl) AS total_pnl
    FROM paper_trades
    WHERE closed_at > datetime('now', '-30 day')
    GROUP BY regime
''').fetchall()
print('Audit 30j (volatility_ratio):', r, f'en {time.time()-t0:.1f}s')
"
```

### Étape 3 : Code Phase 141
Créer `core/v9/v9_news_shock_attenuator.py` :
```python
\"\"\"v9_news_shock_attenuator.py — Phase 141 L19 : News Shock Attenuator.

Module additif (R2) qui module le sizing selon la fenêtre news
(pre_news / imminent / post_news / normalisation / normal).
Defaut OFF (R25' strict motion CEO).
R6 fail-open : JAMAIS d'exception non capturee.
\"\"\"
from core.v9.kill_switches import get

NEWS_SHOCK_ATTENUATOR_ENV = "V9_NEWS_SHOCK_ATTENUATOR_ENABLED"


def news_shock_attenuator_enabled() -> bool:
    \"\"\"Kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED — Phase 141.

    Active l'attenuateur news shock (fenetres NFP/CPI/FOMC).
    Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    \"\"\"
    return get(NEWS_SHOCK_ATTENUATOR_ENV, "0") == "1"


def get_news_window_multiplier(minutes_to_news: int) -> tuple[float, str]:
    \"\"\"Retourne (multiplier, phase_label) selon minutes_to_news.

    Logique:
      - 15 <= minutes_to_news <= 60 : ×0.5 (pre_news)
      - 0 <= minutes_to_news < 15    : ×0.0 (imminent / HALT)
      - -15 <= minutes_to_news < 0   : ×0.5 (post_news)
      - -60 <= minutes_to_news < -15 : ×0.8 (normalisation)
      - autre                        : ×1.0 (normal)

    Returns:
      (multiplier, phase_label)
    \"\"\"
    if not news_shock_attenuator_enabled():
        return 1.0, "kill_switch_off"
    if 15 <= minutes_to_news <= 60:
        return 0.5, "pre_news"
    if 0 <= minutes_to_news < 15:
        return 0.0, "imminent"
    if -15 <= minutes_to_news < 0:
        return 0.5, "post_news"
    if -60 <= minutes_to_news < -15:
        return 0.8, "normalisation"
    return 1.0, "normal"
```

### Étape 4 : Kill switch + .env
Ajouter dans `core/v9/kill_switches.py` (fin de fichier) :
```python
def news_shock_attenuator_enabled() -> bool:
    """Kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED — Phase 141.

    Active l'attenuateur news shock.
    Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    """
    return get("V9_NEWS_SHOCK_ATTENUATOR_ENABLED", "0") == "1"
```

Ajouter dans `config/v9_kill_switches.env` :
```bash
# === Phase 141 L19 News Shock Attenuator (2026-08-04) ===
# Code : core/v9/v9_news_shock_attenuator.py (NEW, ZCode3 C1).
# Additif (R2), defaut OFF (R25' strict), R6 fail-open.
V9_NEWS_SHOCK_ATTENUATOR_ENABLED=0
```

### Étape 5 : Tests
Créer `tests/test_v9_news_shock_attenuator.py` (min 5 tests) :
1. Kill switch OFF → ×1.0
2. minutes_to_news = 30 → ×0.5 (pre_news)
3. minutes_to_news = 5 → ×0.0 (imminent)
4. minutes_to_news = -10 → ×0.5 (post_news)
5. minutes_to_news = 100 → ×1.0 (normal)

### Étape 6 : Commit atomique
```bash
cd C:/projet/V9
git add core/v9/v9_news_shock_attenuator.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_news_shock_attenuator.py
git commit -m "feat(v9): Phase 141 L19 News Shock Attenuator (fenetres NFP/CPI/FOMC)

Context: Sprint CEO 03/08+2 V5 - ZCode3 chantier C1 (parallele Hermes3).
[...suite du message avec audit SQL reel...]"
# NE PAS git push origin (R28 strict)
```

### Étape 7 : Report à Hermes3

À la fin du chantier Phase 141 :
1. **Branche** : `feat/v9-zcode3-l19-news-shock`
2. **Commits** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode3-l19-news-shock`
3. **Tests verts** : sortie pytest complète (min 5/5 verts)
4. **Diff** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode3-l19-news-shock`
5. **Audit SQL** : chiffres mesurés du trade pendant fenêtres news

Hermes3 merge + push origin + entry DECISIONS_LOG.

### Étape 8 : Phase 143 L20 News Heat Map (après Phase 141)

Mêmes étapes (1-7) sur branche `feat/v9-zcode3-l20-news-heat`.

## 🎁 ANTI-PATTERNS (À ÉVITER)

- ❌ Modifier un fichier core/ partagé sans respecter le pattern existant.
- ❌ `git push origin` (R28 strict, ZCode3 n'est pas opérateur git unique).
- ❌ Commit sans tests verts (R7).
- ❌ Inventer des chiffres (R14).
- ❌ Mélanger 2 phases dans le même commit (R22 strict).

## 📚 RESSOURCES

| Ressource | Chemin |
|---|---|
| Context handbook ZCode2 | `workspace/zcode2/CONTEXT_HANDBOOK.md` |
| Prompts copy-paste V3 | `workspace/zcode/PROMPT_PHASE128_L12_CORRELATION.md` et `PROMPT_PHASE129_L16_ASYMMETRY.md` |
| Modules référence | `core/v9/v9_news_shock_attenuator.py` (à créer), `v9_edge_decay_sentinel.py` (ZCode2 C1 livré) |
| Skills catalogue | `skills/powerflow-v9-*.md` (38 skills) |
| DECISIONS_LOG | `workspace/perplexity/memory/DECISIONS_LOG.md` |
| Checkpoint complet | `docs/CHECKPOINT_SPRINT_CEO_03_08_2026.md` |

## 🔥 PROMPT PUISSANT MODE

Tu as **3-5 jours** pour 2 phases. Bénéfice cible V5 **+2800-3300 pips**.
Architecture parallélisée **Hermes3 × ZCode3** opérationnelle.

**Go MAx. CEO motion activée. R7 + R14 + R22 + R25' + R26 + R28 strict.**

---

## 📦 CONTEXTE COMPLET V5

**Sprint CEO 03/08+1 (V4) finalisé** :
- HEAD : `858fc7c`
- 14 leviers ON
- 192 tests verts cumulés
- Bénéfice projeté 30j : +2038-2788 pips

**Métriques cibles V5** :
- 17-18 leviers ON (+L19 + L20)
- 240+ tests verts
- +2800-3300 pips bénéfice projeté
- 42+ skills catalogue V9

**Doctrine V5 (inchangée)** :
- R2 additif, R6 fail-open, R7 tests verts, R14 git vérité
- R22 sous-unité unique, R25' motion CEO, R26 DECISIONS_LOG, R28 multi-IA

**Crons Ready** : 42/42.
**DB** : 5.1 GB, 27 tables, 64 index, quick_check=ok.
**MCP** : 15 servers registered.

---

*Prompt préparé par Hermes le 2026-08-03 17:50 UTC pour ZCode3 (sprint CEO 03/08+2 V5).*
*Sprint CEO mode « plein pouvoir, pas d'arrêt » V5.*