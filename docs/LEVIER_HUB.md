# LEVIER_HUB.md — Carte des 19 Leviers V10

> **Mise à jour** : 07/08/2026 — Architect pass  
> **Référence** : SOUL.md §3 | PIPELINE_MAP.md  
> **Usage** : Table de référence leviers L1-L19 — poids, état, ΔWR mesuré

---

## Leviers Actifs — Table Maître

| # | Levier | Module | Poids Hub | État | ΔWR mesuré | Seuil validation |
|---|--------|--------|-----------|------|------------|------------------|
| L1 | Buy Pressure (F1) | v10_force.py | 0.30 | ✅ ACTIF | +8.2% | ≥+3% sur 100 signaux |
| L2 | BOS/CHoCH (S8) | v10_structure.py | 0.25 | ✅ ACTIF | +6.1% | ≥+3% |
| L3 | Session Quality | v10_session_quality.py | 0.20 | ✅ ACTIF | +5.4% | ≥+2% |
| L4 | News Gate | v10_context.py | gate dur | ✅ ACTIF | filtrage | R10 |
| L5 | Spread/Liquidité | v10_context.py | gate dur | ✅ ACTIF | filtrage | R10 |
| L6 | VSA State | v10_vsa.py | 0.10 | ✅ ACTIF | +3.8% | ≥+2% |
| L7 | Currency Strength Bias | v10_currency_strength.py | 0.08 | ✅ ACTIF | +2.9% | ≥+1.5% |
| L8 | Multi-TF Confluence | v10_confluence.py | 0.07 | ✅ ACTIF | +3.2% | ≥+2% |
| L9 | Fatman DB Direct | v10_fatman_db_reader.py | — | ✅ ACTIF | source | R9 audit |
| L10 | Currency Behavior | v10_currency_behavior.py | gate | ✅ ACTIF | filtrage | degraded gate |
| L11 | Market Context Global | v10_market_context_global.py | gate | ✅ ACTIF | downgrade | tradeable_pairs |
| L12 | Bayesian Recalibration | v10_bayesian_recalibrator.py | seuils | 🔄 SPRINT | +1.8% estimé | Optuna 100 trials |
| L13 | Fatboy Gate P1 (Harmonie) | v10_fatman_bible_signals.py | gate | ✅ ACTIF | filtrage | Sprint 14 |
| L14 | Fatboy Gate P2 (Safe Haven) | v10_fatman_bible_signals.py | gate | ✅ ACTIF | filtrage | Sprint 14 |
| L15 | Fatboy Gate P3 (Sigma) | v10_fatman_bible_signals.py | gate | ✅ ACTIF | filtrage | Sprint 14 |
| L16 | Sigma Oracle (COILING) | v10_perplexity_sigma_oracle.py | gate | ✅ ACTIF | rescue A2 | Sprint 14 |
| L17 | ICT OTE Filter | v10_ict_ote.py | gate final | ✅ ACTIF | +2.1% | Sprint 4 |
| L18 | SMC Detector (BOS/OB) | v10_smc_detector.py | gate final | ✅ ACTIF | +1.9% | Sprint 4 |
| L19 | RL Adapter | v10_rl_adapter.py | futur | ⏳ PHASE H | TBD | track record Søn |

---

## Vérification Cohérence Σ Poids Hub

```
Poids explicites :
  L1 (Force)           = 0.30
  L2 (Structure)       = 0.25
  L3 (Context/Session) = 0.20
  L6 (VSA)             = 0.10
  L7 (Currency Str.)   = 0.08
  L8 (Confluence)      = 0.07
                       ──────
  Σ                    = 1.00  ✅

Gates durs (pas de poids, booléen) :
  L4 (News), L5 (Spread), L9 (Fatman src),
  L10 (Behavior), L11 (Market Ctx),
  L13-L18 (Fatboy+Sigma+Public Filters)
```

---

## Matrice Compatibilité Inter-Leviers

| Levier A | Levier B | Interaction | Note |
|----------|----------|-------------|------|
| L1 (Force HIGH) | L8 (Confluence) | ✅ Synergie | Multi-TF confirme force = A1 |
| L3 (London Open) | L5 (Spread OK) | ✅ Synergie | Session + liquidité = conditions optimales |
| L4 (News Gate) | L1 (Force) | ⚠️ Override | News annule même si force EXTREME |
| L4 (News Gate) | L8 (Confluence) | ⚠️ Override | News annule même si confluence parfaite |
| L13 (Harmonie) | L15 (Sigma) | 🔄 Séquentiel | Harmonie vérifie d'abord, Sigma arbitre en zone grise |
| L16 (Sigma COILING) | L2 (BOS) | ✅ Rescue | BOS confirmé + COILING → garder A2 au lieu de NONE |
| L17 (ICT OTE) | L18 (SMC BOS) | ✅ Synergie | OTE + BOS récent = confirmation maximale |
| L12 (Bayesian) | L11 (Ctx Global) | 🔄 Calibration | Bayesian affine les seuils du Market Context |
| L6 (VSA MARKUP) | L1 (Force HIGH) | ✅ Synergie | Accumulation VSA + force = direction validée |
| L10 (Behavior degraded) | TOUS | ⚠️ Override | degraded=True downgrade systématique (R10) |

---

## Règles Validation — Ajouter / Garder / Rejeter un Levier

```
✅ GARDER si :
   - ΔWR ≥ +2% mesuré sur ≥ 100 signaux forward test
   - Pas de régression sur les leviers existants
   - Implémenté avec R6 fail-open
   - Tests pytest couverts

⚠️ RÉVISER si :
   - ΔWR entre 0% et +2% → investiguer si résultat sur period spécifique
   - Corrélation > 0.7 avec levier existant → fusionner ou supprimer doublon

❌ REJETER si :
   - ΔWR négatif
   - Casse la règle R6 (exception fatale possible)
   - Pas de couverture pytest
   - Augmente la latence pipeline > 50ms sans gain prouvé

📋 AJOUTER si :
   - Hypothèse edge claire et testable
   - R2 additif pur (aucun module existant modifié)
   - Livraison avec tests + entrée DECISIONS_LOG.md
```

---

## Sprint 15 — Leviers En Focus

| Action | Levier | Objectif |
|--------|--------|----------|
| Calibration | L12 (Bayesian) | Optuna 100 trials, seuils recalibrés |
| Audit | L16 (Sigma Oracle) | Vérifier ratio COILING/RANGING sur Jul-Aug 2026 |
| Docs | L13-L15 (Fatboy) | Documenter les 3 principes dans ce fichier |

---

*Liens* : [SOUL.md](./SOUL.md) | [PIPELINE_MAP.md](./PIPELINE_MAP.md) | [STATE.md](./STATE.md)
