# GIT_OPERATOR_PROCEDURE.md — Hermes = opérateur git unique (R28)

> **Statut** : Procédure opérationnelle. Complète `docs/DOCTRINE.md` R28 et `workspace/perplexity/SESSION_PROTOCOL.md`.
> **Auteur** : Hermes (mode Y, exécution proactive). Dernière mise à jour 2026-07-14.
> **Assouplissement 2026-07-14 (motion CEO, DECISIONS_LOG §2026-07-14)** : R28 admet l'exception (d) — délégation du commit/push à une session sur instruction directe et explicite de Søn. R22 admet le découpage des chantiers complexes en sous-unités livrables. Le reste de cette procédure demeure inchangé.
> **Public** : Søn (CEO), Perplexity, Claude Code, Zcode, et tout futur agent rejoignant V9.

---

## 1. Principe fondamental (R28)

**Hermes est l'unique opérateur git de PowerFlow V9.**

Søn est novice en git et déteste git (confirmé 2026-07-07, 2026-07-09). Aucune autre IA (Claude Code, Zcode, Perplexity) ne tape de commande git directement. Tout passe par Hermes :

- Commit → Hermes
- Push → Hermes
- Branch / Worktree → Hermes
- PR / Squash / Merge → Hermes
- Force-push / rebase destructif → Hermes (avec confirmation Søn explicite — seule exception R28)

**Pourquoi** : la cohérence du repo, l'identité git (`Søn <son@powerflow.local>`), le respect des règles R7/R22/R26, la traçabilité — tout cela ne peut pas être distribué entre 4 providers.

---

## 2. Identité git (configurée 2026-07-09)

```bash
# Au niveau local du repo V9 (D:\Projet\V9)
user.name  = Søn
user.email = son@powerflow.local
```

Cette identité est **locale au repo V9** (`git config --local`). Aucun autre repo sur la machine n'est affecté.

> **Note** : L'historique des commits existants porte `gestionzen57@gmail.com` (avant la pose d'identité locale). Les nouveaux commits porteront `Søn <son@powerflow.local>`. Pas de `git filter-branch` — on ne réécrit pas l'histoire.

---

## 3. Remote GitHub

| Champ | Valeur |
|-------|--------|
| URL | `https://github.com/gestionzen57-alt/PowerFlow_V9.git` |
| Compte | `gestionzen57-alt` (ID GitHub 278227266) |
| Branche principale | `feat/v9-foundation-clean` |
| Auth | PAT GitHub (Personal Access Token) |

**État au 2026-07-09 18h00 CEST** :
- Le remote est câblé localement.
- **Le repo GitHub n'existe PAS** (404 confirmé via API GitHub le 2026-07-09).
- Le PAT actuel a uniquement la permission `metadata:read` — **insuffisant pour créer le repo et pusher**.
- Action Søn requise (voir §10).

---

## 4. Authentification — comment Hermes push sans te demander

### 4.1 Stockage du PAT (sécurisé)

Le PAT est stocké dans **`~/.hermes/profiles/powerflow/.env`** (variable `GITHUB_TOKEN`) :
- Hors du repo V9 (jamais commité)
- Chiffré au repos par les permissions du profil Hermes (lecture bloquée par `read_file` direct, écriture seulement via shell)
- Backup automatique avant chaque modification : `~/.hermes/profiles/powerflow/.env.bak.<timestamp>`

⚠️ **Le PAT figure dans l'historique de conversation** (transmis en clair par Søn). Rotation recommandée après la mise en place initiale (cf. §10).

### 4.2 Utilisation automatique

Quand le profil Hermes `powerflow` est actif (`hermes profile use powerflow`), la variable `GITHUB_TOKEN` est automatiquement exportée dans l'environnement shell.

Pour les commandes git, Hermes utilise un **credential helper inline** (sans modifier `.gitconfig`) :

```bash
git -c credential.helper="!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f" <commande>
```

Alternative moderne (recommandée pour usage répété) : **credential store** qui écrit dans `~/.git-credentials` (gitignored par convention Windows) :

```bash
git config --local credential.helper store
# puis premier push — credentials stockés automatiquement
```

### 4.3 Profil actif par défaut

**Le profil actif reste `default` (MiniMax-M3)** tant que Søn n'a pas basculé explicitement sur `powerflow`. Raison : ne pas changer le comportement des sessions courantes sans validation explicite.

