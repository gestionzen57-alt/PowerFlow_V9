# PROMPT ZCode2 — Phase 141 L19 News Shock Attenuator

> **Copy-paste ce prompt dans ta session Z.ai (ZCode CLI)**
> Chantier ZCode2 = branche `feat/v9-zcode2-l19-news-shock` (0 push).
> **Démarre après Phase 140 livrée.**

---

## MISSION — Phase 141 : L19 News Shock Attenuator

**Hypothèse** : Les annonces économiques (NFP, CPI, FOMC) créent des spikes
de volatilité où les edges techniques sont moins fiables. Atténuer le
sizing pendant les fenêtres news (15 min avant/après) réduit les pertes.

**Logique** :
- News upcoming (15 min avant) : sizing ×0.5 (précaution)
- News imminent (5 min avant) : sizing ×0.0 (HALT)
- News passé (5 min après) : sizing ×0.5 (retour progressif)
- News passé (15 min après) : sizing ×1.0 (normal)

**Audit SQL live attendu** : trades pendant fenêtres news vs hors news.

**Gain projeté** : 40-80 pips (réduction pertes news).

**Effort** : 1-2 jours.

## TRAVAIL

### 1. Branche
```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode2-l19-news-shock
```

### 2. Module NEW
**Fichier** : `core/v9/v9_news_shock_attenuator.py`

API :
```python
def news_shock_attenuator_enabled() -> bool:
    """Kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED (defaut OFF, R25')."""

def get_news_window_multiplier(
    minutes_to_news: int,
) -> tuple[float, str]:
    """Retourne (multiplier, phase) selon minutes_to_news.

    Logique :
      - 15 <= minutes_to_news <= 60 : ×0.5 (pre_news)
      - 0 <= minutes_to_news < 15    : ×0.0 (imminent / HALT)
      - -15 <= minutes_to_news < 0   : ×0.5 (post_news)
      - -60 <= minutes_to_news < -15  : ×0.8 (normalisation)
      - autre                        : ×1.0 (normal)

    Returns:
      (multiplier, phase_label)
    """
```

### 3. Kill switch + .env (même pattern que L18)

### 4. Tests (min 5)
**Fichier** : `tests/test_v9_news_shock_attenuator.py`

Cas :
1. Kill switch OFF → multiplier = 1.0
2. minutes_to_news = 30 → ×0.5 (pre_news)
3. minutes_to_news = 5 → ×0.0 (imminent)
4. minutes_to_news = -10 → ×0.5 (post_news)
5. minutes_to_news = 100 → ×1.0 (normal)

### 5. Commit atomique (R26, R22)
```bash
cd C:/projet/V9
git add core/v9/v9_news_shock_attenuator.py core/v9/kill_switches.py \
        config/v9_kill_switches.env tests/test_v9_news_shock_attenuator.py
git commit -m "feat(v9): Phase 141 L19 News Shock Attenuator"
# NE PAS git push origin (R28 strict)
```

### 6. Report à Hermes2 (même format que Phase 140)

---

**Go. Tu as 1-2 jours. Démarre après Phase 140 livrée.**

*Prompt préparé par Hermes le 2026-08-03 07:30 UTC pour ZCode2.*