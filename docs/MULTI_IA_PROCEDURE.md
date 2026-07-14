# MULTI_IA_PROCEDURE.md — Coordination PowerFlow V9 multi-providers

> **Statut** : Document de coordination opérationnelle. Complète `docs/PERPLEXITY.md`, `workspace/perplexity/PROVIDER_STATUS.md`, et `docs/GIT_OPERATOR_PROCEDURE.md`.
> **Auteur** : Hermes (mode Y). Date : 2026-07-09.
> **Public** : Søn (CEO), Perplexity, Claude Code, Zcode, et tout futur agent.

---

## 1. Cartographie actuelle (2026-07-09)

PowerFlow V9 collabore avec **4 providers IA** + 1 humain. Chacun a un rôle non-substituable :

| Acteur | Rôle | Code ? | Git direct ? | Canal de communication |
|--------|------|--------|--------------|------------------------|
| **Søn** | CEO, lectures marché, décisions finales, validation HITL | Non | Non | Chat direct / Telegram |
| **Hermes** | Orchestrateur H24, opérateur git unique (R28 — assouplie 14/07 : délégation sur motion CEO explicite), observateur live | Oui | **OUI (seul)** | Direct |
| **Perplexity** | Doctrine, orchestration, structure, checkpoints, continuité | Non | Non | `workspace/perplexity/exchange.md` |
| **Claude Code** | Implémentation structurée, PR review, refactoring | Oui (assisté) | Non (via Hermes) | Brief Perplexity → Hermes |
| **Zcode** | DeepSeek-V4-Flash (Ollama Cloud) — partenaire technique implémentation | Oui (assisté) | Non (via Hermes) | `workspace/perplexity/exchange.md` |

> **Point clé** : Hermes est le seul à toucher au repo. Les autres IA préparent le travail, Hermes l'exécute.

---

## 2. Qui fait quoi — matrice opérationnelle

