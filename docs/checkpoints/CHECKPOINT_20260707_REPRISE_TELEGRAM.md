# CHECKPOINT — Reprise depuis session Telegram (2026-07-07)

## Date
2026-07-07

## Contexte
Reprise de session après échange Telegram approfondi sur l'alignement entre
`CHARTE_COGNITIVE_V9.md` (source de vérité philosophique) et `DOCTRINE.md` (règles
opérationnelles). Identification de **3 contradictions directes** entre la CHARTE et la
DOCTRINE, plus 5 tensions indirectes — **correction 2026-07-08** : la prose de ce
checkpoint annonçait initialement « 4 contradictions directes » mais le tableau ci-dessous
(D1) n'en documente que 3 (R20, R25, R27) ; aucune trace d'une 4ᵉ contradiction n'existe
ailleurs. Voir `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.1 (friction F0), qui affine ce
décompte à **8 contradictions** au total dans l'audit Phase A (les 3 ci-dessous + 5
nouvelles : F1-F5). Discussion sur la nature des YAML comme
**descripteurs de lecture** et non **prédicteurs statistiques** — décision de pousser
vers un chantier de révision doctrine.

Cet échange a été mené via Telegram (DM avec Sòn) avec le profil Hermes `powerflow`
modèle `MiniMax-M2.7` via `minimax`. Aucune modification de code pendant cet échange —
pure discussion architecturale + identification des contradictions.

## État du repo au moment de la pause

### Code
- **Branche** : `feat/v9-foundation-clean`
- **HEAD** : `fa79787` (sprint Søn Mode A + télémétrie + VPS-ready + Règle 30 + DEPRECATED BONUS_CONFLUENCE_MTF, livré 2026-07-07 21h→22h30)
- **HEAD précédent** : `539a62e` (Phase 9.7 — seuils gelés jusqu'à London open, livré 2026-07-07)
- **Avant sprint Søn** : `8a67583` (test window_gate naissance_isolee)
- **Upstream** : `origin/feat/v9-foundation-clean` à parité avec HEAD
- **Working tree** : clean

### Tests
- **663 verts** (596 → 605 → 637 → 663 au cours des sprints 2026-07-07)
- 3 xfailed (consolidate fragiles)
- 1 xpassed
- Règle 7 (zéro régression) respectée

### Pipeline live
- **Port capture** : 31685
- **Serveur capture_server** : actif (PID 42608 au moment de la dernière activité)
- **DB v9_forces.db** : 2.9 GB, 72K+ snapshots
- **EA MT4** : 7 TF connectés, timestamps qui avancent en temps réel
- **Stale M5+** : ~0.6%

### Doctrine
- **30 règles immuables** (R28 = Hermes git unique, R29 = lecture multi-TF scène-complète
  avec 4 types de zone naissance/2e_jambe/continuation/respiration + pondération
  arbiter zone-type×session, R30 = apprentissage conditionnel WIN/LOSS seuils
  progressifs 5/20/50/200)
- `DOCTRINE.md` 27 → 30 règles

### Mode A agentification bornée (Phase 9.10)
- 5 agents chauds : force_reader, scene_builder, behavior_analyst, gatekeeper, decision_maker
- 1 supervisor + 1 reviewer
- Télémétrie agents opérationnelle : `core/v9/agent_telemetry.py` + hook best-effort
  capture_server
- CLI précision : `scripts/v9_agent_precision.py`
- Préflight VPS : `scripts/v9_check_vps.py`
- **Cible VPS** : 4 cores 2.6 GHz / 12 GB RAM (à charge Søn, SDI à installer)

### Seuils config.py
| Seuil | Valeur | Statut |
|-------|--------|--------|
| `COALITION_THRESHOLD` | 5.38 | ✅ APPLIQUÉ (commit `fb5383a`) |
| `ANTAGONISM_THRESHOLD` | 31.39 | 🟡 PROVISIONAL (rééval n>10k) |
| `PLIURE_THRESHOLD` | 1.7 | 🟡 PROVISIONAL (rééval n>10k) |

### Paper-trade
- 0 trade ouvert (range M5 GBPUSD, comportement attendu)
- 7 signaux directionnels GBPUSD 2026-07-07 (confiance 80-100)
- 2 messages Telegram envoyés 10:07:49 CEST
- Conditions pour 1er paper trade : ≥ 2 principes ACTIVE + confiance ≥ 80 +
  window=exploitable + news_phase ≠ NEWS_SHOCK
- Critères objectifs WIN/LOSS ≥ 20 (règle 25) : **non remplis**

### Prochain driver macro US majeur
- **NFP vendredi 7 août 2026** (1er vendredi du mois, typique UTC 12:30)
- Entre-temps : aucune news HIGH dans 4h (calendar statique)
- Marché range post-Fête US, comportement structurellement inerte

## Décisions prises pendant l'échange Telegram

### Décision D1 — Identification des contradictions CHARTE/DOCTRINE
- **3 contradictions directes** identifiées entre CHARTE_COGNITIVE_V9.md et DOCTRINE.md
  (correction 2026-07-08 — voir note en tête de document et
  `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.1 F0 : le décompte "4" annoncé initialement en
  prose ne correspondait à aucune 4ᵉ ligne du tableau ci-dessous)
- **5 tensions indirectes** identifiées
- Tableau complet des contradictions :

