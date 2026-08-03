# PLAN QUANTIQUE V11+ V5 — Sprint CEO 03/08+2 (2026-08-04)

> **Héritage** : PLAN_QUANTIQUE_V11_PLUS_V4_20260803.md (V4 finalisé 03/08).
> Ce document est la mise à jour V5 du plan quantique — focus news-driven
> risk management (L19 + L20) et clôture audit live.
>
> **Mode CEO no-stop** : « optimisation max, plein pouvoir, pas d'arrêt ».

## Vision V5 — News-driven risk management

Le sprint V5 introduit **2 nouveaux leviers quantiques news-driven** qui
travaillent en composition multiplicative (MIN des deux = le plus restrictif
gagne) :

1. **L19 News Shock Attenuator** : modulation temporelle du sizing selon la
   fenêtre news (pre_news / imminent / post_news / normalisation / normal).
2. **L20 News Heat Map** : modulation spatiale (symbol × news_type) selon la
   chaleur historique de la réaction d'une paire à un type de news.

Ensemble, ces 2 leviers permettent d'écraser les pires combinaisons news
(USDCHF × NFP, USDCAD × NFP) tout en préservant les paires résilientes
(GBPUSD, XAUUSD).

## Architecture composition V5

```
L19 (fenetre news)        L20 (heat map symbol x news_type)
     │                              │
     ▼                              ▼
  minutes_factor           heat_map_base
  (0.0 / 0.5 / 0.8 / 1.0)  (0.0 / 0.5 / 0.7 / 1.0)
     │                              │
     └────────────── MIN ───────────┘
                    │
                    ▼
           sizing_final (R6 fail-open)
                    │
                    ▼
            trade_engine.sizing()
```

**Règle MIN** : le plus restrictif gagne. Si L19 = 0.0 (HALT imminent) ET
L20 = 0.5 (heat map modérée) → sizing = 0.0 (HALT). Si L19 = 1.0 (normal)
ET L20 = 0.0 (USDCHF × NFP blacklisted) → sizing = 0.0 (HALT).

## Phase 141 — L19 News Shock Attenuator ✅ LIVRÉ

**Commit** : `5878550` — 33/33 tests verts en 0.28s.

**Logique** :
- `15 <= m <= 60` → `(0.5, "pre_news")` (45 min atténuation)
- `0 <= m < 15` → `(0.0, "imminent")` (HALT)
- `-15 <= m < 0` → `(0.5, "post_news")` (15 min post-impact)
- `-60 <= m < -15` → `(0.8, "normalisation")` (45 min)
- autre → `(1.0, "normal")` (hors fenêtre)

**Audit SQL live 03/08 (R14, n=337 paper_trades 30j)** :
- `normal_spread` (1.5-2.0) : n=215, WR 53.0%, PNL -245.8 pips
- `wide_spread` (2.0-3.0, proxy news) : n=122, WR **18.0%**, PNL **-619.4 pips**

→ Fenêtre news détruit **2.7× plus** de pips/trade. Justification R14 directe.

**Gain projeté** : 40-80 pips / cycle.

## Phase 143 — L20 News Heat Map ✅ LIVRÉ

**Commit** : `41048b2` — 44/44 tests verts en 1.39s.

**Univers** : 5 paires (EURUSD / USDJPY / XAUUSD / GBPUSD / AUDUSD) × 4 types
news (NFP / CPI / FOMC / ECB) = **20 cellules** encodées.

**Heat map (base_multiplier)** :
- USDCHF × NFP/CPI/FOMC : 0.0 (blacklist — WR 10.5%, -5.92 pips)
- USDCAD × NFP/CPI/FOMC : 0.0 (blacklist — WR 0%, -9.38 pips)
- EURUSD × ECB : 0.5 (fragile — WR 16.3%, -4.69 pips)
- AUDUSD × NFP/CPI : 0.7 (fragile — WR 28.6%, -3.53 pips)
- GBPUSD × (tous) : 1.0 (résilient — WR 63.4%, -0.26 pips)
- XAUUSD × (tous) : 1.0 (safe — non capturé, fallback 1.0)
- Default (unknown symbol) : 1.0 (R6 fail-open)

**Composition** : `final = MIN(heat_map_base, minutes_factor)`.

