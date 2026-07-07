# SESSION_PROTOCOL — démarrage / clôture de session

Complète `docs/PERPLEXITY.md` §« Principe de continuité » et `docs/DOC_GOVERNANCE.md`.
Ne remplace aucune règle de gouvernance documentaire — en précise juste l'exécution côté
session Perplexity/multi-provider.

## Démarrer une session
1. Coller le bloc de `REPRISE_TEMPLATE.md`.
2. Lire dans l'ordre imposé : `BOARD.md` → `docs/CACHE_BOARD.md` → `docs/STATE.md` →
   `ACTIVE_TASKS.md` → `memory/DECISIONS_LOG.md` → dernier checkpoint → `git log`.
3. Vérifier qu'aucun de ces fichiers ne contredit `git log`/`git status`. En cas de
   contradiction : la continuité est rompue, la reconstruire avant de poursuivre
   (ne jamais improviser un état de chantier).
4. Vérifier `ACTIVE_TASKS.md` §« Gelé » avant toute proposition de chantier — ne jamais
   proposer de démarrer un chantier gelé même si le contexte semble le permettre.

## Finir une session
1. Mettre à jour `ACTIVE_TASKS.md` (déplacer les tâches terminées, ajouter les nouvelles).
2. Si une décision structurante a été prise pendant la session, l'ajouter datée dans
   `memory/DECISIONS_LOG.md`.
3. Si un incident opérationnel a eu lieu (bug, comportement inattendu, blocage
   temporaire), le consigner dans `INCIDENTS.md`.
4. Mettre à jour `BOARD.md` si le statut global, le dernier commit structurant ou les
   blocages ont changé.
5. Rappeler explicitement à l'utilisateur si `docs/STATE.md`, `docs/CACHE_BOARD.md` ou
   `docs/ROADMAP.md` nécessitent également une mise à jour côté code (ce workspace ne
   les remplace jamais, voir `docs/DOC_GOVERNANCE.md` règle 1).

## Quand créer un checkpoint
- À la clôture de chaque phase de code (obligatoire, voir `docs/DOC_GOVERNANCE.md`
  règle 4, template : `docs/checkpoints/CHECKPOINT_TEMPLATE.md`).
- À tout jalon structurant même hors clôture de phase (ex. correctif critique comme
  `c83423e`, fusion de gouvernance documentaire).
- Après le test live d'ouverture de marché — utiliser `assets/MARKET_OPEN_TEMPLATE.md`
  pour le mini-checkpoint post-open, distinct d'un checkpoint de phase complet.

## Quand mettre à jour BOARD / STATE / ROADMAP
- **`workspace/perplexity/BOARD.md`** : à chaque changement de statut global, de
  blocage, ou de dernier commit structurant — à chaque fin de session au minimum.
- **`docs/STATE.md`** : à chaque phase livrée ou correctif structurant côté code
  (source de vérité vivante — reste la responsabilité de la session d'implémentation).
- **`docs/ROADMAP.md`** : quand le séquencement des phases restantes change, ou qu'un
  chantier gelé est débloqué (jamais l'inverse sans décision explicite documentée).
- Dans tous les cas, `docs/DOC_REGISTRY.yml` doit être tenu à jour si un document est
  créé ou supprimé (`docs/DOC_GOVERNANCE.md` règle 2).

## Pattern worktree par agent (Phase 11+)

Inspiration : vidéo "Claude Fable 1000x" (2026-07-07, transcript
`workspace/perplexity/inspiration/INSPIRATION_20260707_FABLE.md`).

**Principe** : un agent qui travaille en parallèle d'une session principale
doit utiliser un **worktree dédié** pour isoler ses modifications.

### Quand ouvrir un worktree
- Chantier de code de Phase 11+ impliquant > 1 commit
- Session Claude Code / Zcode parallèle à une session Hermes orchestrateur
- Tout développement > 200 LOC qui ne doit pas bloquer le pipeline live

### Procédure
```bash
# 1. Créer le worktree depuis feat/v9-foundation-clean
cd /d/Projet/V9
git worktree add ../V9_wt_<chantier> -b feat/<chantier>

# 2. Travailler dans le worktree
cd ../V9_wt_<chantier>
# ... commits ...

# 3. Push branche + PR (jamais de merge direct)
git push origin feat/<chantier>
gh pr create --base feat/v9-foundation-clean --head feat/<chantier>

# 4. Après merge, nettoyer
cd /d/Projet/V9
git worktree remove ../V9_wt_<chantier>
```

### Anti-patterns à éviter
- **JAMAIS de worktree partagé entre 2 agents** (race conditions sur DB / fichiers runtime).
- **JAMAIS de commit direct sur feat/v9-foundation-clean depuis un worktree**
  sans PR (règle 26 : 1 commit / DECISIONS_LOG / STATE.md par session).
- **JAMAIS de worktree sans branche dédiée** (sinon conflits de nom).

### Référence incident historique
INCIDENTS.md 2026-07-05 — "Fusion concurrente de branches de phase" : une
session concurrente avait fast-forward mergé une branche de phase dans
`feat/v9-foundation-clean` localement, créant des dirty files parasites.
Le worktree pattern est la **prévention** standard de ce type d'incident.
