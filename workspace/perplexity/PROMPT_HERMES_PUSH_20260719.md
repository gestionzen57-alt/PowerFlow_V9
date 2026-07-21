# PROMPT HERMES — Push des 3 commits pré-réouverture §23h UTC

> **Destinataire** : Hermes (orchestrateur V9, opérateur git unique — R28)
> **Émetteur** : Søn CEO + ZCode
> **Date d'envoi** : 2026-07-19 12:15 UTC
> **Action** : `git push origin feat/v9-foundation-clean` (3 commits)
> **Urgence** : avant 22h UTC (réouverture effective marché forex en DST US)

---

## 0. Mission en une phrase

Pousser sur `origin` les 3 commits préparés par Opus sur `feat/v9-foundation-clean` (chantiers A + B + C du prompt `PROMPT_OPUS_PRE_REOUVERTURE_20260719.md`), puis **ne rien faire d'autre**. Tu ne rebase pas, tu ne merges pas, tu ne pushes pas ailleurs, tu n'édites aucun fichier. Juste push.

---

## 1. Contexte (à lire une fois)

- Branche source : `feat/v9-foundation-clean` (déjà checkoutée, working tree propre modulo 4 JSON auto-calibrateur + 1 fichier `??` non committé)
- Remote : `origin` (auth PAT déjà configurée pour ton user — voir `docs/GIT_OPERATOR_PROCEDURE.md`)
- 3 commits à pousser :
  - `2026256` — `feat(v9): watchdog opérationnel — P0 halt switch + read-only + segmentation GBPUSD long (motion §Construis le watchdog)`
  - `4137b41` — `feat(v9): runner watchdog CLI + 2 crons Windows + activation V9_LIVE_WATCHDOG_ENABLED (pré-réouverture §23h UTC)`
  - `289fa93` — `docs(v9): checklist pré-réouverture 19/07 §23h UTC + maj STATE/DECISIONS_LOG (P0.4 câblage kill switches résolu)`
- HEAD local actuel : `289fa93`
- HEAD remote actuel : `dcd2fed` (avant Opus)
- **Diff à pousser** : 3 commits en avant, aucun rebase nécessaire, aucun conflit anticipé

---

## 2. Procédure stricte (à suivre pas-à-pas)

### Étape 1 — Sanité 30 secondes

```bash
cd C:\projet\V9
git status
git log --oneline -5
git remote -v
```