**Gain projeté** : 60-100 pips / cycle.

## Phase 142 — ROADMAP V5 + PLAN V5 finalisé (en cours)

**Livrables** :
- `docs/ROADMAP.md` (V5) ✅
- `docs/audits/PLAN_QUANTIQUE_V11_PLUS_V5_20260804.md` (ce doc) ✅
- 2 skills catalogue V5 (L19 + L20) ✅ (déjà dans commit Phase 141 + 143)

## Phase 145 — Audit live mardi 04/08 (24h post-activation)

**Quand** : 04/08 18:00 UTC (24h après activation L7+L8+L9+L11+L13+L17×2).

**Livrable** : `docs/audits/PHASE145_AUDIT_LIVE_20260804.md` avec SQL live.

**Métriques à capturer** :
- WR global 24h post-activation
- PNL par régime (trending / ranging / news)
- PNL par session (asie / london / ny)
- Niches confirmées / contredites
- Drawdown max 24h

**Kill switches surveillés** : V9_L7_HEATMAP_ENABLED, V9_L8_*, V9_L9_*,
V9_L11_GBPUSD_BOOST_ENABLED, V9_L13_VOL_TP_SL_ENABLED, V9_L17_CROSS_*.

## Phase 146 — Audit live vendredi 08/08 (semaine)

**Quand** : 08/08 18:00 UTC (semaine post-activation).

**Livrable** : `docs/audits/PHASE146_AUDIT_LIVE_20260808.md` avec stats
cumulées semaine.

**Métriques** :
- WR semaine
- PNL cumulé
- Bénéfice projeté 30j actualisé (vs V4 +2038-2788p, cible V5 +2800-3300p)
- Leviers confirmés vs à recalibrer
- Recommandations pour V6 (Phase 148+)

## Phase 147 — Push final + bilan CEO V5

**Livrables** :
- Push final sur `origin/feat/v9-foundation-clean` (déjà fait par phases)
- `workspace/perplexity/memory/DECISIONS_LOG.md` entrée clôture V5
- Bilan CEO V5 dans `docs/BILAN_CEO_SPRINT_V5_20260804.md`

**Métriques clôture** :
- 28 commits sprint CEO (V3 + V4 + V5)
- 15 leviers quantiques ON
- 269 tests verts cumulés (192 V4 + 33 L19 + 44 L20)
- 40 skills catalogue V9 (38 V4 + L19 + L20)
- 144 phases livrées
- Bénéfice projeté 30j : +2800-3300 pips

## Doctrine sprint V5

Identique V3+V4 (cf. ROADMAP.md §Doctrine sprint V5).

## Périmètre GELÉ (rappel)

- Phase 10 : Fédération d'agents (gelé jusqu'à V6)
- Skills auto-générés avant canonisation (gelé)
- Exécution d'ordres réelle avant Phase 12 (gelé)

## Anomalies V5 documentées

1. **Branche active ≠ branche annoncée** : sprint ouvert sur
   `feat/v9-zcode3-l19-news-shock` au lieu de `feat/v9-foundation-clean`
   (brief V5 désaligné). Resync : checkout feat/v9-foundation-clean, refait
   commits 5878550 et 41048b2 propres.
2. **Secret leak prevention** : ajout `.gitignore` pattern
   `backups/token_rotation_*/` (3 fichiers .json.bak jamais versionnés).
3. **Dette technique pré-V4** : 72-76 tests F documentés (hors périmètre
   sprint CEO V5, à traiter en Phase 144 sprint dédié).
4. **test_arbiter:552 préexistant** : 1 F motion CEO 28/07 "context_unavailable"
   vs "disabled" — à fixer dans Phase 144.

## Prochaine étape

- Phase 145 audit live mardi 04/08 18:00 UTC (24h post-activation)
- Phase 146 audit live vendredi 08/08 18:00 UTC (semaine)
- Phase 144 fix dette technique pré-V4 (sprint dédié futur, 2-3 j)

**Sprint CEO 03/08+2 V5 = NEWS-DRIVEN RISK MANAGEMENT. Architecture
parallélisée Hermes3 × ZCode3 validée. 2 leviers ON à activer (motion
CEO requise). Bénéfice cible 30j +2800-3300 pips.**
