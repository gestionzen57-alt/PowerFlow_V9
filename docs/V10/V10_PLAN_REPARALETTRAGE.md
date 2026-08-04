# 🔄 V10 — Reparalettage de V9 sur TA lecture

> **Mission** : transformer V9 (infrastructure mature mais stratégie
> inventée) en V10 (système aligné sur TA lecture du marché).
>
> **Philosophie** : V9 voyait des chiffres. V10 verra ce que TU vois.
>
> **Date** : 2026-08-04
> **Auteur** : Hermes (CEO Søn mandate "reparalettage compréhension")
> **Statut** : Plan directeur, à itérer après réponse CEO

---

## 🎯 ÉTAT DES LIEUX — POURQUOI V10

### Ce que V9 a fait (à conserver)
```
✅ INFRASTRUCTURE (Phase 175-180, 100% saine)
   - capture_server : port 31685 stable, PID 5128 (5h+ uptime)
   - DB v9_forces.db (6.4 GB, 27 tables, 41k signaux/5min)
   - Pipeline cognitif 9 modules : scene_builder, behavior_analyzer,
     window_gate, exploitability_evaluator, regime_detector,
     zone_detector, principle_engine, signal_generator, decision_logger
   - Doctrine R0-R30 (30 règles gouvernance)
   - 134+ tests verts cumulés (42 + 13 + 8 par phase)
   - 12 MCP tools (filesystem, sqlite, telegram, pipeline, meta-agent)
   - 6 skills catalogue Hermes (edge-fund, market-reader, etc.)
   - Alerter Telegram (Phase 179) : daemon auto, daemon install
   - Risk management (5 paliers DD + risk parity 5 paires)
   - 3 skills patchés (mcp-architecture, telegram-bidirectional, yaml-runtime)
   - Audit integrity check (Phase 180) : script rejouable, 8 tests
```

### Ce que V9 a mal fait (à jeter)
```
❌ STRATÉGIE (Phase 180 audit, 100% fausse)
   - paper_trades = 337 clôturés, WR 44.51%, PnL -865 pips
   - Edge fictif 90.33% WR / +27239 pips / Sharpe 0.845
     (confusion avec features ML datasets JSONL)
   - 42 groupes de doublons cachés (bug insertion)
   - Bug d'insertion paper_trade_engine (snapshot successif
     → nouveau trade_id au lieu d'UPDATE)
   - Edge decay 17→24/07 : WR 100% → 12% (overfitting 3 jours)
   - Le pipeline cognitif applique des features que TU n'utilises PAS
     (zone_type, coalition_strength, pliure, etc. — terminology
     interne V9, pas alignée sur TA lecture)

❌ PROMESSE CASSÉE
   - AGENTS.md affichait "Hedge Fund Mondial" avec des chiffres faux
   - L'infrastructure est honnête (logs, DB, tests) mais la STRATÉGIE
     est du theater (calibrée sur backtest, pas sur TA lecture)
```

### Le pivot fondamental
```
AVANT (V9) :
  Données brutes → features V9 inventées → paper_trade → chiffres faux

APRÈS (V10) :
  Données brutes → TA lecture (features) → détection contexte
  → alerte CEO (PAS d'auto-trade) → validation manuelle → track record réel
```

---

## 🏗️ ARCHITECTURE V10 — 4 COUCHES (alignées sur TA lecture)

### Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 — DÉCISION (CEO-driven)                            │
│  Alerter Telegram → Søn analyse le chart manuellement       │
│  → Søn décide : entry / skip / wait                          │
│  → Track record Søn (pas auto)                               │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 3 — CONTEXTE (ce que TU lis)                         │
│  Session (Asia/London/NY) | News proximity | Range journalier│
│  Structure dominante | Volatilité regime                     │
│  → MODULE V10 : "Contexte" — sortie : C1..C7                 │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 2 — STRUCTURE (ce que TU vois)                       │
│  Support/Résistance | Trendlines | Patterns | Order blocks  │
│  Zones institutionnelles | Liquidity pools                   │
│  → MODULE V10 : "Structure" — sortie : S1..S9               │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 1 — FORCE (ce que TU sens)                           │
│  Domination acheteurs/vendeurs | Volatilité | Spread         │
│  Volume | Tick activity | Range vs trend                     │
│  → MODULE V10 : "Force" — sortie : F1..F5                    │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 0 — DONNÉES BRUTES (V9 conservé)                     │
│  capture_server (port 31685) → DB v9_forces.db (forces)     │
│  schema : symbol, timestamp, open, high, low, close,         │
│  volume, spread, regime, etc. (déjà ingéré par capture)      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 PLAN D'EXÉCUTION — 11 PHASES (90 jours)