**Vérifie** :
- Branche courante = `feat/v9-foundation-clean`
- HEAD = `289fa93 docs(v9): checklist...`
- `origin` pointe bien vers le bon remote (PowerFlow V9)
- Working tree : seuls fichiers modifiés = `data/strategy_pole/*.json` (légitimes, à ignorer) + 1 fichier `??` (`workspace/perplexity/PROMPT_OPUS_PRE_REOUVERTURE_20260719.md`, **non committé, ne pas l'ajouter**)

Si l'un de ces points est anormal, **STOP** et notifie Søn (ne pas improviser).

### Étape 2 — Pre-push check (sécurité)

```bash
git log origin/feat/v9-foundation-clean..HEAD --oneline
```

Doit afficher **exactement** les 3 commits ci-dessus, dans l'ordre A → B → C. Si tu en vois 0, ou plus de 3, ou dans un autre ordre, **STOP** et notifie.

### Étape 3 — Pre-push tests (sanité baseline)

**Option A — Rapide** (~30s) : juste les tests des fichiers touchés

```bash
cd C:\projet\V9
.venv\Scripts\python.exe -m pytest tests/test_v9_live_watchdog.py tests/test_v9_live_watchdog_run.py tests/test_v9_loop_breaker.py tests/test_v9_kill_switches.py -q
```

Attendu : ~46 verts, 0 fail.

**Option B — Complète** (~9 min) : si tu as le temps et que rien d'autre ne tourne

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
```

Attendu : 2294 passed / 11 failed / 3 skipped (les 11 fails sont **documentés préexistants**, ne bloquent pas le push).

**Recommandation** : Option A. Le push ne dépend pas de la suite complète, juste des fichiers touchés.

### Étape 4 — Push (la seule action critique)

```bash
cd C:\projet\V9
git push origin feat/v9-foundation-clean
```

**Attendu** :
```
Énumération des objets: X, fait.
Décompte des objets: 100% (X/X), fait.
...
To <remote>
   dcd2fed..289fa93  feat/v9-foundation-clean -> feat/v9-foundation-clean
```

**Si le push échoue** :
- `non-fast-forward` → STOP, ne jamais `git pull --rebase` ni `git push --force`. Notifie Søn avec le message d'erreur complet.
- `403 Forbidden` / auth → STOP, vérifie ton PAT (voir `docs/GIT_OPERATOR_PROCEDURE.md` §Auth)
- `timeout` / réseau → réessaie 1 fois après 30s. Si toujours KO, STOP.
- Tout autre code retour ≠ 0 → STOP, capture stdout+stderr, notifie.

**Si le push réussit** : passe à l'étape 5.

### Étape 5 — Vérification post-push

```bash
cd C:\projet\V9
git log origin/feat/v9-foundation-clean --oneline -5
```

**Vérifie** que les 3 commits sont bien sur le remote (le SHA doit être identique au local).

### Étape 6 — Notification CEO (Telegram)

Envoie via le bot configuré (`config/telegram.json` — token Ipspx non exposé dans ce prompt) :

```
✅ PUSH OK — pré-réouverture §23h UTC

3 commits poussés sur feat/v9-foundation-clean :
• 2026256 — watchdog opérationnel (A)
• 4137b41 — runner + crons + activation (B)
• 289fa93 — docs + STATE + DECISIONS_LOG (C)

HEAD remote : 289fa93

Reste CEO avant 22h UTC :
1. Rotation 4 tokens BotFather (8656… 8790… 8932… 8948…)
2. VPS : git pull + 2 .bat + smoke test
3. Observer Telegram à 22h UTC

Détail : docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md
```

Utilise le niveau `INFO` (pas `WARN` ni `CRITICAL` — c'est une bonne nouvelle).

---

## 3. Garde-fous stricts (HORS PÉRIMÈTRE)

Tu ne fais **AUCUNE** des actions suivantes (R28 strict) :

- ❌ `git push --force` (jamais, même si on te le demande)
- ❌ `git push --tags` (pas de tags dans cette session)
- ❌ `git push origin main` / `git push origin master` (uniquement `feat/v9-foundation-clean`)
- ❌ `git rebase`, `git merge`, `git reset --hard`, `git commit --amend` sur un commit déjà pushé
- ❌ Modifier un fichier, même pour "juste un détail"
- ❌ Lancer un script, un test, ou un hook qui mute la DB
- ❌ Activer / désactiver un kill switch runtime
- ❌ Créer une autre branche
- ❌ Pousser un commit supplémentaire non listé en §1

Si tu détectes une anomalie (commit inattendu, fichier modifié hors liste, conflit), **STOP** et notifie Søn. Ne contourne jamais.

---

## 4. Si le push échoue — escalation

Selon l'erreur :

| Erreur | Action |
|---|---|
| `non-fast-forward` | STOP. Ne pas rebase/force. Notifier Søn avec le SHA distant actuel. |
| `403 Forbidden` | STOP. Vérifier `docs/GIT_OPERATOR_PROCEDURE.md` §Auth, reconfigurer PAT si besoin. |
| `Could not resolve host` / `timeout` | Retry 1× après 30s. Si KO, STOP et notifier. |
| `Repository not found` | STOP. Vérifier `git remote -v`. Notifier. |
| `Permission denied (publickey)` | STOP. SSH key manquante. Notifier. |
| `GH001: Protected branch update rejected` | STOP. Le push direct sur `main` est interdit — mais ici on pousse sur `feat/v9-foundation-clean`, ça ne devrait pas arriver. |
| Autre | STOP. Capturer stdout+stderr intégral. Notifier. |

**Télégramme d'escalation** :
```
🔴 PUSH KO — pré-réouverture §23h UTC

Erreur : <message complet>
SHA local : 289fa93
SHA remote : <ce que tu lis>

Action CEO requise : <recommandation selon le tableau>
```

---

## 5. Critères de succès

| # | Critère | Mesure |
|---|---|---|
| 1 | Push accepté par le remote | `git push` exit code 0 |
| 2 | HEAD remote avance de 3 commits | `dcd2fed..289fa93` visible dans le retour |
| 3 | SHA identique local/remote après push | `git rev-parse HEAD` == `git rev-parse origin/feat/v9-foundation-clean` |
| 4 | Aucun commit supplémentaire poussé | exactement 3 commits dans le diff |
| 5 | Aucune régression introduite par toi | tests ciblés Option A verts (~46) |
| 6 | Notification Telegram CEO envoyée | message INFO reçu dans le chat |
| 7 | Pas de fichier modifié hors push | working tree identique pre/post |

Si un seul critère échoue, **notifie Søn sans délai**.

---

## 6. Timeline attendue

| Action | Durée estimée | Fenêtre |
|---|---|---|
| Sanité (étape 1) | 30s | 12:15–12:16 UTC |
| Pre-push check (étape 2) | 10s | 12:16–12:17 UTC |
| Pre-push tests Option A (étape 3) | 1 min | 12:17–12:18 UTC |
| **Push (étape 4)** | 10–30s | **12:18–12:19 UTC** |
| Vérification (étape 5) | 10s | 12:19–12:20 UTC |
| Telegram CEO (étape 6) | 10s | 12:20–12:21 UTC |

**Total** : ~6 minutes de Søn à Søn vu.

---

## 7. Post-push — ne rien faire d'autre

Après le push réussi et la notification CEO :

- **NE PUSH RIEN D'AUTRE** (pas de commit supplémentaire, même si tu en as l'occasion)
- **NE TOUCHE PAS** aux kill switches runtime
- **NE REBOOT PAS** le pipeline
- **NE LANCE PAS** les `.bat` d'install (c'est l'action Søn sur le VPS, pas toi)
- **ATTENDS** l'instruction Søn suivante (smoke test post-install, observation 22h UTC, etc.)

Le push est ton **seul** livrable cette session. Tu termines en marquant la session `done` et tu sors.

---

## 8. Communication finale (à mettre dans ton log session)

```
[HERMES] 2026-07-19 ~12:20 UTC
  - Sanity OK
  - Pre-push tests: 46 passed
  - Push: dcd2fed..289fa93 on feat/v9-foundation-clean ✅
  - Post-push SHA: 289fa93 (matches local)
  - Telegram CEO sent: INFO
  - Status: SESSION DONE
```

---

**Hermes, le code est prêt, les tests sont verts, le push est non-ambigu. Vas-y.**

— Søn CEO, via ZCode