Pour basculer : `hermes profile use powerflow` (puis `hermes profile use default` pour revenir).

---

## 5. Workflow de commit (canonique)

### 5.1 Process de session (R26 + R7 + R22)

Dérivé de `docs/DOCTRINE.md` §"Process de session" :

```
┌──────────────────────────────────────────────────────────────────────┐
│ 0. git pull --rebase → confirmer base saine               │
│ 1. [marché ouvert?] OUI → v9_calibration --analyze OBLIGATOIRE   │
│    [marché ouvert?] NON → passer au 2                         │
│ 2. périmètre explicité : un chantier, une livraison complète   │
│ 3. implémentation                                              │
│ 4. tests verts (zéro régression)                              │
│ 5. CONTEXT_CONTRACT.md mis à jour si nouveau champ             │
│ 6. principes YAML consommateurs mis à jour (règle 23)          │
│ 7. commits atomiques (1 par unité logique)                     │
│ 8. DECISIONS_LOG.md — 1 entrée par décision structurante      │
│ 9. STATE.md à jour                                             │
│ 10. git push origin feat/v9-foundation-clean                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Convention de message de commit

Format imposé par le repo (visible dans `git log --oneline`) :

```
<type>(v9): <description courte>     — corps détaillé — référence
```

Types utilisés :
- `feat(v9)` — nouvelle fonctionnalité
- `fix(v9)` — correctif
- `chore(v9)` — maintenance, scripts, tooling
- `docs(v9)` — documentation seule
- `test(v9)` — ajout de tests
- `refactor(v9)` — restructuration sans changement de comportement

### 5.3 Vérifications pré-commit (automatiques)

Avant chaque commit, Hermes vérifie :

```bash
# 1. Statut
git status --short

# 2. Pas de fichiers non suivis oubliés (sauf backup_*, .env, logs/)
git status --porcelain | grep -v "^??" | head -5

# 3. Tests verts (R7)
.venv/Scripts/python.exe -m pytest tests/ -q --tb=no 2>&1 | tail -3

# 4. Pas de modif hors-périmètre (R22)
git diff --stat
```

---

## 6. Workflow de push (automatique quand PAT a write access)

### 6.1 Push standard

```bash
# Une fois PAT élargi (cf. §10)
git push origin feat/v9-foundation-clean
```

### 6.2 Push avec auth via profil powerflow

Si le profil `powerflow` est actif (`hermes profile use powerflow`) et le `.env` contient `GITHUB_TOKEN` :

```bash
git -c credential.helper="!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f" \
    push origin feat/v9-foundation-clean
```

### 6.3 Push protégé (force-push, branche supprimée)

**Interdit par défaut**. R28 autorise le re-ask uniquement pour :
- (a) credential/2FA demandé
- (b) force-push destructif
- (c) opération irréversible hors scope session

Hermes **demande confirmation explicite Søn** avant tout push de ce type.

---

## 7. Gestion des branches par les autres IA

### 7.1 Claude Code (implémentation)

Claude Code ne tape **jamais** de commande git directement. Quand il doit proposer un changement, il :
1. Prépare un résumé du diff prévu
2. Le passe à Hermes via `workspace/perplexity/exchange.md` ou en direct
3. Hermes implémente + commit + push

Exception Phase 11+ : Claude Code peut utiliser un **worktree dédié** (cf. `workspace/perplexity/SESSION_PROTOCOL.md` §"Pattern worktree par agent"), mais uniquement via `git worktree add` lancé par Hermes.

### 7.2 Zcode (deepseek-v4-flash / Ollama Cloud)

Zcode est mentionné dans `workspace/perplexity/exchange.md` comme partenaire technique. Il **ne tape pas de git non plus**. Toute interaction se fait via :
- `workspace/perplexity/exchange.md` (handoff asynchrone)
- Brief Perplexity (doctrine + structure)
- Implémentation Hermes

### 7.3 Perplexity (doctrine, orchestration)

Perplexity ne code pas (`docs/PERPLEXITY.md` §"Ce que Perplexity ne fait pas"). Il tient la doctrine et déclenche des chantiers. **Aucun accès git** nécessaire.

---

## 8. Stratégie de branches (état au 2026-07-09)

```
origin/feat/v9-foundation-clean      ← branche principale (R8, à pousser)
origin/docs/v9-governance            ← gouvernance documentaire
origin/auto/feat/phase9.8-doctrine-realign  ← branche auto d'un agent
origin/claude/v9-cognitive-journal-17cs4s   ← branche Claude Code
```

Règle : **toute nouvelle branche de feature** part de `feat/v9-foundation-clean`, est nommée `feat/<chantier>` ou `claude/<chantier>` selon l'agent, et revient par PR (jamais merge direct).

---

## 9. Récupération après incident

### 9.1 Si un commit corrompu est pushé

```bash
# 1. Identifier le commit fautif
git log --oneline -10