### PHASE A — CAPTURE DE TA LECTURE (SEMAINE 1-2)

**Objectif** : formaliser ce que TU vois en features mesurables.

**Actions** :
```
A1. Entretien CEO (60-90 min) : Søn explique sa lecture à Hermes
    - Sur 5-10 trades récents (Søn a ses propres trades manuels)
    - Format : "je vois X parce que Y, dans le contexte Z"
    - Sortie : transcription brute, 1-2h d'enregistrement

A2. Structuration des features (Hermes, 4-6h)
    - Pour chaque "X" identifié par Søn :
      * Mesurable sur les bougies ? (oui/non/partiellement)
      * Quels champs DB faut-il ajouter ? (ALTER TABLE)
      * Quel calcul ? (SQL/Python/indicateur)
    - Sortie : TABLEAU_FEATURES_V10.md (~30 features)

A3. Validation du glossaire (CEO, 30 min)
    - Søn relit TABLEAU_FEATURES_V10.md
    - Valide que chaque feature correspond à ce qu'il VOIT
    - Ajuste les noms/termes pour qu'ils matchent SA vision
    - Sortie : TABLEAU_FEATURES_V10.md VALIDÉ

Livrables Phase A :
  - docs/V10/TRANSCRIPTION_LECTURE_SON.md (1-2h d'audio transcrit)
  - docs/V10/TABLEAU_FEATURES_V10.md (~30 features)
```

**Doctrine** : R18 (pas de LLM dans la boucle cognitive), R2 additif
(que des nouveaux fichiers `docs/V10/`), R7 (chaque feature testée
unitairement).

---

### PHASE B — SCHÉMA DB V10 (SEMAINE 2-3)

**Objectif** : adapter la DB pour stocker les features V10 sans casser V9.

**Actions** :
```
B1. Audit schéma V9 (Hermes, 1h)
    - Lister tables/colonnes existantes dans data/v9_forces.db
    - Identifier quelles colonnes V9 sont inutiles
    - Sortie : DB_SCHEMA_AUDIT.md

B2. Création tables V10 (R2 additif, 0 modif V9)
    - Nouvelle DB data/v10_features.db (séparation V9/V10)
    - Tables : v10_force_state, v10_structure_state, v10_context_state
    - Colonne v10_signal_id (unique) pour traçabilité
    - Sortie : scripts/v10_init_db.py + tests/test_v10_db_schema.py

B3. Migration donnees brutes V9 → V10
    - Lire forces_snapshots de v9_forces.db
    - Calculer features V10 (selon TABLEAU_FEATURES_V10.md)
    - Insérer dans v10_features.db
    - Sortie : scripts/v10_migrate_from_v9.py + tests

B4. Tests schema (Hermes, 2h)
    - INSERT/SELECT/UNIQUE constraint
    - Volume : 1 semaine de données (10k+ lignes attendues)
    - Sortie : tests/test_v10_db_schema.py (5+ tests verts)

Livrables Phase B :
  - data/v10_features.db (nouvelle DB, isolée de v9_forces.db)
  - scripts/v10_init_db.py
  - scripts/v10_migrate_from_v9.py
  - tests/test_v10_db_schema.py (5+ tests)
```

**Doctrine** : R2 additif (V9 intact), R8 (backup MD5 avant modif DB),
R22 (1 périmètre = schéma DB), R7 (tests verts avant commit).

---

### PHASE C — MODULE FORCE (SEMAINE 3-4)

**Objectif** : coder le module qui calcule les features COUCHE 1.

**Actions** :
```
C1. Implémenter calculs "Force" (Hermes, 6-8h)
    - F1 : Ratio acheteurs/vendeurs (delta prix × volume)
    - F2 : Volatilité réalisée (ATR sur N bougies)
    - F3 : Spread normalisé (spread / ATR)
    - F4 : Volume relatif (volume / moyenne mobile volume)
    - F5 : Tick activity (variations de prix par minute)
    - Fichier : core/v10/v10_force.py
    - Tests : tests/test_v10_force.py (5+ tests, 1 par feature)

C2. Validation sur données historiques (Hermes, 2h)
    - Appliquer sur juillet 2026 (forces_snapshots V9)
    - Vérifier cohérence : un trade "gagnant" du passé Søn
      correspond à F1 dominant et F4 élevé ?
    - Sortie : docs/V10/FORCE_VALIDATION_JUILLET2026.md

Livrables Phase C :
  - core/v10/v10_force.py
  - tests/test_v10_force.py (5+ tests)
  - docs/V10/FORCE_VALIDATION_JUILLET2026.md
```

