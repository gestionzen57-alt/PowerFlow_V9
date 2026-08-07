# SOUL.md — PowerFlow V10 | Source de Vérité Opérationnelle

> **Mise à jour** : 07/08/2026 — Architect pass (Perplexity MCP)  
> **Branche** : `feat/v9-foundation-clean`  
> **Usage** : Ce fichier EST le cerveau de session. Zcode/Hermes/Søn l'ouvrent en PREMIER.

---

## 0. Chronologie Jalon (table seule — détail dans JOURNAL_PHASES.md)

| Date | Jalon | Statut |
|------|-------|--------|
| 2026-06 | V9 pipeline live MT4 | ✅ |
| 2026-07-18 | V10 architecture pivot SIGNAL-ONLY | ✅ |
| 2026-07-21 | Sprint 03 — RL Adapter + Fatman DB reader | ✅ |
| 2026-08-03 | Sprint 14 — Sigma Oracle + public filters | ✅ |
| 2026-08-07 | Sprint 15 — SOUL v2 + docs architect | 🔄 EN COURS |
| TBD | Phase H — track record Søn validé → micro-lot | ⏳ |

---

## 1. Doctrine Fondamentale (JAMAIS modifier sans consensus CEO)

```
R1  — AGIR : un signal produit → on l'enregistre, on ne l'ignore pas
R2  — ADDITIF PUR : tout nouveau module s'ajoute, ne remplace rien
R4  — VERSIONING : chaque modification est tracée dans DECISIONS_LOG.md
R5  — CHAIN-OF-THOUGHT : chaque signal porte son reasoning complet (cot dict)
R6  — FAIL-OPEN : si un module plante → score neutre 0.50, pas d'exception fatale
R7  — TESTS : tout code livré a ses tests pytest avant merge
R9  — AUDIT : chaque décision est loggée avec source explicite
R10 — CAPITAL PROTÉGÉ : signaux UNIQUEMENT, zéro ordre réel avant Phase H
```

**Critère d'entrée V10 (Phase G)** :
```
tradeable = force_level IN (HIGH, EXTREME)
            AND structure_type IN (BREAK, REJECT, EXTENSION*)
            AND context_state NOT IN (NEWS, ILLIQUIDE)
* EXTENSION uniquement si force = EXTREME
```

---

## 2. Pipeline V10 — 6 Couches

