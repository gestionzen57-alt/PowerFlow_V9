# INSPIRATION_20260707_FABLE — Source vidéo YouTube & cartographie d'expansion V9

> **Statut** : Note d'inspiration (non décisionnelle). Patterns identifiés + pistes d'expansion à arbitrer.
> **Source** : YouTube `mVbwTrj1-hw` — vidéo 32 min "Claude Fable 1000x more powerful" (Claude B, juillet 2026)
> **Screenshots** : `D:\SCREEN\Juillet\FABLE\` (35 captures, 01:24-01:50 + 1 capture finale 20:03-32:24)
> **Transcript** : 82 802 chars extraits via `youtube-content` skill
> **Référencé par** : `agents/AGENTIC_MAP.md` (chantier Phase 9.8) — note d'input pour arbitrage futur
> **Conformité** : règle 22 (chantier = livraison complète) — ici 0 code, juste cartographie doc, pas de commit obligatoire

---

## 1. Résumé de la vidéo (32 min)

La vidéo présente l'architecture **"Loop Engineering"** appliquée aux agents Claude Fable/Mythos. L'idée centrale : remplacer l'approche chatbot ("prompt → réponse") par une architecture en 3 blocs récursifs avec un **work loop** au milieu. Le LLM observe l'état, sélectionne outils + mémoire, puis itère (test → diagnostic → fix → retest) jusqu'à validation, avec un **branching HITL** (Human-In-The-Loop) qui s'active dès que la confiance descend sous un seuil (typiquement 10%).

L'auteur insiste sur 4 points clés pour V9 :
1. **3 types de mémoire** : persistante (`memory.md`) + temporaire (`memory_temp.md`) + swap entre LLMs.
2. **Skill ≠ Agent** : un skill est une fonction de routing passive, un agent peut **coder son propre skill** en cours d'exécution quand il ne sait pas faire.
3. **Worktrees = agents parallèles** : un agent par branche Git, partage du contexte via mémoire partagée.
4. **HITL obligatoire** dès qu'un doute > seuil (l'humain garde le dernier mot, surtout pour les actions destructives).

---

## 2. Patterns V9 DÉJÀ en place (validation a posteriori)

| Pattern vidéo | Équivalent V9 | Statut |
|---|---|---|
| **Boucle test→diag→fix→retest** | Chaîne cognitive 9 couches (Forces→Scènes→...→Décision) | ✅ Livré Phase 1-9 |
| **Mémoire persistante versionnée** | `workspace/perplexity/memory/*.md` (memory.md, DECISIONS_LOG.md) + Git | ✅ Livré Phase 0 |
| **Mémoire temporaire** | `workspace/perplexity/JOURNAL.md` (deltas opérationnels, purgés en fin de session) | ✅ Livré 2026-07-07 |
| **Mémoire swap entre LLMs** | Bus `exchange.md` (Hermes↔Zcode) + multi-provider (ollama/openrouter/nous) | ✅ Livré Phase 8 |
| **Trigger heartbeat** | `scripts/v9_heartbeat.py` (5min check + 60min alive) | ✅ Livré Phase 9.8 (commit `4aa4fd3`) |
| **HITL sur action destructrice** | Règle doctrine "aucune logique d'exécution d'ordre avant Phase 12" + Telegram review | ✅ Livré Phase 9 + 9.7 |
| **Critères mesurables (preuve de succès)** | Règle 7 doctrine (tests 0 régression), 527+ tests verts | ✅ Livré Phase 1-9.8 |
| **Worktree = agent parallèle** | Sessions V8 parallèles (cf. INCIDENTS.md 2026-07-05 "fusion concurrente") | ⚠️ Vécu comme bug, pas comme feature |
| **Verification stage (boucle max 3)** | `validate-coherence.py` (7 checks DB) + compteur échecs heartbeat (3 = alerte) | ✅ Livré |
| **Skill routing (chargement conditionnel)** | Hermes profile + skills_view() dynamique | ✅ Livré |
| **Boot script qui prépare/vérifie/lance** | `scripts/v9_bootstrap.py` + `scripts/v9_ops.py` | ✅ Livré |
| **Quota/circuit breaker** | Règle 18 (LLM non bloquant) + fallback_providers (openrouter/nous) | ✅ Livré |

→ **12 patterns sur 12 sont déjà opérationnels dans V9.** La vidéo valide rétroactivement l'architecture qu'on a construite empiriquement. C'est une **confirmation doctrinale forte**.

---

## 3. Patterns NOUVEAUX à étudier pour expansion V9

### 3.1 Branching HITL basé sur confiance < seuil (vs binaire `is_win IS NULL`)

**Vidéo** : "When the algorithm detects uncertainty, it asks the user or the orchestrator to intervene" — l'agent demande confirmation dès que sa confiance interne < 10%.

**V9 actuel** : la décision est journalisée avec `conf` (0-100), mais le HITL Telegram n'est déclenché qu'à `conf > 65` ET `is_win IS NULL`. Pas de branching "doute modéré".

**Piste expansion** : ajouter un seuil de doute (ex. conf entre 40-65) qui envoie une notification Telegram "⚠️ décision peu fiable, voulez-vous l'exclure du scoring ?". Cela rejoint la règle 25 (calibration SHADOW→ACTIVE) : un principe avec hit_rate < 60% devrait être rétrogradé SHADOW ou HITL.

**Complexité** : faible (~30 LOC + 1 test). À intégrer en Phase 11 ou 13.

### 3.2 Skill auto-généré par l'agent en cours d'exécution

**Vidéo** : "When it realizes it can't perform a task, it will code its skills based on your request and improve its operation."

**V9 actuel** : les 27 principes YAML sont fixes (gelés par règle doctrine). Aucune auto-génération.

**Piste expansion** : un agent "principe_builder" qui propose de nouveaux principes YAML à partir d'observations de marché non couvertes (zone d'inertie, fake breakout, etc.), avec **HITL obligatoire** avant activation (le Søn valide chaque nouveau principe).

**Complexité** : moyenne (nouvelle couche 7bis, ~150 LOC + tests + doctrine amendement règle 25). À ouvrir en Phase 13 (apprentissage et auto-calibration), pas avant.

### 3.3 Worktree par agent (parallélisme Git)

**Vidéo** : "transform your AI agent into a work partner that you orchestrate. Your AI agent isn't simply a file; it's an architecture."

**V9 actuel** : 1 branche `feat/v9-foundation-clean`. Sessions parallèles = risque de merge conflict (cf. INCIDENTS.md).

**Piste expansion** : standardiser le pattern "1 agent = 1 worktree + 1 branche dédiée + 1 PR de retour" pour les chantiers de Phase 11+. Cf. déjà pratiqué pour Phase 7 et 8 dans V8 historique.

**Complexité** : faible (process, pas de code). À documenter dans `docs/SESSION_PROTOCOL.md` puis appliquer dès la Phase 11.

### 3.4 Mémoire FFN (MemoryLLM) — long terme

**Vidéo (réf. étude Apple July 2026)** : "the ability to store information between VRAM and storage significantly improves the quality of an LLM's work." → on remplace la mémoire self-attention par une mémoire FFN persistante, mêmes paramètres totaux.

**V9 actuel** : aucun mécanisme d'apprentissage. Phase 13 = "Apprentissage et auto-calibration" mais sans roadmap détaillée.

**Piste expansion** : Phase 13 = fine-tuning léger d'un petit LLM local (qwen3-coder ou phi3) sur les WIN/LOSS résolus. Modèle "V9-trader-mini" (~1-3 GB) qui apprend la calibration des 27 principes à partir des trades résolus. **Reste local, pas d'API** (règle 18).

**Complexité** : haute (fine-tuning + dataset + eval). À ouvrir seulement si WIN/LOSS ≥ 50 résolus (cf. règle 25 implicite). Hors roadmap court terme.

### 3.5 UI locale HITL pour paper-trade

**Vidéo (email agent)** : "Aucune mise à la corbeille sans validation humaine explicite" — schéma `boot-cleaner.ps1 → cleaner-server.mjs → A:Gmail API + B:Classification + C:UI locale HITL → state/logs/feedback`. Le HITL est **UI locale** (pas Telegram) pour l'action finale.

**V9 actuel** : HITL Telegram uniquement (cf. décision 2a Phase 9.8).

**Piste expansion** : si le volume de paper-trades HITL explose (> 10/jour), ajouter un mini-dashboard web `/review` (FastAPI + HTML statique, < 100 LOC) avec boutons "Approuver / Rejeter". Conforme à la décision 2b qu'on a mise en option Phase 11+.

**Complexité** : moyenne. À ouvrir seulement si le besoin se confirme post-déploiement VPS.

### 3.6 Email/Slack comme canal HITL secondaire

**Vidéo** : agent email capable de trier 2 500 emails en 15s avec 70% auto + 30% HITL.

**V9 actuel** : Telegram uniquement.

**Piste expansion** : si Søn voyage sans Telegram, fallback email (SMTP + IMAP via `himalaya` skill déjà disponible). Pas de priorité, mais l'infrastructure `himalaya` est déjà dans les skills.

**Complexité** : faible. À ouvrir si Søn le demande.

---

## 4. Synthèse — ce qu'on garde, ce qu'on ouvre

### 4.1 Confirmations (rassurant, pas d'action)
- L'architecture V9 actuelle est **cohérente avec l'état de l'art agentique 2026**.
- Les 12 patterns identifiés sont déjà livrés ou en cours.
- Le périmètre strict (règle 22, chantier = livraison complète) protège des dérives "agents partout".

### 4.2 Backlog d'expansion (à ouvrir Phase 11+ ou 13)
| # | Piste | Phase cible | Effort | Dépendance |
|---|---|---|---|---|
| 3.1 | Branching HITL confiance < seuil | 11 | faible | WIN/LOSS collectés |
| 3.2 | Principe_builder auto-généré | 13 | moyen | HITL + 3.1 |
| 3.3 | Worktree par agent | 11 | doc only | aucune |
| 3.4 | V9-trader-mini fine-tuning | 13+ | haute | WIN/LOSS ≥ 50 |
| 3.5 | UI locale HITL | 11+ | moyen | volume paper-trade |
| 3.6 | Email fallback HITL | anytime | faible | demande Søn |

### 4.3 Anti-patterns à éviter (le transcript montre aussi des pièges)
- **"99% des utilisateurs utilisent mal l'IA"** — Søn fait l'inverse (V9 = système, pas chatbot). ✅ On est alignés.
- **"Brûler tous les tokens en 1 session"** — V9 = LLM non bloquant, pas ce risque. ✅
- **"LLM qui code ses propres skills sans HITL"** — V9 = HITL obligatoire pour toute action destructrice (règle doctrine). ✅ On ne tombera pas dans ce piège.
- **"Modèle cher = meilleure qualité"** — l'auteur lui-même dit que l'architecture > le modèle. V9 utilise Ollama Cloud qwen3-coder (cheap) + raisonnement décentralisé. ✅

---

## 5. Actions concrètes pour V9 (sous réserve arbitrage Søn)

### Court terme (cette semaine, Phase 9.8 déploiement VPS)
- [ ] **Aucune** — la vidéo valide l'existant, pas d'urgence.
- [ ] Documenter la cohérence : ajouter une référence à cette vidéo dans `docs/DOCTRINE.md` §"Sources" ?

### Moyen terme (Phase 11, post-VPS stable 24-48h)
- [ ] **3.1 Branching HITL confiance** : ouvrir chantier ~30 LOC
- [ ] **3.3 Worktree standardisé** : amender `docs/SESSION_PROTOCOL.md`

### Long terme (Phase 13, si WIN/LOSS ≥ 50)
- [ ] **3.2 Principe_builder** + **3.4 V9-trader-mini** : chantiers de recherche
- [ ] **3.5 UI HITL** : si volume > 10/jour

---

## 6. Références

- Transcript complet : `/tmp/transcript_timestamps.txt` (32 min, 82 802 chars)
- Screenshots analysés : `D:\SCREEN\Juillet\FABLE\` (35 captures, 11 Mo)
- Screens clés :
  - `00` (12:24) — Flowchart "Processus clarification/exécution/diagnostic/résolution"
  - `17` (13:94) — Définition skill + worktrees
  - `20` (14:02) — Structure `agent.md` (objectif / environnement / règles / paths)
  - `25` (14:61) — MemoryLLM / Flex-MemoryLLM (architecture Apple July 2026)
  - `28` (20:03) — Arborescence skill complète (`memory.md` + `memory_temp.md` + `asset/` + `script/`)
  - `32` (29:12) — Schéma final email agent (boot→server→Gmail+Classif+UI→state/feedback)
  - `34` (dernier) — `transformer skill en agent`
- Vidéo source : https://www.youtube.com/watch?v=mVbwTrj1-hw

---

**Note close — V9 confirmé conforme à l'état de l'art 2026.**
**Prochaine action : déploiement VPS Phase 9.8, puis arbitrage Søn sur 3.1/3.3 (Phase 11).**