**Doctrine** : R18 (pas de LLM), R2 (nouveau module `core/v10/`),
R7 (chaque feature testée sur données réelles juillet 2026).

---

### PHASE D — MODULE STRUCTURE (SEMAINE 4-5)

**Objectif** : coder le module qui détecte les features COUCHE 2.

**Actions** :
```
D1. Implémenter détection "Structure" (Hermes, 8-10h)
    - S1 : Support/Résistance horizontaux (pivots hauts/bas)
    - S2 : Trendlines (régression linéaire sur swing points)
    - S3 : Patterns chandelles (engulfing, hammer, doji, etc.)
    - S4 : Order blocks (dernier m15 против avant cassure)
    - S5 : Zones institutionnelles (N rounds de prix)
    - S6 : Liquidity pools (equal highs/lows)
    - S7 : Structure de marché (HH/HL vs LH/LL = trend vs range)
    - S8 : Break of structure (BOS) vs change of character (CHoCH)
    - S9 : Premium/Discount zones (50% equilibrium)
    - Fichier : core/v10/v10_structure.py
    - Tests : tests/test_v10_structure.py (9+ tests)

D2. Validation Søn (CEO, 60 min)
    - Søn compare 10 structures détectées vs ce qu'il voit
    - Accord sur terminologie (ex: "BOS" vs "cassure")
    - Ajustement paramètres (fenêtre lookback, tolérance)
    - Sortie : docs/V10/STRUCTURE_VALIDATION_SON.md

Livrables Phase D :
  - core/v10/v10_structure.py
  - tests/test_v10_structure.py (9+ tests)
  - docs/V10/STRUCTURE_VALIDATION_SON.md
```

**Doctrine** : alignement strict sur TERMINOLOGIE SØN. Si Søn appelle
"cassure" ce que ICT appelle "BOS", on adopte "cassure" partout.

---

### PHASE E — MODULE CONTEXTE (SEMAINE 5-6)

**Objectif** : coder le module qui détecte les features COUCHE 3.

**Actions** :
```
E1. Implémenter "Contexte" (Hermes, 4-6h)
    - C1 : Session (Asia 00-08 UTC, London 08-16, NY 13-22, overlap 13-16)
    - C2 : News proximity (event < 30min = NO_TRADE_ZONE)
    - C3 : Range journalier (high-low day vs ATR)
    - C4 : Vol regime (VIX-like, realised vol, vol-of-vol)
    - C5 : Day of week (lundi violent, vendredi creux)
    - C6 : Spread regime (large = illiquide = NO_TRADE)
    - C7 : Correlation regime (DXY trending = USD pairs trending)
    - Fichier : core/v10/v10_context.py
    - Tests : tests/test_v10_context.py (7+ tests)

E2. Validation Søn (CEO, 30 min)
    - Søn valide les seuils (ex: news < 30min, pas < 60min)
    - Ajustement des heures de session si Søn trade différemment
    - Sortie : docs/V10/CONTEXT_VALIDATION_SON.md

Livrables Phase E :
  - core/v10/v10_context.py
  - tests/test_v10_context.py (7+ tests)
  - docs/V10/CONTEXT_VALIDATION_SON.md
```

**Doctrine** : R6 fail-open (news API down → C2 = NO_TRADE_ZONE par
défaut, pas de bug en cascade).

---

### PHASE F — PIPELINE V10 (SEMAINE 6-7)

**Objectif** : orchestrer les 3 modules en chaîne.