```
┌─────────────────────────────────────────────────────────────────┐
│  COUCHE 1 — DONNÉES BRUTES                                      │
│  MT4 → forces_snapshots (v9_forces.db) + barres OHLCV           │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│  COUCHE 2 — MODULES DE BASE (3 piliers)                         │
│  v10_force.py │ v10_structure.py │ v10_context.py               │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│  COUCHE 3 — ENRICHISSEMENT                                      │
│  v10_vsa.py │ v10_currency_strength.py │ v10_fatman_db_reader.py │
│  v10_currency_behavior.py │ v10_confluence.py                   │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│  COUCHE 4 — SCORING & FILTRES PUBLICS                           │
│  v10_signal_scorer.py │ v10_filter_compositor.py               │
│  v10_ict_ote.py │ v10_smc_detector.py │ v10_session_quality.py  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│  COUCHE 5 — ORCHESTRATION (point d'entrée principal)            │
│  v10_orchestrator.py → compose_signal_with_context()            │
│  → ContextFilteredSignal {signal, context, final_level}         │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│  COUCHE 6 — SORTIE & FEEDBACK                                   │
│  v10_rl_adapter.py │ v10_scanner_behavioral.py                  │
│  v10_alert_dispatcher.py │ Telegram/Discord/VPS                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Modules V10 — Fiche Technique Rapide

| Module | Fichier | Rôle | Poids Hub | Particularité |
|--------|---------|------|-----------|---------------|
| Force | `v10_force.py` | Pression acheteur/vendeur | 0.30 | F1-F8 leviers |
| Structure | `v10_structure.py` | BOS / CHoCH / REJECT | 0.25 | S7-S8 clés |
| Context | `v10_context.py` | Session / News / Vol / Spread | 0.20 | Gate dur |
| VSA | `v10_vsa.py` | Volume Spread Analysis | 0.10 | MARKUP/MARKDOWN |
| Fatman | `v10_fatman_db_reader.py` | Forces devises DB directe | — | Source vérité |
| Currency Strength | `v10_currency_strength.py` | Bias base-quote | 0.08 | Filtre additif |
| Currency Behavior | `v10_currency_behavior.py` | Régime comportemental | — | Gate R10 |
| Confluence | `v10_confluence.py` | Multi-TF alignment | 0.07 | Phase 3 |
| Orchestrator | `v10_orchestrator.py` | Compose les 6 couches | — | Point d'entrée |
| Signal Scorer | `v10_signal_scorer.py` | Score 0..1 + niveau A1/A2/A3 | — | EnhancedSignal |
| Filter Compositor | `v10_filter_compositor.py` | Gate final ICT+SMC+session | — | Sprint 4 |
| ICT OTE | `v10_ict_ote.py` | Optimal Trade Entry ICT | — | Public filter |
| SMC Detector | `v10_smc_detector.py` | Smart Money Concepts | — | BOS/OB |
| Session Quality | `v10_session_quality.py` | Qualité session Forex | — | London/NY/Asia |
| Market Context | `v10_market_context_global.py` | Contexte global multi-TF | — | Couche 3 |
| Bayesian Recalibrator | `v10_bayesian_recalibrator.py` | Seuils recalibrés Phase 16 | — | Optuna |
| Fatman Bible | `v10_fatman_bible_signals.py` | Fatboy Gate 3 principes | — | Sprint 14 |
| Sigma Oracle | `v10_perplexity_sigma_oracle.py` | COILING/RESOLVING/RANGING | — | Sprint 14 |
| Fractal Context | `v10_fractal_context.py` | Contexte fractal multi-TF | — | Phase 23 |
| Grammar V9 | `v10_grammar_v9.py` | Grammaire signaux V9 compat | — | RL input |
| RL Adapter | `v10_rl_adapter.py` | Reinforcement Learning | — | Phase 4 |

---

## 4. Logique de Fusion Hub

```python
# Formule Hub (v10_signal_scorer.py)
composite_score = (
    w_force    * score_force    +   # 0.30
    w_structure * score_structure +  # 0.25
    w_context  * score_context   +   # 0.20
    w_vsa      * score_vsa       +   # 0.10
    w_cs       * score_cs        +   # 0.08  (currency_strength)
    w_conf     * score_confluence    # 0.07  (confluence multi-TF)
)  # Σ = 1.00
```

**Niveaux setup** :
| Score | Niveau | Conditions additionnelles |
|-------|--------|--------------------------|
| ≥ 0.75 | A1 | force IN (HIGH,EXTREME) + structure IN (BREAK,REJECT) + vol IN (NORMAL,HIGH) |
| ≥ 0.55 | A2 | score seul suffit |
| ≥ 0.35 | A3 | score seul suffit |
| < 0.35 | NONE | bloqué |

**Downgrade progressif** (chaque gate) :
```
A1 → A2 → A3 → NONE
```
Gates dans l'ordre : Context Global → Currency Strength → Behavior → Fatboy → Public Filters

---

## 5. Stack Technologique

| Composant | Technologie | Statut |
|-----------|-------------|--------|
| Pipeline data | MT4 EA → SQLite `v9_forces.db` | ✅ Live |
| Core V10 | Python 3.11, dataclasses | ✅ Live |
| Tests | pytest, 1332+ tests | ✅ CI |
| Calibration | Optuna (Bayesian) | 🔄 Sprint 15 |
| Alertes | Telegram Bot | ✅ Live |
| VPS | Ubuntu, cron 5min | ✅ Live |
| RL | Stable-Baselines3 (préparation) | ⏳ Phase H |
| Dashboard | HTML/JS statique | ✅ Live |

---

## 6. Fichiers Critiques — Navigation Rapide

```
docs/
├── SOUL.md              ← CE FICHIER — ouvrir en premier
├── STATE.md             ← État courant du sprint
├── LEVIER_HUB.md        ← Carte des 19 leviers + poids + ΔWR
├── PIPELINE_MAP.md      ← Vue 1-page pipeline + fail-open R6
├── AGENT_PROMPT_MASTER.md ← Prompt universel pour tout agent IA
├── DOCTRINE.md          ← Règles R1-R10 complètes
├── DECISIONS_LOG.md     ← Journal des décisions (R4)
├── ARCHITECTURE.md      ← Vue architecture détaillée
└── JOURNAL_PHASES.md    ← Historique complet des phases