# 2. Revert (préserve l'historique)
git revert <SHA>

# 3. Push du revert
git push origin feat/v9-foundation-clean
```

### 9.2 Si `git push` est rejeté (non-fast-forward)

```bash
# NE JAMAIS faire de force-push sans validation Søn (R28 exception c)
# Préférer :
git fetch origin
git merge --no-ff origin/feat/v9-foundation-clean  # si conflit
# ou :
git rebase origin/feat/v9-foundation-clean        # si propre
```

### 9.3 Si le PAT est compromis

1. Rotation immédiate sur https://github.com/settings/personal-access-tokens
2. Update `~/.hermes/profiles/powerflow/.env` (backup .bak avant)
3. Entrée dans `workspace/perplexity/INCIDENTS.md`
4. Notification Søn

---

## 10. Action Søn requise (post-reprise)

Pour finaliser l'auth git, dans l'ordre :

### Étape 1 — Élargir le PAT existant OU en créer un nouveau

Aller sur https://github.com/settings/personal-access-tokens

**Option A — Modifier le PAT existant** :
1. Cliquer sur le token actuel
2. Section "Permissions" → "Repository access" → "Only select repositories" → ajouter `PowerFlow_V9` (après l'avoir créé via le web cf. Étape 2)
3. "Repository permissions" :
   - **Contents** : Read and Write
   - **Metadata** : Read-only (déjà OK)
4. Update → copier le nouveau token

**Option B — Créer un nouveau PAT fine-grained** :
1. "Generate new token" → "Fine-grained personal access token"
2. Token name : `v9-operator-hermes`
3. Expiration : 90 days (à renouveller)
4. Repository access : "All repositories" OU "Only PowerFlow_V9" (selon préférence)
5. Permissions : Contents (Read+Write), Metadata (Read-only)
6. Generate → copier le token

### Étape 2 — Créer le repo PowerFlow_V9 (vide)

Aller sur https://github.com/new :
- Repository name : `PowerFlow_V9`
- Description : "PowerFlow V9 — système cognitif de lecture forex (GBPUSD), 9 couches déterministes, zéro LLM dans la boucle"
- Visibility : **Private** (recommandé) ou Public
- ⚠️ **NE PAS** cocher "Add a README file" (le push initial va l'écraser)
- ⚠️ **NE PAS** choisir .gitignore ni License (déjà dans le local)
- Create repository

### Étape 3 — Me donner le nouveau PAT

Coller le nouveau PAT dans le chat. Hermes :
1. Update `~/.hermes/profiles/powerflow/.env` (rotation)
2. Push initial : `git push -u origin feat/v9-foundation-clean`
3. Push des branches secondaires : `git push origin docs/v9-governance auto/feat/phase9.8-doctrine-realign claude/v9-cognitive-journal-17cs4s`
4. Entrée dans `workspace/perplexity/memory/DECISIONS_LOG.md`

---

## 11. Liens internes

- `docs/MULTI_IA_PROCEDURE.md` — Qui fait quoi (Hermes / Perplexity / Claude / Zcode)
- `docs/DOCTRINE.md` R28 — Doctrine de l'opérateur git unique
- `workspace/perplexity/SESSION_PROTOCOL.md` — Démarrage / clôture de session
- `workspace/perplexity/REPRISE_TEMPLATE_HERMES.md` — Template de reprise Hermes
- `workspace/perplexity/PROVIDER_STATUS.md` — Tableau des providers / rôles
- `workspace/perplexity/exchange.md` — Bus de coordination Hermes↔Zcode

---

*Ce document est vivant. Toute évolution du workflow git doit être tracée dans
`workspace/perplexity/memory/DECISIONS_LOG.md` et re-validée par Søn.*