**Actions** :
```
F1. Orchestrateur V10 (Hermes, 4h)
    - core/v10/v10_orchestrator.py
    - Reçoit les forces (V9 capture_server)
    - Calcule F1-F5 (module Force)
    - Calcule S1-S9 (module Structure)
    - Calcule C1-C7 (module Context)
    - Compose le "V10 Signal" : (force_level, structure_type, context_state)
    - Sortie : insertion dans v10_signals (table de signaux V10)

F2. Mapping V9 → V10 (R22, 1 périmètre = mapping seulement)
    - Ne PAS supprimer les tables V9
    - AJOUTER scripts/v10_bridge.py qui mappe :
      regime_v9 → context_v10 (mapping simple)
      scenes_v9 → structure_v10 (mapping simple)
      window_v9 → liquidity_v10 (mapping simple)
    - Sortie : scripts/v10_bridge.py

F3. Tests pipeline (Hermes, 2h)
    - 100 bougies historiques
    - Vérifier que V10 produit 100 signaux (1/bougie)
    - Vérifier cohérence avec features V9 (où applicable)
    - Tests : tests/test_v10_orchestrator.py

Livrables Phase F :
  - core/v10/v10_orchestrator.py
  - scripts/v10_bridge.py (V9 → V10, sans casser V9)
  - tests/test_v10_orchestrator.py
```

**Doctrine** : R2 additif pur (0 modif core/v9/), R22 (V9 intact,
V10 en parallèle).

---

### PHASE G — DÉCISION & ALERTE (SEMAINE 7-8)

**Objectif** : transformer les V10 Signals en alertes CEO actionnables.

**Actions** :
```
G1. Logique de filtrage (Hermes, 4-6h)
    - core/v10/v10_decision.py
    - Compose force + structure + context → "setup_level"
    - Niveaux : A1 (excellent), A2 (bon), A3 (moyen), NONE (no setup)
    - Critères de Søn : "je trade quand A1 OU A2, jamais A3"
    - Sortie : setup_level par signal

G2. Alerter V10 (Hermes, 2h)
    - Réutiliser scripts/v9_signal_alerter.py (Phase 179) mais renommer
    - scripts/v10_signal_alerter.py : poll v10_signals, alerte
      Telegram si setup_level IN ('A1', 'A2')
    - Critère "vraie entrée" = (force_level >= MEDIUM AND
                                structure_type IN (BREAK, REJECT) AND
                                context_state NOT IN (NEWS, ILLIQUIDE))
    - Format message : comme V9 mais avec terminologie Søn

G3. Tests e2e (Hermes, 2h)
    - 100 setups générés, vérifier :
      * 0 alertes si force=LOW
      * 100% alertes si A1+A2
      * 0 alertes si context=NEWS
    - Tests : tests/test_v10_decision.py + tests/test_v10_alerter.py

Livrables Phase G :
  - core/v10/v10_decision.py
  - scripts/v10_signal_alerter.py
  - scripts/install_v10_signal_alerter_task.ps1 (AtStartup daemon)
  - tests/test_v10_decision.py
  - tests/test_v10_alerter.py
```

**Doctrine** : R18 (templates statiques, pas de LLM), R6 fail-open
(sans token Telegram → log console, pas de crash).

---

### PHASE H — TRACK RECORD SØN (SEMAINE 8-10)

**Objectif** : Søn trade manuellement sur 1 mois, on mesure le track record RÉEL.

**Actions** :
```
H1. Table track_record_son (Hermes, 1h)
    - data/v10_track_record.db (séparé de v9_forces.db)
    - Colonnes : trade_id, signal_v10_id, direction, entry_time,
      entry_price, exit_time, exit_price, pips, result, notes
    - Saisi par Søn après chaque trade (UI minimaliste ou CLI)

H2. UI de saisie (Hermes, 4-6h, R2 additif)
    - scripts/v10_track_record_ui.py (Streamlit minimal)
    - 3 champs : "J'ai pris le signal V10 OUI/NON"
                  "Résultat WIN/LOSS/BREAKEVEN"
                  "Notes (ce que j'ai vu que V10 n'a pas vu)"
    - Streamlit = stdlib + dashboard léger

H3. CLI de saisie (alternative, plus simple)
    - scripts/v10_track_record_cli.py
    - Question/réponse en terminal
    - 30 secondes par trade

H4. Comparaison V10 predictions vs Søn reality
    - Metrics : WR alertes suivies vs alertes skipped
    - Si Søn skip systématiquement les alertes A3 → V10 doit
      ne plus générer A3 (feedback loop)
    - Tests : tests/test_v10_track_record.py

Livrables Phase H :
  - data/v10_track_record.db
  - scripts/v10_track_record_ui.py (Streamlit)
  - scripts/v10_track_record_cli.py
  - tests/test_v10_track_record.py
```

