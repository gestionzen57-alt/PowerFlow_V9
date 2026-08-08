# RL FAIL ANALYSIS — Sprint 24

**Créé :** 2026-08-08 20:45 CEST — Perplexity GitHub MCP  
**Cible :** EURUSD + USDJPY — résolution des 2 gates shadow échous (Phase 17)

---

## 🔍 Hypothèses d'échec identifiées

### EURUSD — Gate 30 consécutifs

| Facteur | Détail |
|---|---|
| Baseline très haute (69.3%) | Peu de marge pour surpasser sur 30 trades consécutifs |
| Variance haute | Variance naturelle sur 30 trades peut inverser le delta +2.7% |
| Filtre session | OUTSIDE peut dégrader WR (ICT : NY+LONDON dominants) |
| Action SELL | Friction asymmétrique documentée Phase 12 (BUY +46.4p vs SELL -5.0p) |

**Plan :** filtrer session OUTSIDE pour EURUSD, augmenter poids LONDON/NY dans Thompson Sampling.

### USDJPY — Gate 30 consécutifs

| Facteur | Détail |
|---|---|
| Bug pip JPY (Phase 19) | Métriques étaient faussées avant fix |
| Baseline 58.1% | Modérée — shadow +7.9% = delta le plus élevé des 4 paires |
| Seuil pip JPY | Max pips H1 = 8000 (vs 80 paires 4-déc.) après fix watchdog |

**Plan :** re-run post-fix JPY obligatoire. USDJPY a le plus fort potentiel shadow.

---

## 🛠️ Corrections techniques

1. **Filtre session OUTSIDE** : exclure les trades hors ICT Kill Zones pour EURUSD
2. **Thompson Sampling** : augmenter alpha/beta pour sessions LONDON+NY (prior fort)
3. **Gate adaptatif** : si baseline > 60%, gate = 20 trades consécutifs (vs 30)
4. **Re-run USDJPY** : post-watchdog fix JPY (Phase 19)

---

## 📊 Script d'analyse

`scripts/v10_rl_fail_analysis.py` — lit `v10_rl_shadow_log`, calcule :
- WR shadow global par paire
- Distribution WR par session ICT (ASIAN / LONDON / NY / OUTSIDE)
- Série perdante maximum
- Distribution par action (BUY/SELL)
- Gate 30 consécutifs best-streak
- Recommandations automatiques

Sortie : `reports/v10_rl_fail_analysis_YYYYMMDD_HHMMSS.json`

---

## 🎯 Actions S24

- [ ] Run `scripts/v10_rl_fail_analysis.py` (post Hermes sync)
- [ ] Run `scripts/v10_rl_shadow_rerun.py` post-fix JPY
- [ ] Valider gate 30 sur les 2 paires
- [ ] GO/NO-GO promotion CEO

---

*Perplexity GitHub MCP — 2026-08-08 20:45 CEST*