core/v10/
├── v10_orchestrator.py  ← Point d'entrée compose_signal_with_context()
├── v10_signal_scorer.py ← Scoring + EnhancedSignal
└── [67 modules total]   ← voir INDEX_MODULES.md
```

---

## 7. Tables Décision — Session

| Session | UTC | Qualité | Paires prioritaires |
|---------|-----|---------|--------------------|
| London Open | 07:00-09:00 | ⭐⭐⭐ | EURUSD, GBPUSD, EURGBP |
| London | 07:00-12:00 | ⭐⭐⭐ | Toutes majeures |
| NY Open | 13:00-15:00 | ⭐⭐⭐ | EURUSD, USDCAD, GBPUSD |
| London/NY Overlap | 12:00-16:00 | ⭐⭐⭐ | Volume max |
| NY | 13:00-21:00 | ⭐⭐ | USD pairs |
| Asia | 22:00-07:00 | ⭐ | USDJPY, AUDUSD |
| Dead Zone | 21:00-23:00 | ❌ | NO TRADE |

---

## 8. Tables Décision — Volatilité

| Régime Vol | ATR relatif | Action |
|------------|-------------|--------|
| EXTREME | > 3× ATR14 | BLOQUER (gate dur) |
| HIGH | 1.5-3× ATR14 | OK si force HIGH+ |
| NORMAL | 0.7-1.5× ATR14 | OK standard |
| LOW | < 0.7× ATR14 | Spread élargi → vérifier |
| ILLIQUIDE | spread > 3× normal | BLOQUER (gate dur) |

---

## 9. Tables Décision — Fusion & Gates

| Gate | Condition FAIL | Action | Doctrine |
|------|---------------|--------|----------|
| Context Global | tradeable=False | downgrade progressif | R6 fail-open |
| Behavior | degraded=True | downgrade comme ctx | R10 capital |
| Currency Strength | \|bias\| < min_bias | downgrade progressif | R2 additif |
| Fatboy Gate | principe échoue | downgrade progressif | Sprint 14 |
| Sigma Oracle | RANGING | → NONE | Sprint 14 |
| Public Filters | session/OTE/SMC/regime | downgrade final | Sprint 4 |
| News Gate | NO_TRADE_ZONE | tradeable=False | R10 |
| Spread Gate | ILLIQUIDE | tradeable=False | R10 |

---

## 10. Résultats Empiriques (Phase G validés)

| Métrique | Valeur | Période | Note |
|----------|--------|---------|------|
| WR global A1+A2 | ~58-62% | Jul-Aug 2026 | Forward test signaux |
| WR A1 seul | ~68-72% | Jul-Aug 2026 | Setup optimal |
| RR moyen | 1:2.1 | Jul-Aug 2026 | SL structure |
| Taux A1 | ~15% des signaux | — | Sélectif |
| Taux NONE (filtré) | ~40% | — | Gates efficaces |

> ⚠️ **Avertissement Phase 180** : résultats sur signaux seuls (ZERO ordre réel). Validation track record Søn requise avant Phase H (micro-lot).

---

## 11. Contacts & Ownership

| Rôle | Responsabilité |
|------|---------------|
| **Søn (CEO)** | Décisions stratégiques, validation Phase H, capital |
| **Zcode** | Implémentation sprint, tests pytest, push code |
| **Hermes** | Monitoring VPS, alertes, crons |
| **Perplexity (Architecte)** | SOUL.md, docs, revue architecture, push MCP |

---

*Ce fichier est la source de vérité. En cas de contradiction avec un autre doc → SOUL.md prime.*  
*Liens* : [LEVIER_HUB.md](./LEVIER_HUB.md) | [PIPELINE_MAP.md](./PIPELINE_MAP.md) | [STATE.md](./STATE.md) | [DECISIONS_LOG.md](./DECISIONS_LOG.md)