**Doctrine** : R0 (zéro kill, zéro modif V9), R7 (tests chaque input UI).

---

### PHASE I — CALIBRATION (SEMAINE 10-11)

**Objectif** : ajuster les seuils V10 selon le track record Søn.

**Actions** :
```
I1. Analyse WR par feature (Hermes, 4h)
    - Group trades par : force_level, structure_type, context_state
    - Identifier les features qui prédisent le WR
    - Sortie : TABLEAU_CALIBRATION_V10.md

I2. Ajustement seuils (Hermes + CEO, 2h)
    - Si structure=BREAK a WR 80% → A1=CONTEXT_PASS+BREAK
    - Si structure=REJECT a WR 30% → A3=REJECT (downgrade)
    - Seuils documentés, versionnés (R14 git = source de vérité)

I3. Re-test (Hermes, 2h)
    - Rejouer le track record avec les nouveaux seuils
    - Vérifier que WR monte (ou au moins ne descend pas)
    - Tests : tests/test_v10_calibration.py

Livrables Phase I :
  - docs/V10/TABLEAU_CALIBRATION_V10.md
  - core/v10/v10_calibration.py
  - tests/test_v10_calibration.py
```

**Doctrine** : R2 (ajustement de seuils = R2 additif), R7 (re-test).

---

### PHASE J — ALLER PLUS LOIN (SEMAINE 11-12)

**Objectif** : V10 devient un système mature, prêt pour itération longue.

**Actions** :
```
J1. Documentation utilisateur (CEO + Hermes, 4h)
    - docs/V10/USER_GUIDE.md : "comment je lis avec V10"
    - docs/V10/FEATURES_CATALOG.md : 30 features expliquées
    - docs/V10/GLOSSAIRE.md : terminologie Søn (vs ICT vs V9)

J2. KPIs hebdo (Hermes, 2h)
    - dashboard : WR Søn / WR alertes V10 / taux d'utilisation
    - si V10 alerte 100 fois et Søn en suit 10 → le ratio est
      plus important que le WR brut
    - scripts/v10_kpi_weekly.py

J3. Roadmap V11 (CEO, 1h)
    - Phase 183+ : ajouter features selon demande Søn
    - Phase 184+ : multi-paires (si Søn trade 6 paires)
    - Phase 185+ : multi-TF (si Søn passe M15/H1)

Livrables Phase J :
  - docs/V10/USER_GUIDE.md
  - docs/V10/FEATURES_CATALOG.md
  - docs/V10/GLOSSAIRE.md
  - scripts/v10_kpi_weekly.py
  - docs/V10/ROADMAP_V11.md
```

**Doctrine** : R8 (doc mise à jour à chaque livraison), R26 (1 entrée
DECISIONS_LOG par phase), R28 (push CEO-mandaté).

---

### PHASE K — CLÔTURE V10 (SEMAINE 12)

**Objectif** : bilan, mise en sommeil de V9, plan V11.

**Actions** :
```
K1. Bilan V10 (CEO + Hermes, 2h)
    - Track record 1 mois Søn
    - KPIs hebdo respectés ?
    - Si WR Søn > 50% avec V10 → SUCCESS
    - Si WR Søn < 50% → diagnostic Phase 183

K2. V9 → archive (Hermes, 2h)
    - Marquer V9 comme "legacy" dans AGENTS.md
    - Garder tests V9 (régression) mais plus en CI critique
    - Garder alerter V9 (Phase 179) au cas où Søn veut comparer
    - V10 devient le système par défaut

K3. Annonce interne (CEO, 30 min)
    - Note aux stakeholders : "V9 = infrastructure, V10 = stratégie"
    - "V10 est aligné sur la lecture Søn, validé sur 1 mois"
    - "Edge fictif de V9 (90.33%) remplacé par track record Søn réel"

Livrables Phase K :
  - docs/V10/BILAN_V10.md
  - AGENTS.md : section V10 prioritaire, V9 = legacy
  - DECISIONS_LOG entry Phase K
```

---

## 📊 MÉTRIQUES DE SUCCÈS V10

### Objectif réaliste (pas le 90.33% fictif)
```
Mois 1 : WR Søn 45-55% (baseline honnête, pas de promesse)
Mois 2 : WR Søn 50-60% (calibration des seuils)
Mois 3 : WR Søn 55-65% (edge aligné sur lecture Søn)
Mois 6 : WR Søn 55-65% stable (edge validé)
```

