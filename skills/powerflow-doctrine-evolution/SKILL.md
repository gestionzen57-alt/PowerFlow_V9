---
name: powerflow-doctrine-evolution
description: "Méthodologie pour challenger une doctrine de marché existante — passer d'une règle statique à une doctrine adaptative"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, doctrine, methodology, evolution, calibration]
---

# Powerflow Doctrine Evolution

# PowerFlow Doctrine Evolution

## Rôle
Méthodologie pour faire évoluer une doctrine de marché quand les conditions changent (régime, volatilité, structure). Évite le surapprentissage et la doctrine figée.

## Quand charger
- WR d'une fenêtre chute >10% sur 30 jours glissants.
- Nouveau régime détecté (VIX, risk-on/off, central bank).
- Søn demande "pourquoi ça marche plus ?" / "il faut challenger la règle".

## 5 étapes
1. **Recueil** — extraire règles actives depuis `learned_rules` (cf. `config_strategy_rules` MCP 3113).
2. **Diagnostic** — WR par régime, par session, par timeframe. Identifier surapprentissage (window=15min WR=80% mais WR@120min=45%).
3. **Challenge** — formuler 3 hypothèses alternatives : "la règle X est obsolète car Y", "le régime Z n'était pas dans le training set".
4. **Test** — backtest A/B sur fenêtre glissante 90j avec paper-trade 2 semaines.
5. **Décision** — promouvoir / déclasser / archiver. MAJ `docs/DOCTRINE_LECTURE_MARCHE.md`.

## Format hypothèse
```markdown
## Doctrine évolution #N — [règle challengée]
**Règle actuelle** : "trend_following strict, meanrev_low_only si WR<55%"
**Observation** : WR 32% sur 14 jours (vs baseline 60%)
**Hypothèse H1** : Régime changé → safe_haven dominant, meanrev adapté
**Hypothèse H2** : Bug fix UNKNOWN=578 a reclassifié 578 ancres, calibration à refaire
**Test** : backtest 90j + paper-trade 14j avec règle candidate
**Seuil promotion** : WR ≥ 60% sur 200 décisions minimum
```

## Garde-fous
- **Recalibration > 24h** post-fix obligatoire (cf. style CEO §3 blocages durs).
- Ne JAMAIS archiver une règle sans backup dans `docs/archive/doctrines/`.
- Versionner chaque doctrine : `doctrine_v{N}_{slug}.md`.

## Pièges
- Surapprentissage : calibration sur période trop courte (<200 décisions).
- Oublier le régime filter → règle H1 battue par H2 car VIX différent.
- Promouvoir sans paper-trade → "regression to mean" en prod.

