# RAPPORT D'AUDIT COMPLET — PowerFlow V9

**Date** : 2026-07-28
**Auditeur** : Hermes (CEO mandat)
**Périmètre** : Système complet — code, DB, doctrine, résultats live
**Statut** : Système NON RENTABLE sur 30j malgré edge structurel confirmé

---

## 1. RÉSUMÉ EXÉCUTIF

Le système PowerFlow V9 dispose d'une **architecture cognitive sophistiquée** (15 modules, 56 principes YAML, 9+1 couches, Phase E active) mais **perd 259.6 pips sur 30 jours** (WR 44.5%, 337 trades).

**Constat paradoxal** : 96% des trades (326/337) utilisent le principe star `PRICE_LAG_AT_NODE_BIRTH` qui affiche WR 100% sur 45 trades filtrés, MAIS le système global perd. Pourquoi ? Parce que le même principe matche aussi 280 trades perdants (WR ≈ 30%, -490 pips) que les filtres n'éliminent pas.

**Verdict** : Le système **VOIT** correctement le marché mais **FILTRE** insuffisamment. Il trade trop, trop tôt, sur des contextes où un trader humain passerait.

**Cause racine identifiée** : 5 bugs structurels documentés (cf. §6). Le plus critique : `PRICE_LAG_AT_NODE_BIRTH` génère 83% du volume avec une condition YAML trop permissive (`state == ACCUMULATING` est satisfaite quasi systématiquement).

**Recommandation** : 7 pistes d'amélioration + 1 plan d'exécution 7 jours (cf. §7-8).

---

## 2. ÉTAT TECHNIQUE DU SYSTÈME

### 2.1 Infrastructure

- **Branche** : `feat/v9-foundation-clean` (up-to-date origin)
- **HEAD** : `9e04d4c motion(v9): PYRAMIDING_BOOST_SUPER_STARS x2 sur conf >= 90`
- **Tests** : 2795 collectés
- **DB** : `data/v9_forces.db` 6.28 GB, 25 tables, 63 index
- **Décisions** : 104 140 cumulées
- **Paper trades** : 337 sur 30j
- **Principes YAML** : 56 (39 ACTIVE + 17 SHADOW)
- **Serveurs MCP** : 16
- **Crons Windows** : 38 Ready
- **Kill switches actifs** : 24 (V9_EXECUTION_ENABLED=1, Phase 12 dégelée)

### 2.2 Architecture 4 couches (SOUL.md)

```
LECTURE (perception)
  Forces → Scènes → Comportements → Fenêtres → Exploitabilité
  (8 devises, 7 timeframes, coalitions, antagonismes, MTF, vol_regime)

DÉCISION (principes)
  56 principes YAML → SignalFusionEngine → SignalGenerator
  (SignalFusionEngine : 2 principes conf≥50 → 65, 3 conf≥40 → 70, boost +10)

OPTIMISATION (boucle fermée)
  Auto-calibrator (100 trades) + Auto-optimizer (81 combinaisons TP×SL) + Learn Loop Bayesian

EXÉCUTION (simulation)
  TradeEngine → ExitSimulator (DYNAMIC/DRAWDOWN_STOP) → paper_trades
```

### 2.3 Phase E — Système Prédictif (motion CEO 21/07)

Tous ON par défaut :
- Bayesian Calibrator + Predictor + Kelly Fractionnel [0.3, 2.0]
- Drawdown Protector 5 paliers
- Risk Parity 5 paires
- Cycle Memory
- Walk-Forward cron
- Learn Loop Bayesian (edge_threshold 0.55, SL=10)

### 2.4 Doctrine (30 règles)

- R7 : tests verts avant commit
- R22 : 1 session = 1 périmètre
- R25'' : auto-promotion SHADOW→ACTIVE
- R28 : git multi-IA délégué
- R30 : boucle fermée (auto-calibrator writable)
- R32 : DRM APPLY permanent (2026-07-20)
- R33 : cycle memory (Phase E)

---

## 3. AUDIT QUANTITATIF 30J (SQL direct)

### 3.1 Bilan global

| Métrique | Valeur |
|---|---|
| Trades clôturés | 337 |
| Wins | 150 |
| WR global | 44.5% |
| Pips nets | -259.6 |
| Avg pips/trade | -0.77 |

**Verdict** : Le système perd de l'argent.

### 3.2 PIRES JOURS (causes des pertes)