| Règle | CHARTE § | Type | Sévérité |
|-------|----------|------|----------|
| **R3** | Règle 2 | Tension | 🟡 |
| **R10** | Priorité 1 | Tension | 🟡 |
| **R13** | Priorité 6 | Tension | 🟡 |
| **R20** | Interdit #4 | **Contradiction** | 🔴 |
| **R22** | Règle 4 | Tension | 🟡 |
| **R23** | Règle 4 | Tension | 🟡 |
| **R25** | Interdit #4 + Règle 3 | **Contradiction** | 🔴 |
| **R27** | Règle 3 | **Contradiction** | 🔴 |

### Décision D2 — Position philosophique de Søn sur les YAML SHADOW
- **Position** : Les YAML ne sont pas des prédictions à vérifier mais des **descripteurs
  de lecture**. Un YAML qui se déclenche ajoute de l'information descriptive, pas une
  thèse à valider statistiquement.
- **Conséquence** : Les 17 `kind: grammar` SHADOW privent la lecture d'information
  cognitive. Le filtrage rentabilité (hit_rate ≥ 60%) contredit frontalement la CHARTE
  §Interdit #4 ("Laisser une logique de rentabilité déformer la perception amont").
- **Chantier à ouvrir** : Phase 9.8 — Révision R25 (et alignement général CHARTE/DOCTRINE)

### Décision D3 — 3 options proposées pour R25
- **Option A** : Aligner R25 sur CHARTE (suppression logique rentabilité)
- **Option B** : Maintenir R25 mais justifier explicitement (exception CHARTE)
- **Option C** : Supprimer R25 (les 27 YAML = tous ACTIVE par défaut)
- **Choix** : À faire par Søn à la reprise

## Prochaines actions au retour sur PC

### 1. Lecture obligatoire avant action
- `workspace/perplexity/BOARD.md` — état sprint Søn
- `workspace/perplexity/ACTIVE_TASKS.md` — tâches en cours
- `workspace/perplexity/memory/DECISIONS_LOG.md` — historique décisions
- `docs/STATE.md` — détail vivant par phase
- `docs/CACHE_BOARD.md` — tableau reprise complet
- `docs/checkpoints/CHECKPOINT_20260707_PHASE10.md` — détail Phase 10

### 2. Décision Søn — Révision R25 (CHARTE/DOCTRINE)
Choisir entre A / B / C et documenter dans DECISIONS_LOG.md avec :
- Date
- Décision
- Motivation
- Impact/portée
- Référence

### 3. Vérification pipeline live
```bash
# Vérifier que le serveur tourne
python scripts/v9_supervisor.py --health

# Vérifier la DB
python scripts/v9_calibration.py --stats

# Vérifier les derniers signaux
python scripts/v9_ops.py signals --limit 10

# Vérifier les dernières décisions
python scripts/v9_ops.py decisions --limit 10
```

### 4. Hit_rate des 17 YAML SHADOW (si décision = B ou C)
```bash
python scripts/v9_calibration.py --principes
```
Sortie : liste 27 principes + hit_rate + confiance → base empirique pour la décision.

### 5. Chantier Phase 9.8 (si A ou C retenu)
- Créer worktree : `D:\Projet\V9_wt_doctrine_realign`
- Branche : `auto/feat/phase9.8-doctrine-realign`
- Modifications minimales :
  - `config.py` : `PRINCIPLE_ACTIVE_IDS` (si C)
  - `docs/DOCTRINE.md` : reformulation R25 (si A ou C)
  - `tests/test_principle_engine.py` : test propagation 27 YAML
- 1 commit par modification + DECISIONS_LOG + STATE.md (règle 26)

## Contraintes opérationnelles

### Limites Telegram de cette session
- Pas de terminal → pas d'exécution de commande V9
- Pas d'accès direct à la DB SQLite
- Modèle `MiniMax-M2.7` via `minimax` (différent de la session Claude Code habituelle)
- Lecture seule des fichiers texte
- Write de fichiers texte possible (création checkpoint fait)

### Mémoire de session
- La mémoire Hermes est cohérente (Søn CEO PowerFlow V9, FR GMT+1, Git=vérité)
- Limite 50 tool-calls/session atteinte → reprise PC nécessaire pour actions code

## Fichiers pivots à toujours consulter

1. `D:\Projet\V9\workspace\perplexity\BOARD.md`
2. `D:\Projet\V9\docs\STATE.md`
3. `D:\Projet\V9\docs\CACHE_BOARD.md`
4. `D:\Projet\V9\docs\DOCTRINE.md`
5. `D:\Projet\V9\docs\CHARTE_COGNITIVE_V9.md` (ou `docs/doctrine/CHARTE_COGNITIVE_V9.md`)
6. `D:\Projet\V9\workspace\perplexity\ACTIVE_TASKS.md`
7. `D:\Projet\V9\workspace\perplexity\memory\DECISIONS_LOG.md`
8. `D:\Projet\V9\docs\checkpoints\CHECKPOINT_20260707_PHASE10.md`

## Validation
- [x] Fichier checkpoint créé
- [ ] Commit de ce checkpoint (à faire au retour PC)
- [ ] Push origin (à faire au retour PC)
- [ ] `docs/STATE.md` mis à jour (à faire au retour PC)
- [ ] `docs/DOC_REGISTRY.yml` mis à jour (à faire au retour PC)

## Prochaine étape
Reprise sur PC → lecture des 8 fichiers pivots listés ci-dessus → décision Søn sur
R25 (option A / B / C) → chantier Phase 9.8 si retenu.