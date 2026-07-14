---
name: powerflow-doctrine-evolution
description: "Méthodologie pour challenger une doctrine de marché existante — passer d'une règle statique à une doctrine adaptative. Compatible R7 assoupli (régression justifiée par DECISIONS_LOG) et R25' assoupli (mandat CEO explicite)."
version: 1.1.0
author: powerflow-m3-align
tags: [powerflow, doctrine, methodology, evolution, calibration, r7-assoupli, r25-assoupli]
statut: actif
derniere_maj: 2026-07-14
note_chantier: aligne au HEAD 080fb3f (1277 verts + 2 skipped + 0 fail, 4 règles assouplies 2026-07-14)
---

# Powerflow Doctrine Evolution

# PowerFlow Doctrine Evolution

## Rôle
Méthodologie pour faire évoluer une doctrine de marché quand les conditions changent (régime, volatilité, structure). Évite le surapprentissage et la doctrine figée.

## Compatibilité 2026-07-14 — 4 règles assouplies (DOCTRINE.md)

Suite à la motion CEO Søn « assouplissement des 4 » (2026-07-14), la
doctrine V9 a été assouplie sur 4 règles structurantes :

- **R7** (zéro régression) : assoupli en « zéro régression **non
  justifiée** ». Toute régression de comportement doit être
  accompagnée d'une entrée DECISIONS_LOG explicative. Cette skill
  illustre parfaitement le nouveau R7 : faire évoluer une doctrine
  = introduire un changement de comportement, à justifier.

- **R25'** (promotion SHADOW→ACTIVE) : assoupli « sauf mandat CEO
  explicite contraire ». Les motions CEO « go global » successives
  (« go activer tous », « go r28 », « go la suite ») constituent des
  mandats explicites couvrant un périmètre autorisé de promotions.

- **R22** (1 session = 1 périmètre) : assoupli « sauf chantier complexe
  découpé en sous-unités ». Une évolution doctrinale peut être livrée
  en plusieurs commits si chaque sous-unité est autonome.

- **R28** (Hermes opérateur git unique) : assoupli « sauf instruction
  directe et explicite de Søn ». Le push direct reste la norme, motion
  CEO explicite = délégation de push.

Référence : `docs/DOCTRINE.md` (c560506) + DECISIONS_LOG §2026-07-14.

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

## Justification de régression (R7 assoupli 2026-07-14)

Toute évolution doctrinale introduisant un changement de comportement
doit être accompagnée d'une entrée DECISIONS_LOG explicitant :

- **Progrès attendu** : pourquoi la nouvelle règle est meilleure que
  l'ancienne (gain de WR, réduction du risque, etc.)
- **Coût de la régression** : ce qu'on perd (cas où l'ancienne règle
  était meilleure, false positives évités, etc.)
- **Critère de rollback** : si WR@N chute sous le seuil baseline, on
  revient en X temps

Template :
```markdown
## R7-justification — [évolution #N]
**Progrès attendu** : WR +X% sur Y décisions
**Coût de la régression** : Z cas historiques défavorables
**Critère de rollback** : WR < W% sur V décisions en U jours
**Date d'effet** : YYYY-MM-DD
```

## Garde-fous
- **Recalibration > 24h** post-fix obligatoire (cf. style CEO §3 blocages durs).
- Ne JAMAIS archiver une règle sans backup dans `docs/archive/doctrines/`.
- Versionner chaque doctrine : `doctrine_v{N}_{slug}.md`.
- R7-justification tracée dans DECISIONS_LOG avant tout commit de
  modification de comportement (pas une régression silencieuse).

## Pièges
- Surapprentissage : calibration sur période trop courte (<200 décisions).
- Oublier le régime filter → règle H1 battue par H2 car VIX différent.
- Promouvoir sans paper-trade → "regression to mean" en prod.
- R7 nouvelle formulation : confondre "régression justifiée" (OK,
  tracée) et "régression silencieuse" (interdite). Toute régression
  non documentée est une violation R7.
