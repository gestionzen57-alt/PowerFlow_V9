# SESSION BRAINSTORM AGENTS — 2026-07-07 nuit CEST (CEO Søn)

## Statut
🔒 Note de session, **pas un chantier**. Documentée ici pour reprise future.
Aucun engagement de livraison tant que Søn n'a pas arbitré.

## Identification
- **Date** : 2026-07-07 ≈ 23h45 UTC (≈ 01h45 CEST 2026-07-08)
- **HEAD** : `5b3e6cf` (parité origine, working tree clean)
- **Mode** : A — VEILLE
- **Opérateur** : Hermes (Søn CEO via Telegram)
- **Trigger** : « Go commit et push tout... lis tous les documents du projet car il y a des
  documents parlant de skill maker en agent... propose un plan digne architecture agentique »
- **Suite trigger** : « on reste en mode brainstorming α (sniper périphérique) les agents vont
  apporter quoi en plus values, si je fais sauter les règles qu'est-ce que cela permettrait,
  j'ai l'impression que cela limite trop le plein potentiel des choses »
- **Trigger final** : « sauvegarde ton plan pour plus tard... il faut nettoyer la DB au max
  car je dois l'exporter sur VPS »

## 1. État repository au moment du gel
- Branche : `feat/v9-foundation-clean`
- HEAD : `5b3e6cf docs(v9): sprint CEO nuit — backlog Phase 14 + log anomalie 21h00`
- 699 verts / 3 xfailed / 1 xpassed (règle 7 OK)
- Daemon : port 31685 occupé, capture_server PID 42608 actif, marche OUVERT session sydney
- DB live : v9_forces.db 3.1 GB, 76733 forces_snapshots

## 2. Reformulation CEO Søn
Brut : « implémente des agents pas comme V8, propose un plan d'archi agentique pour mettre
PowerFlow à son plein potentiel, Ollama Cloud dispo, accès modèles free ».

Reformulé : « Architecture agentique qui (a) respecte doctrine V9 comme contrainte d'or,
(b) consomme Ollama Cloud + free pour leur force (langage, revue, RAG), (c) zéro LLM dans
boucle chaude, (d) gain opérationnel mesurable dès sprint 1, (e) Phase 10 déclenchable
proprement quand canonisation atteinte, (f) 1 sprint borné par chantier, pas big-bang ».

## 3. Audit honnête — existant vs imaginé

| Søn imagine | Réalité V9 |
|------------|-----------|
| Skill maker = à créer | Existe comme intention verrouillée dans SKILLS_BACKLOG.md / AGENT_BACKLOG.md / 5 squelettes placeholders (gelés par règle 19 + Søn 14h58) |
| REGISTRY = agents LLM | REGISTRY = wrappers Python in-process (code déterministe, 0 LLM, règle 18) |
| Phase 10 = agents LLM | Phase 10 = fédération V8 (REJETÉE explicitement par Søn). Mode A = VRAIE réponse agentique |
| Ollama Cloud free = cœur | Ollama Cloud free = agents PÉRIPHÉRIQUES uniquement (HITL/RAG/doctrine-keeper/replay-confronter/daily-briefing). JAMAIS dans chaîne chaude (R18) |

## 4. Diagnostic contradiction à arbitrer
Søn veut « implémentation d'agents » alors que : R19/Phase 10/SKILLS_BACKLOG INTERDIT
fondateur ; R18 zéro LLM chaîne chaude ; Phase 12/11 gelées. 2 lectures : (a) déverrouiller
Phase 10 — GO doctrinal daté requis ; (b) exploiter potentiel SANS toucher cœur cognitif —
direction recommandée.

## 5. 3 options d'architecture agentique (brainstorm)