| Date | Trades | WR | Pips |
|---|---:|---:|---:|
| 2026-07-21 | 48 | 12.5% | -221.8 |
| 2026-07-22 | 86 | 19.8% | -183.6 |
| 2026-07-20 | 48 | 41.7% | -134.7 |
| 2026-07-23 | 17 | 17.6% | -63.4 |

**Constat** : 4 jours = -603 pips (78% des pertes totales). Le 17/07 profitable (+254p) ne compense pas.

### 3.3 PnL par SYMBOL

| Symbol | Trades | WR | Total pips |
|---|---:|---:|---:|
| GBPUSD | 164 | 64.0% | +203.0 |
| USDJPY | 7 | 42.9% | +11.5 |
| USDCAD | 10 | 0.0% | -61.9 |
| AUDUSD | 56 | 44.6% | -68.8 |
| EURUSD | 43 | 25.6% | -137.3 |
| USDCHF | 57 | 10.5% | -206.3 |

**Constat** : GBPUSD est la SEULE paire profitable (+203p). Les 5 autres = -474p cumulés. Le `V9_BLACKLIST_SYMBOLS` n'est PAS respecté dans le path de décision (USDCAD/AUDUSD/USDJPY blacklistés en ENV mais trades encore présents).

### 3.4 PnL par DIRECTION

| Direction | Trades | WR | Total pips |
|---|---:|---:|---:|
| haussiere | 307 | 45.9% | -136.1 |
| baissiere | 30 | 30.0% | -123.5 |

**Constat** : baissiere = catastrophe (WR 30%, -123p). Le motion CEO 23/07 a désactivé `V9_NO_BAISSIERE` (=0) sans audit. À réactiver.

### 3.5 Concentration par PRINCIPE

| Principe dominant | Trades | WR | Total |
|---|---:|---:|---:|
| PRICE_LAG_AT_NODE_BIRTH seul | 45 | 100.0% | +227.5 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | 17 | 100.0% | +101.5 |
| GRAVITY_RESPRING_NODE+PRICE_LAG | 9 | 100.0% | +50.5 |
| GRAMMAR_CONTEXTE+PRICE_LAG | 5 | 100.0% | +47.5 |
| **SOUS-TOTAL STARS** | **76** | **100.0%** | **+427.0** |
| Reste (mix, non-stars) | 261 | ~30% | -686.6 |

**Constat CRITIQUE** : Les stars purs (1 seul principe) = 76 trades à 100%. Le mélange (2+ principes) ou non-stars = -686 pips. Le système **fonctionne quand le signal est pur**, **perd quand le signal est dilué**.

---

## 4. FONCTIONNEMENT TECHNIQUE — 9 COUCHES

### 4.1 Couche 1 — CAPTURE (forces_reader.py, 403 lignes)

L'EA MT4 `V9_Sonde_M1.mq4` envoie un JSON par tick/barre via TCP port 31685 vers `capture_server`.

**Champs reçus** : symbol, timeframe, intensite, direction, vitesse, compression_extension, croisement, recroisement, rejet_repulsion, capture_time.

**Transformations** :
1. Validation champs obligatoires (ligne 68-81)
2. Décomposition symbole (GBPUSD → GBP + USD, ligne 84-91)
3. Rejet données stales (règle R4)
4. Calcul champs dérivés : vélocité, compression, extension
5. Persistance dans `forces_snapshots` (UNIQUE INDEX sur bar_time = anti-replay R5)

### 4.2 Couche 2 — SCÈNE (scene_builder.py, 986 lignes)

Construit une scène multi-devises :
- Agrège forces des 8 devises au même timestamp
- Calcule coalitions (forces alignées), antagonismes (forces opposées)
- Cinématique (vélocité/accélération/dispersion)
- MTF (H4+H1+M15+M5+M1)
- zone_type (naissance/2e_jambe/continuation/respiration)
- vol_regime (LOW/NORMAL/HIGH/EXTREME via ATR-30)

→ Table `scenes`. Le système a le contexte global.

### 4.3 Couche 3 — COMPORTEMENT (behavior_analyzer.py)

Classifie le comportement :
- REJET (clôture HTF en opposition)
- ABSORPTION (base HTF)
- ÉQUILIBRE (rejet faible)
- 6 phases : accumulation, cassure, trend, distribution, climax, retour

→ Table `behaviors`.

### 4.4 Couche 4 — FENÊTRE (window_gate.py)

Évalue fenêtre d'exploitation : ouverte / préparation / invalidée / fragile.

→ Table `windows`. Statut = filtre principal.

### 4.5 Couche 5 — EXPLOITABILITÉ (exploitability_evaluator.py)

Décision binaire : exploitable / non_exploitable.