### KPIs de qualité du système (pas de l'edge)
```
- Taux de couverture : % des bougies qui reçoivent un V10 Signal
- Taux d'alertes : % des signaux qui deviennent alertes Telegram
- Taux d'utilisation Søn : % des alertes que Søn suit
- Latence : capture → signal → alerte < 5s
- Uptime : capture_server > 99% (5min/h max d'indisponibilité)
- Tests : 100% verts (jamais de régression silencieuse)
```

### Anti-patterns à éviter
```
❌ Cacher des pertes sous des seuils permissifs
❌ Calibrer sur backtest sans validation Søn
❌ Promettre un edge avant 1 mois de track record Søn
❌ Mélanger V9 et V10 (reste 2 systèmes séparés)
❌ "Optimiser" en boucle (R2 additif = 1 changement à la fois)
```

---

## 🔧 INFRASTRUCTURE RÉUTILISÉE (V9 → V10)

| Élément V9 | Réutilisé V10 | Modifié | Notes |
|---|---|---|---|
| `core/v9/capture_server.py` | ✅ | ❌ | Source de données brutes |
| `core/v9/scenes.py` etc. (9 modules) | ❌ | ❌ | Jetés (calibrés sur features V9) |
| `data/v9_forces.db` | ✅ lecture | ❌ | Source des forces brutes |
| `data/v9_forces.db` tables `paper_trades` | ❌ | ❌ | Jetées (chiffres faux Phase 180) |
| `scripts/v9_capture_watchdog.py` | ✅ | ❌ | Daemon capture inchangé |
| `scripts/v9_signal_alerter.py` (Phase 179) | refactor en V10 | oui | Terminologie alignée Søn |
| `tests/test_*.py` V9 | partiel | partiel | Régression V9 conservée |
| `docs/SOUL.md`, `AGENTS.md` | refactor | oui | Section V10 ajoutée |
| `~/.hermes/skills/powerflow-v9-*` | ❌ | ❌ | Archivés, remplacés par V10 skills |
| 134+ tests verts V9 | ✅ conservés | ❌ | Garde-fou anti-régression |
| Doctrine R0-R30 | ✅ conservée | ❌ | Inchangé |
| MCP tools (12) | partiel | partiel | V10 tools ajoutés |

---

## 📅 TIMELINE 90 JOURS (visualisation)

```
SEMAINE 1-2  ████ Phase A — Capture TA lecture
SEMAINE 2-3  ████ Phase B — Schéma DB V10
SEMAINE 3-4  ████ Phase C — Module Force
SEMAINE 4-5  ████ Phase D — Module Structure
SEMAINE 5-6  ████ Phase E — Module Contexte
SEMAINE 6-7  ████ Phase F — Pipeline V10
SEMAINE 7-8  ████ Phase G — Décision & Alerte
SEMAINE 8-10 ████ Phase H — Track Record Søn
SEMAINE 10-11 ███ Phase I — Calibration
SEMAINE 11-12 ███ Phase J — Documentation + Roadmap
SEMAINE 12    ██ Phase K — Clôture V10
```

**Effort total** : 90 jours, ~200h dev Hermes, ~20h CEO Søn

---

## 🚨 KILL CRITERIA V10 (abandonner si)

```
🛑 V10 est un échec si (après Phase H, 1 mois de track record) :
   - WR Søn < 45% (alignement nul, V10 n'aide pas)
   - Søn skip > 80% des alertes V10 (bruit > signal)
   - Søn prend des trades HORS alertes V10 (V10 ne capture pas Søn)
   - Latence V10 > 10s (alerte trop tardive)
   - Plus de 5 faux positifs critiques (V10 dit UP, marché DOWN brutal)

🛑 Abandonner aussi si :
   - Søn n'a pas le temps de trader manuellement 1 mois
   - Søn ne peut pas formaliser sa lecture (Phase A échoue)
   - Le marché est en mode "crash/cyto" qui rend toute lecture caduque
```

---

## 🎯 PROCHAINE ÉTAPE IMMÉDIATE (24-48h)