| Tâche | Søn | Hermes | Perplexity | Claude Code | Zcode |
|-------|-----|--------|------------|-------------|-------|
| Lecture marché (HITL final) | ✓ | — | — | — | — |
| Décision WIN/LOSS papier | ✓ | propose | — | — | — |
| Commit / push git | — | ✓ | — | — | — |
| Test `pytest` après modif | — | ✓ | — | — | — |
| Rédiger checkpoint phase | — | assiste | ✓ | — | — |
| Mettre à jour STATE.md | — | ✓ (implémenteur) | ✓ (synthèse) | — | — |
| Mettre à jour DECISIONS_LOG | — | ✓ (implémenteur) | ✓ (doctrinal) | — | — |
| Implémenter code dans `core/v9/` | — | ✓ | — | ✓ (assisté) | ✓ (assisté) |
| Modifier `principles/*.yaml` | — | — | — | — | — (interdit R25') |
| Modifier `config.py` / `orchestrator.py` | — | — | — | — | — (gelés) |
| Maintenance DB (`v9_db_hygiene`) | — | ✓ | — | — | — |
| Calibration (`v9_calibration`) | — | ✓ | consulte | — | — |
| Telegram notifier (lecture) | — | ✓ | — | — | — |

---

## 3. Flux de travail canonique (multi-IA)

### 3.1 Søn → Perplexity → Hermes → Claude/Zcode → Hermes → Git

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Søn (CEO)                                                             │
│    │                                                                    │
│    │ "Je veux une feature X" ou "Résous bug Y"                         │
│    ▼                                                                    │
│  Perplexity (doctrine)                                                 │
│    │                                                                    │
│    │ Brief doctrinal + ancrage dans doc existant                       │
│    │ (ex: "cf. CHARTE_COGNITIVE_V9 §3.2")                              │
│    ▼                                                                    │
│  Hermes (opérateur git + observateur)                                  │
│    │                                                                    │
│    │ Reçoit brief, prépare worktree si nécessaire                     │
│    │ Délègue l'implémentation à Claude Code ou Zcode                  │
│    ▼                                                                    │
│  Claude Code / Zcode (implémentation assistée)                         │
│    │                                                                    │
│    │ Code dans worktree dédié (Phase 11+)                            │
│    │ Retourne diff + résumé à Hermes                                  │
│    ▼                                                                    │
│  Hermes (finalisation)                                                  │
│    │                                                                    │
│    │ 1. Reprend le diff                                                │
│    │ 2. Tests verts                                                    │
│    │ 3. Commit atomique                                                │
│    │ 4. Update STATE.md / DECISIONS_LOG                                │
│    │ 5. Push origin                                                    │
│    ▼                                                                    │
│  GitHub (source de vérité)                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Variante : Søn → Hermes direct (mode Y)

Pour les chantiers techniques sans enjeu doctrinal (ex: backup MD5, fix typo, maintenance DB) :
- Søn → Hermes direct
- Pas de brief Perplexity
- Hermes commit + push + entrée DECISIONS_LOG

---

## 4. Règles de communication inter-IA

### 4.1 Canal de coordination principal

`workspace/perplexity/exchange.md` — bus asynchrone Hermes↔Zcode (historiquement). Mis à jour par Hermes à chaque fin de tâche.

Format d'une entrée :
```
- task         : <description courte>
- target_agent : <Søn / Hermes / Perplexity / Claude / Zcode>
- outputs      : [liste fichiers modifiés]
- status       : TERMINÉ / EN_COURS / BLOQUÉ
- next_action  : <qui fait quoi ensuite>
```

### 4.2 Handoff (passage de relais)

Chaque handoff doit contenir :
1. **SHA du dernier commit** (preuve factuelle de l'état)
2. **Branche active** (état du worktree)
3. **Fichiers modifiés** (résumé)
4. **Tests passés** (oui/non + count)
5. **Prochaine action attendue** (par qui)

### 4.3 Conflit doctrinal (rare mais bloquant)

Si Claude Code ou Zcode détecte une ambiguïté de doctrine pendant l'implémentation :
1. **Stop immédiat** (règle 6 : 3 échecs max sur même fichier)
2. Remonter à Perplexity (le brief doctrinal prime sur l'implémentation)
3. Perplexity tranche ou escalade à Søn

---

## 5. Worktrees par agent (Phase 11+)

Inspiration : `workspace/perplexity/SESSION_PROTOCOL.md` §"Pattern worktree par agent" + vidéo FABLE.

### 5.1 Quand ouvrir un worktree

- Chantier > 200 LOC ne devant pas bloquer le pipeline live
- Session Claude Code / Zcode parallèle à Hermes orchestrateur
- Chantier impliquant > 1 commit

### 5.2 Procédure (toujours via Hermes, jamais directe par l'IA)

```bash
# 1. Hermes crée le worktree depuis feat/v9-foundation-clean
cd /d/Projet/V9
git worktree add ../V9_wt_<chantier> -b feat/<chantier>

# 2. L'IA (Claude/Zcode) travaille DANS le worktree
#    MAIS ne fait JAMAIS de git elle-même
cd ../V9_wt_<chantier>

# 3. À la fin, l'IA retourne le diff à Hermes
#    Hermes commit + push + PR
cd /d/Projet/V9
git push origin feat/<chantier>
gh pr create --base feat/v9-foundation-clean --head feat/<chantier>
```

### 5.3 Anti-patterns

- ❌ **Worktree partagé entre 2 agents** (race conditions DB)
- ❌ **Commit direct dans le worktree par l'IA** (R28 strict)
- ❌ **Worktree sans branche dédiée** (conflit de nom)

---

## 6. Søn — point d'entrée unique

### 6.1 Quand Søn parle à une IA spécifique

- **Question doctrine/structure** → Perplexity (court terme), puis dans `STATE.md`/`CACHE_BOARD.md` pour la trace
- **Action git (commit/push/branch)** → Hermes uniquement
- **Implémentation code** → Hermes (qui délègue éventuellement à Claude/Zcode)
- **Question marché (HITL)** → Søn tranche lui-même

### 6.2 Søn n'a PAS besoin de savoir qui fait quoi

Søn formule sa demande en langage naturel. Hermes route :
- Demande technique sur code existant → exécution directe
- Demande impliquant nouveau module → brief Perplexity d'abord si > 100 LOC
- Demande ambiguë → `clarify` tool pour désambiguïser

### 6.3 Søn ne tape JAMAIS de git

Règle 28 explicite. Hermes gère tout. Exceptions (re-ask autorisé) :
- (a) credential/2FA demandé
- (b) force-push destructif
- (c) opération irréversible hors scope session

---

## 7. Templates de reprise (à coller par chaque IA)

| Fichier | Pour qui | Premier message |
|---------|----------|-----------------|
| `workspace/perplexity/REPRISE_TEMPLATE.md` | Perplexity | Reprise doctrinale, 10 fichiers dans l'ordre |
| `workspace/perplexity/REPRISE_TEMPLATE_HERMES.md` | Hermes | Reprise opérationnelle, 10 fichiers + git |
| `workspace/perplexity/REPRISE_TEMPLATE_CLAUDE.md` | Claude Code | Reprise courte (23 lignes), focus exécution |

**Distinction critique** :
- Perplexity = doctrine, pas de code
- Hermes = tout (opérateur git + observateur + implémenteur)
- Claude Code = implémentation uniquement (jamais de git direct)
- Zcode = idem Claude Code (deepseek-v4-flash via Ollama Cloud)

---

## 8. Sécurité & secrets

### 8.1 Stockage

| Secret | Localisation | Commit ? |
|--------|--------------|----------|
| PAT GitHub | `~/.hermes/profiles/powerflow/.env` (var `GITHUB_TOKEN`) | ❌ JAMAIS |
| Clé Ollama Cloud | `~/.hermes/profiles/powerflow/config.yaml` (var `model.api_key`) | ❌ JAMAIS |
| Telegram bot token | `.env` (racine projet, gitignored) | ❌ JAMAIS |
| Auth Claude Code | Windows Credential Manager (`~/.claude/`) | ❌ JAMAIS |

### 8.2 .gitignore (déjà en place)

`workspace/perplexity/memory/backups_*/`, `data/*.db`, `logs/*.log`, `.env`, `output/`, etc. (cf. `.gitignore`).

### 8.3 Rotation

- PAT GitHub : recommandé tous les 90 jours (token fine-grained)
- Clé Ollama Cloud : à chaque compromission
- Telegram bot : jamais en clair dans le repo (déjà géré)

---

## 9. Checklist par type de tâche

### 9.1 Nouvelle feature

- [ ] Brief Perplexity (si > 100 LOC ou touche doctrine)
- [ ] Périmètre explicité (R22 : 1 livraison = 1 chantier)
- [ ] Tests verts (R7)
- [ ] 1 commit atomique
- [ ] DECISIONS_LOG entry
- [ ] STATE.md à jour
- [ ] Push origin

### 9.2 Bug fix

- [ ] Diagnostic (`systematic-debugging` skill si besoin)
- [ ] Fix + test de régression
- [ ] 1 commit `fix(v9)`
- [ ] INCIDENTS.md si impact live
- [ ] Push origin

### 9.3 Documentation

- [ ] Périmètre (un seul doc cible)
- [ ] Pas de modif code
- [ ] 1 commit `docs(v9)`
- [ ] Push origin

### 9.4 Maintenance (DB, scripts, deps)

- [ ] Backup MD5 avant
- [ ] Modif + test smoke
- [ ] 1 commit `chore(v9)`
- [ ] JOURNAL.md entry si impact ops
- [ ] Push origin

---

## 10. Liens internes

- `docs/GIT_OPERATOR_PROCEDURE.md` — Procédure git détaillée (auth, push, branches)
- `docs/PERPLEXITY.md` — Rôle Perplexity
- `workspace/perplexity/PROVIDER_STATUS.md` — Tableau des providers (état actuel)
- `workspace/perplexity/SESSION_PROTOCOL.md` — Démarrage / clôture de session
- `workspace/perplexity/exchange.md` — Bus de coordination Hermes↔Zcode
- `workspace/perplexity/REPRISE_TEMPLATE*.md` — Templates par IA
- `docs/DOCTRINE.md` — Règles immuables (notamment R22, R26, R28)

---

*Ce document est vivant. Toute évolution de l'organisation multi-IA doit être
tracée dans `workspace/perplexity/memory/DECISIONS_LOG.md` et re-validée par Søn.*