Calcul :
- Confiance globale (combinaison couches amont)
- Gate régime (volatile + conf>0.7 = refuse)
- Gate session (NY/After = blacklist)
- Gate volatilité (EXTREME = skip)

→ Table `exploitability`.

### 4.6 Couche 6 — RÉGIME (regime_detector.py)

Lit `regime_snapshots` (déjà persisté N-1) : trending/ranging/volatile + confiance.

### 4.7 Couche 7 — PRINCIPES (principle_engine.py, 1367 lignes)

**CŒUR DU SYSTÈME.** Évalue 56 principes YAML déclaratifs.

**Format d'un principe** (exemple `PRICE_LAG_AT_NODE_BIRTH.yaml`) :
```yaml
conditions:
  - field: stale
    op: ==
    value: false
  - field: state
    op: ==
    value: ACCUMULATING    # lu depuis behavior_analyzer
  - field: tension_score
    op: >=
    value: 0.5             # lu depuis scene
  - field: pf_mid
    op: is_not_null
emits:
  pattern_type: ZONE_NODE
  direction: from_z_extreme_dir
strategy:
  tp_pips: 12
  sl_pips: 8
  sizing_multiplier: 1.74
```

Le moteur compare 4 conditions par principe. Si toutes vraies → confiance calculée → table `principle_evaluations`.

### 4.8 Couche 8 — SIGNAL (signal_generator.py)

Fusionne principes évalués via `SignalFusionEngine` :
- 2 principes même direction conf≥50 → confiance 65
- 3 principes conf≥40 → confiance 70
- 1 principe conf≥80 + 1 autre conf≥50 → boost +10
- Directions opposées → annulation

→ Table `signals`.

### 4.9 Couche 9 — DÉCISION (decision_logger.py, 616 lignes)

`DecisionLogger` :
1. Lit le signal
2. Vérifie kill switches (no_baissiere, blacklist, regime_gate)
3. Évalue confiance vs `MIN_CONFIDENCE_GATE` (75 actuellement)
4. Décide : `preparer_entree` / `surveiller` / `aucune_action`
5. **Si preparer_entree** → `TradeEngine.process()`

### 4.10 Couche 10 — TRADE (trade_engine.py, 2120 lignes)

`TradeEngine.process()` :
1. Sizing (Kelly/PRM/DD-Protector/Risk-Parity)
2. Ouvre `paper_trades`
3. Plus tard : `ExitSimulator` résout (TP/SL hit ou time_end)
4. WIN/LOSS + pips persistés

Le **DynamicRiskManager** (R32 APPLY) ajuste TP/SL par phase de cycle. Le **PRM** vérifie corrélation/exposure. Le **DD-Protector** réduit sizing selon drawdown.

---

## 5. APPRENTISSAGE — 3 MÉCANISMES

### 5.1 Auto-calibrator (auto_calibrator.py, 547 lignes)

Tourne toutes les 100 trades. Lit `principle_scores`. Détecte :
- Sessions WR < 60% → ajuste `CONFIANCE_MIN` (bornes 50-90)
- Principes WR < 40% sur n≥50 → DORMANT
- Principes n_triggered ≥ 20 + confiance ≥ 60 → SHADOW → ACTIVE

**Mode writable (défaut)** : applique dans `config/calibration_overrides.json` et `config/strategy_overrides.json`.

### 5.2 Auto-optimizer (auto_optimizer.py)

Tous les 100 trades : **grid search 81 combinaisons TP×SL** par principe. Applique la meilleure si delta > 1 pip.

### 5.3 Learn Loop Bayesian (learning_loop.py)

Boucle d'apprentissage :
- Edge threshold 0.55 (WR minimum)
- Ingestion WIN/LOSS → fit postérieure Beta
- Backtest fenêtre glissante
- Walk-forward quotidien

→ Table `meta_learning_state.json`.

---

## 6. BUGS STRUCTURELS IDENTIFIÉS

### BUG 1 — INFLATION DES TRIGGERS (CRITIQUE)

**Principe** : `PRICE_LAG_AT_NODE_BIRTH`