### OPTION α — « Sniper périphérique » (RECOMMANDÉE)
4 agents IA Ollama Cloud free branchés sur I/O existants, 100% hors boucle chaude, 0 modif core/v9/* :
- AG1 reviewer enrichi (déjà livré minimal, à muscler sémantiquement)
- AG2 doctrine-keeper (cohérence live vs DOCTRINE, signal PRÉSENT↔DOCTRINE par décision)
- AG3 replay-confronter (top-5 cas similaires cosine sur contexte_complet_json)
- AG4 daily-briefing (Telegram 07h30 Paris chaque matin, 5 lignes)
Coût ~$0 Ollama Cloud free + modèles 7B. Délai 1 sprint. Risque nul.

### OPTION β — « Bridge symbiotique »
α + 1 LLM local en COPILOTE de calibration (lecture seule sur DB, assiste Søn sur
v9_calibration.py --principes, propose seuils candidats, n'écrit rien, signale sur Telegram).

### OPTION γ — « Cœur cognitif augmenté » (DÉVERROUILLE DOCTRINE)
β + plug-in LLM en ASSISTANT lecture multi-TF sur behavior_analyst et gatekeeper. PRÉREQUIS :
DECISIONS_LOG datée levant règle 18 ou 19 (signature Søn).

## 6. Valeur ajoutée des 4 agents périphériques (α)

| Agent | Coût | Gain direct | Gain indirect |
|-------|------|-------------|---------------|
| AG1 reviewer | ~$0 | 7-22 min/jour lecture signaux | trace HITL auditable |
| AG2 doctrine-keeper | ~$0 | 20 min/commit YAML | dérive détectée avant casse |
| AG3 replay-confronter | ~$0 | biais -30% LOSS | corpus pour règle 30 |
| AG4 daily-briefing | ~$0 | 10-15 min/jour | 0 anomalie silencieuse |

Total : ~$0, 4-6h/sem économisées, mémoire opérationnelle + audit auto + veilleuse.

## 7. Si les règles sautaient — plein potentiel révélé

### Niveau 1 — R18 tombe (LLM boucle chaude sous feature flag)
A. Lecture sémantique scènes 6 dims temps réel (200ms, // déterministe, flag ON/OFF)
B. Génération features sémantiques pour YAML non-traditionnels (canal YAML-sémantique)
C. Confirmation contextuelle avant décision (LLM sanity check, decision reste déterministe prioritaire)
D. Auto-naming fenêtres (« rejet faible sous support hebdo » vs étiquette SQL nue)

### Niveau 2 — R19+Phase 10 débloc (fédération)
E. Multi-agent par devise (5 paires //) → 10× débit décision
F. Multi-agent par TF (H4 stock / H1 confirme / M15 transmet / M5 fenêtre / M1 tick)
G. Risk-manager inter-devises autonome (corrélation live, exposition cachée)
H. Mémoire vectorielle ChromaDB tous WIN/LOSS (R30 ≥ 200 devient statistiquement fondée)

### Niveau 3 — R25 tombe (seuils inventés possibles)
I. Auto-tuning seuils par reinforcement learning (au lieu de propositions only)
J. Seuils par régime × session × devise (dispersion naturelle enfin modélisée)

### Niveau 4 — R16 tombe (migration V8 avant agentification)
K. Réimportation sélective 11 YAML V8 blanchis (+15-20% patterns couverts)

### Niveau 5 — R12 tombe (replay/live non distingués)
L. Mode bootstrap continu (chaque soir = replay 24h, ajustement seuils)

### Niveau X — R6 tombe
M. Watchdog LLM superviseur qui raisonne (debug 10× plus rapide)

## 8. 11 différences structurelles V8 vs V9 (AU-DELÀ DES RÈGLES)

| Dimension | V8 | V9 |
|-----------|----|----|
| Process | Multi-process bus | Monolithique in-process |
| Mémoire | Redis + bus | SQLite WAL row_factory |
| Pipeline | 4 couches | 9 couches |
| Source vérité temp | Multi-snapshots/TF désynchro | 1 bougie=1 snapshot UNIQUE INDEX |
| Lecture doctrine | HTF-first obligatoire | Scène-complète multi-TF non-HTF-first conditionnelle (R29) |
| Principes YAML | Règles de trading | DÉTECTEURS de patterns (R11) |
| Tests | Flaky | 699 verts déterministes |
| DB | Multi-DB par sous-système | 1 v9_forces.db WAL schéma explicite |
| Exécution | Manuelle Perplexity | Auto capture_server + orchestrator (R6 no crash) |
| Migration | Implicite désordonnée | Classification A/B/C/D explicite MIGRATION_POLICY_V9.md |
| Gouvernance doc | Sparse | DOCTRINE.md + DOC_GOVERNANCE.md + DECISIONS_LOG (R26) |
| Forme principes | Seuils absolus | Seuils = repères révisables (R25) |

**Constat clé** : les 30 règles sont la COUCHE de gouvernance au-dessus de ces 11 choix.
On peut rouvrir les 11 sans danger tant qu'on ne touche pas aux 11 (catégorie A-D dans doc).

## 9. Catégorisation des 11 choix par réversibilité

### CATÉGORIE A — IRRÉVERSIBLES (on n'y touche pas)
A1 UNIQUE INDEX bar_time (R5) | A2 SQLite WAL row_factory | A3 pipeline 9 couches |
A4 SQLite unique (12GB RAM)

### CATÉGORIE B — RÉVERSIBLES SANS RISQUE (juste GO daté)
B1 Générateur YAML propositions SØN valide | B2 LLM interprétation // déterministe |
B3 Multi-paires lecture seule | B4 ChromaDB cosine tf-idf pure-SQL (0 LLM)

### CATÉGORIE C — RÉVERSIBLES AVEC PRÉCAUTION (règle + feature flag)
C1 Seuils contextualisés V9_SEUILS_CONTEXTUAL=1 | C2 LLM sanity_check V9_LLM_SEMANTIC=1 |
C3 Auto-naming fenêtres (cosmétique pur)

### CATÉGORIE D — ADN V9 (on conserve = ≠ V8)
D1 Process unique | D2 SQLite unique | D3 Pipeline 9 couches | D4 Principes=DÉTECTEURS |
D5 Tests verts | D6 1 bougie=1 snapshot | D7 Doc gouvernance | D8 Lecture scène-multi-TF |
D9 Seuils repères révisables | D10 Apprentissage WIN/LOSS | D11 Zéro LLM chaîne chaude

## 10. 4 RÉGLAGES possibles

| Réglage | ADN préservé | Ajouts activés | Diff vs V8 |
|---------|--------------|----------------|------------|
| R1 JUSTE (statu quo) | 11/11 | néant | 11/11 distinctions |
| R2 SERRÉ (recommandé) | 11/11 | B1+B2+B3+B4 | 11/11 distinctions |
| R3 OUVERT | 11/11 | B1+B2+B3+B4 + C1+C2+C3 flag | 11/11 distinctions |
| R4 FENÊTRÉ (post WIN/LOSS≥200) | 9/11 | tous + multi-paires TRADE + LLM chaîne chaude | 9/13 |

## 11. RECOMMANDATION HERMES = RÉGLAGE 2 SERRÉ

Pourquoi R2 :
(i) Søn limité par R1 sans exploiter modules — R2 résout
(ii) 4 leviers B1-B2-B3-B4 réversibles indépendamment
(iii) Prépare R30 palier ≥ 50 sans le déclencher
(iv) ChromaDB + multi-paires lecture = transforme V9 « 1 paire 1 TF dominant » → « N paires pattern recognition »
(v) B2 sémantique gratuit en ADN V9 (coprocesseur //, écrit rien)
(vi) Pas d'invention seuils (R25 reste), pas d'auto-tune (R30 reste), pas de LLM chaîne chaude (R18 reste). Ajoute des YEUX, pas des MAINS.

## 12. RÉÉCRITURE R19 PROPOSÉE (seule règle à lever)

R19 actuelle : « Les chantiers agents/routing/skills auto-générés ne démarrent pas avant canonisation live ».

R19v2 (signature Søn datée) :
« Les chantiers agents/routing/skills auto-générés ne démarrent pas avant canonisation live,
À L'EXCEPTION DE :
(a) Mémoire vectorielle ChromaDB en lecture seule (cosine + tf-idf, pas de LLM dans la chaîne, propositions only) ;
(b) Lecture multi-paires (lecture seule, propagation contexte_complet, aucun trade) ;
(c) Générateur de features sémantiques pour YAML (propositions only, validation Søn avant commit, caractéristique `auto_generated=true`) ;
(d) Interprétation sémantique des scènes 6 dimensions en // de l'analyse déterministe (n'écrit rien dans la décision, Markdown dans `data/scene_interpretations/`) ».

Chirurgical, pas爆破. Esprit R19 préservé (canonisation d'abord), 4 perméabilités ouvertes.

## 13. Plan de livraison (si Søn arbitre R2)
- 1 commit spec R19v2 : 30 min
- 4 modules inoffensifs (B1/B2/B3/B4) : 4 sprints ~25 commits
- Zéro modif core/v9/business
- Zéro régression test (règle 7)

## 14. PROJECTION COMPRESSION DB (Søn pour export VPS)

DB actuelle 3.1 GB, +0.5 GB/48h linéaire. VPS 12 GB RAM cible. Export VPS doit être allégé.

### DONNÉES 100% MORTES (jamais consommées aval)
1. **zone_diagnostics** 364 528 rows × 25 cols + 2 JSON = ~25% DB → supprimer
2. scenes.coalitions_json jamais lu → volume négligeable
3. behaviors.singularites_locales_json 133 rows × 105 B → minuscule
4. behaviors.ecarts_json 129 rows × 105 B → minuscule
5. behaviors.point_de_rupture_* flag=0 à 100% → propriété morte
6. **principle_evaluations.context_json** {} hardcodé × 1.2M rows ≈ 60 MB gaspillés
7. **principle_evaluations lignes v9_status='SHADOW'** ~800K rows × 66% jamais routées SignalGenerator

### DONNÉES 90% MORTES (valeur résiduelle)
8. **scenes.confluences_mtf_json** 94 MB — Cascades sérialisables, normalisation 3NF table séparée → -60 MB.
   Note doctrine : behavior_analyzer intègre déjà confluence MTF, double bonus ferait double-compte (config.py).
9. scenes.cinematique_json 15 MB — 80% champs inutilisés par regime_detector
10. 17 YAML SHADOW — 0 downstream, archivage 1 jour

### DONNÉES 50/50
11. exploitability.replay_cas_compares_json — REPLAY_MIN_CAS=3 sur 0 WIN → BUGB6 rend usage nul
12. zone_diagnostics.context_tags_json 4 KB × 364K = 1.4 GB potentiel si activé Phase 13

### DONNÉES VIVANTES (aval consomme)
forces_snapshots / decisions / signals / behaviors / windows / exploitability.

### SCÉNARIOS COMPRESSION
| Scénario | Compression | DB après | Effort |
|----------|-------------|----------|--------|
| A sprint immédiat SHADOW+context_json vide+zone_diagnostics | -30 à -35% | 2.0 GB | 1 sprint 2-3h |
| B +VACUUM+normalisation confluences_mtf | -45 à -55% | 1.4 GB | 2 sprints 5-6h |
| C migration DuckDB columnare | -55 à -70% | 0.9 GB | 1 sprint 3-4h |
| D FULL=DuckDB+nettoyage+normalisation | -70 à -80% | 0.6 GB | 3 sprints 10-12h |

### Recommandation export VPS
Scénario B (1.4 GB, tient 1 mois) ou D (0.6 GB, tient plus). AGENT_BACKLOG.md a déjà documenté
Phase 14a (4 commits kill switch SHADOW/JSON + VACUUM, ROI -70%) + Phase 14b DuckDB.
**Phase 14a reste gelée** en attente GO Søn à tête reposée (règle 22, sprint CEO nuit clos
00h30 CEST).

Kill switch V9_DISABLE_ZONE_DIAGNOSTICS=1 déjà livré (commit 45b4912) → ROI -25% DB si
Søn l'active côté VPS lui-même.

## 15. PROCHAINE ACTION (mode A — VEILLE par défaut)

Aucune action V9 tant que Søn n'arbitre pas :
  (a) R1 / R2 / R3 / R4 — choix du réglage
  (b) Ou GO Phase 14a (nettoyage DB pré-export VPS)
  (c) Ou autre directive

Søn a indiqué « je te donne le fil de tout à l'heure » — gelé en attendant.

## 16. Mémoire durable
- mem0 event `a56ecc4e-fef9-49f4-8d07-ba2d445f5c93` : plan stratégique agentique (R1-R4,
  11 différences V8/V9, brainstorm règles sautées, AG1-AG4, R19v2)
- mem0 event `1c5dbed1-9ed0-4ec6-8bc3-6437cf4d0e4b` : projection compression DB +
  inventaire données mortes + décision export VPS

## 17. Reprise future (à l'heure Søn)
Quand Søn revient, lecture obligatoire dans cet ordre :
1. `workspace/perplexity/AGENT_BACKLOG.md` (état backlog)
2. `workspace/perplexity/BOARD.md` (synthèse)
3. ce fichier `SESSION_BRAINSTORM_AGENTS_20260707.md` (continuité brainstorm)
4. mem0 search « agent » ou « compression DB » (fil恢复了)
5. `git log --oneline -10` (état commits)
6. `python scripts/v9_ops.py health` (état daemon)

Pas de `core/v9/*` contact tant que pas d'arbitrage Søn.
Pas d'invention de seuils (R25).
Hermes seul opérateur git (R28).

---
**Fin de session brainstorm — gelé à l'heure Søn. Aucune action sans arbitrage.**