### CEO doit fournir (Phase A prerequisite)
```
1. 1-2h d'enregistrement audio/vidéo : Søn explique sa lecture
   sur 5-10 de ses trades manuels récents
2. Capture d'écran annotée : Søn dessine ce qu'il voit
3. Glossaire personnel : termes Søn (ex: "cassure" vs "BOS")
4. Validation : Søn accepte l'idée que V10 reproduit SA lecture
   (pas une lecture "ICT" ou "Wyckoff" ou autre)
```

### Hermes (moi) en parallèle
```
1. Audit schéma V9 (1h, sans rien casser)
2. Création squelette docs/V10/ (10 min, fichiers vides)
3. Tableau préliminaire features V10 (4h, à valider par Søn)
4. Commit initial V10 (1 fichier, R2 additif pur)
```

---

## 📎 ANNEXES

### A — Inventaire fichiers V9 à conserver
```
core/v9/capture_server.py
core/v9/db_schema.py
core/v9/config.py
core/v9/kill_switches.py
scripts/v9_capture_watchdog.py
scripts/v9_capture_watchdog.py (Phase 177 v1+v2 patché)
scripts/audit_integrity_check.py (Phase 180, pour diagnostiquer V9)
tests/test_v9_capture_watchdog_lock.py
tests/test_v9_capture_watchdog_anti_doublon.py
tests/test_v9_venv_yaml_available.py
tests/test_audit_integrity_v9.py
config/telegram.json
config/v9_kill_switches.env
```

### B — Inventaire fichiers V9 à archiver (gelés)
```
core/v9/scenes.py → archive/
core/v9/behavior_analyzer.py → archive/
core/v9/window_gate.py → archive/
core/v9/exploitability_evaluator.py → archive/
core/v9/regime_detector.py → archive/
core/v9/zone_detector.py → archive/
core/v9/principle_engine.py → archive/
core/v9/signal_generator.py → archive/
core/v9/decision_logger.py → archive/
core/v9/paper_trade_engine.py → archive/ (BUG DOUBLONS)
data/v9_forces.db tables paper_trades, paper_trades_backup → archive/
```

### C — Nouveaux fichiers V10 (à créer)
```
docs/V10/TRANSCRIPTION_LECTURE_SON.md
docs/V10/TABLEAU_FEATURES_V10.md
docs/V10/FORCE_VALIDATION_JUILLET2026.md
docs/V10/STRUCTURE_VALIDATION_SON.md
docs/V10/CONTEXT_VALIDATION_SON.md
docs/V10/USER_GUIDE.md
docs/V10/FEATURES_CATALOG.md
docs/V10/GLOSSAIRE.md
docs/V10/BILAN_V10.md
docs/V10/ROADMAP_V11.md
data/v10_features.db (nouveau)
data/v10_track_record.db (nouveau)
core/v10/v10_force.py
core/v10/v10_structure.py
core/v10/v10_context.py
core/v10/v10_orchestrator.py
core/v10/v10_decision.py
core/v10/v10_calibration.py
scripts/v10_init_db.py
scripts/v10_migrate_from_v9.py
scripts/v10_bridge.py
scripts/v10_signal_alerter.py
scripts/install_v10_signal_alerter_task.ps1
scripts/v10_track_record_ui.py
scripts/v10_track_record_cli.py
scripts/v10_kpi_weekly.py
tests/test_v10_force.py
tests/test_v10_structure.py
tests/test_v10_context.py
tests/test_v10_db_schema.py
tests/test_v10_orchestrator.py
tests/test_v10_decision.py
tests/test_v10_alerter.py
tests/test_v10_track_record.py
tests/test_v10_calibration.py
```

### D — Liens utiles
- AUDIT_INTEGRITY_2026_08.md (Phase 180, diagnostic complet)
- DECISIONS_LOG.md (Phase 175-181)
- AGENTS.md (chiffres corrigés Phase 180)
- Plan "Levier Quantique" (Phase pré-180, archivé)

---

## 🔖 SIGNATURE

**Auteur** : Hermes (CEO Søn mandate)
**Date** : 2026-08-04
**Statut** : PLAN DIRECTEUR — à exécuter après validation CEO
**Doctrine respectée** : R0 (zéro kill), R2 (additif pur), R6 (fail-open),
R7 (tests verts), R8 (doc), R14 (git vérité), R18 (pas de LLM),
R22 (1 périmètre), R26 (DECISIONS_LOG), R28 (multi-IA).

**Prochaine action** : CEO Søn fournit la Phase A prerequisite
(1-2h audio + captures annotées). Sans ça, V10 ne peut pas démarrer.