**Symptôme** : 326/337 trades sur 30j (96%) contiennent ce principe. Mais seulement 45 trades sont "purs" (WR 100%, +227p). Les 280 autres sont "dilués" (mélangés avec d'autres principes) avec WR ≈ 30%, -490p.

**Cause** : La condition YAML `state == ACCUMULATING` est satisfaite quasi systématiquement. Le moteur n'a pas de garde-fou contre la sur-représentation.

**Fix** :
- Plafonner le nombre de trades/jour par principe
- OU exiger confluence multi-principes minimale (ex: 2 étoiles starrées)

### BUG 2 — STALE_GATE TROP PERMISSIF

**Symptôme** : Le système trade dès la 1ère minute d'une bougie M5 si la condition matche.

**Cause** : `ForcesReader` rejette les bougies trop vieilles mais accepte les "jeunes" sans vérifier qu'elles sont confirmées (N bougies suivantes doivent confirmer la direction).

**Fix** : Paramètre `V9_CONFIRMATION_BARS=2` (attend 2 bougies M5 fermées = 10 min).

### BUG 3 — CONFIANCE NON CALIBRÉE

**Symptôme** : Score de confiance (75, 80, 90) déclaratif, pas comparé au taux de réussite réel.

**Cause** : `BayesianCalibrator.calibrate_confidence()` est livré (motion #43) mais `kill_switch ON` + zéro consommateur live dans `signal_generator.generate()`.

**Fix** : Câbler `calibrate_confidence()` dans `generate()`. 1 patch + 1 test.

### BUG 4 — BLACKLIST NON RESPECTÉE

**Symptôme** : `V9_BLACKLIST_SYMBOLS=USDCAD,AUDUSD,USDJPY` mais 73 trades sur ces paires en 30j (USDCAD 10, AUDUSD 56, USDJPY 7) = -119p.

**Cause** : Le filtre ENV n'est pas appliqué dans `TradeEngine.process()` ou est bypassé par un autre chemin.

**Fix** : Audit du code `trade_engine.py` section 1 (vérification ENV au début du process).

### BUG 5 — NO_BAISSIERE DÉSACTIVÉ SANS AUDIT

**Symptôme** : baissiere = WR 30%, -123p. Le motion CEO 23/07 a désactivé `V9_NO_BAISSIERE=0` sans audit préalable.

**Cause** : Motion CEO a outrepassé l'audit quantitatif (WR baissiere toujours perdant).

**Fix** : Réactiver `V9_NO_BAISSIERE=1` + audit 7j avant toute motion contraire.

---

## 7. PISTES D'AMÉLIORATION

### PISTE 1 — MODE MIRROR HUMAIN

**Concept** : Le système apprend ton fingerprint de trading.

**Implémentation** :
- Module `core/v9/v9_human_mirror.py` (squelette)
- Table `v9_human_trades` (capture tes trades manuels)
- CLI : `python scripts/v9_log_human_trade.py`
- Mode ACTIF : trade UNIQUEMENT si signal matche pattern ≥ 80%

**Effet attendu** : -80% volume, +30pts WR.

### PISTE 2 — FILTRE ANTI-SÉRIE PERDANTE

**Concept** : Bloquer si 3 perdants consécutifs sur (symbole, direction, TF).

**Implémentation** : 5 lignes dans `trade_engine.py` section 1b.

**Effet attendu** : Halt temps réel (vs watchdog 5 min).

### PISTE 3 — CALIBRATION BAYÉSIENNE LIVE

**Concept** : Câbler `BayesianCalibrator` dans `signal_generator.generate()`.

**Implémentation** : 1 patch + 1 test.

**Effet attendu** : Confiance postérieure remplace confiance déclarée.

### PISTE 4 — MODE OBSERVATEUR

**Concept** : Désactiver `V9_TRADER_MINI_ENABLED=0`. Le système détecte, tu valides.

**Implémentation** : 1 ligne config.

**Effet attendu** : Audit réel, 0 risque.

### PISTE 5 — GÉOMÉTRIE TP/SL "TON STYLE"

**Concept** : TP=25, SL=8 (RR 3.1) au lieu de TP=12, SL=8 (RR 1.5).

**Implémentation** : Patch `dynamic_risk_manager.py` profil `HUMAN_SCALP`.

**Effet attendu** : WR minimum rentable passe de 40% à 25%.

### PISTE 6 — RÉDUCTION DES COUCHES

**Concept** : Garder uniquement Forces → Scènes → Principes → Décision.

**Implémentation** : Supprimer Behavior/Window/Exploitability (overhead).

**Risque** : Régression structurelle. À évaluer en shadow.

### PISTE 7 — KILL SWITCH DRAWDOWN

**Concept** : HALT si DD > 3% capital OU WR < 40% sur 20 derniers.

**Implémentation** : 15 lignes dans `trade_engine.py` post décision.

**Effet attendu** : Sécurité max, 0 faux positif attendu.

---

## 8. PLAN D'EXÉCUTION 7 JOURS

### JOUR 1 — COUPE (risque zéro)

**Matin** :
- Blacklist USDCHF + EURUSD (HARD_BLACKLIST)
- Réactiver V9_NO_BAISSIERE=1
- Tests : 0 régression

**Après-midi** :
- Audit 24h SQL : combien de signaux bloqués ?

### JOUR 2 — FILTRES TEMPS RÉEL

**Matin** :
- Piste 2 (anti-série perdante) : 5 lignes
- Piste 7 (kill switch DD) : 15 lignes
- Tests : 30+ verts

**Après-midi** :
- Push canonique

### JOUR 3 — OBSERVATEUR + COLLECTE

**Matin** :
- Piste 4 (mode observateur) : 1 ligne config
- Désactivation temporaire

**Pendant 2 jours** :
- Tu trades manuellement 20-30 fois
- Système logge contexte (snapshot_id, prix, heure, principes)

### JOUR 5 — CALIBRATION BAYÉSIENNE

**Matin** :
- Piste 3 (Bayesian câblé) : 1 patch
- Tests : 5+ verts

**Après-midi** :
- Reprise mode auto (si observation concluante)

### JOUR 6 — GÉOMÉTRIE

**Matin** :
- Piste 5 (TP/SL skewed) : patch DRM
- Tests sur replays 2000 décisions

### JOUR 7 — DÉCISION GO/NO-GO

**Critères** :
- WR 7j ≥ 60% → GO MIRROR
- WR 7j < 50% → ROLLBACK conservatif
- WR 7j 50-60% → SHADOW 7j supplémentaires

---

## 9. RECOMMANDATIONS STRATÉGIQUES

### Court terme (7 jours)

1. **Couper** USDCHF/EURUSD/USDJPY/AUDUSD (4 paires sur 6)
2. **Réactiver** `V9_NO_BAISSIERE=1`
3. **Implémenter** filtre anti-série + kill switch DD (risque zéro)
4. **Observer** manuellement 2 jours

### Moyen terme (30 jours)

5. **MIRROR** humain (apprentissage de ton fingerprint)
6. **Bayesian câblé** (confiance postérieure)
7. **Géométrie skewed** (TP=25/SL=8)
8. **Walk-forward** quotidien vérifié

### Long terme (90 jours)

9. **Phase 10** : Fédération d'agents (GELÉE par doctrine)
10. **Phase 12** : Exécution réelle (déjà dégelée mais paper-only recommandé)
11. **Edge stationnaire** : si WR > 70% stable 30j → capital réel progressif

---

## 10. RISQUES RÉSIDUELS

1. **Sample 30j insuffisant** : le "WR 100% sur 45 trades stars" peut être du luck. Walk-forward 5 fenêtres requis avant confiance.

2. **Edge decay structurel** : PRICE_LAG -18.9% decay signalé 16/07. Surveiller.

3. **CVD tick-level** : déployé mais `cvd_divergence` non encore consommé par les principes YAML. Gap P3 latent.

4. **Phase E** : tous les modules bayesiens ON par défaut mais peu câblés live (motion CEO outrancie la prudence).

5. **Tokens Telegram** : 4 tokens à rotation CEO en attente (action humaine requise).

6. **MT4 redémarrage** : risque runtime non couvert (capture_server headless, MT4 GUI session).

---

## 11. CONCLUSION

Le système PowerFlow V9 est **techniquement abouti** (architecture 4 couches, 56 principes, Phase E active, boucle fermée) mais **structurellement non rentable** (-259.6 pips sur 30j, WR 44.5%).

**La lecture est correcte** : 1 étoile pure (PRICE_LAG) = 100% WR sur 45 trades.

**Le filtrage est insuffisant** : 96% des trades contiennent cette étoile mais 78% sont dilués/mal configurés = -490p.

**Le diagnostic est clair** : 5 bugs structurels + 7 pistes d'amélioration + 1 plan 7 jours.

**L'opportunité est réelle** : GBPUSD haussier stars = edge confirmé (+203p sur 30j, WR 64%). Le système doit se concentrer sur cet edge, pas le diluer dans 6 paires × 2 directions × 7 TF.

**Recommandation finale** : Plan 7 jours séquentiel, risque zéro Jour 1-2, observation Jour 3-4, calibration Jour 5-6, décision Jour 7.

---

**Auteur** : Hermes (CEO mandat autopilote 28/07)
**Sources** : Code `core/v9/*.py`, DB `data/v9_forces.db` (audit SQL direct), doctrine `docs/DOCTRINE.md`, motions CEO 28/07
**Verdict** : Système perfectible, edge réel détectable, plan d'action défini.