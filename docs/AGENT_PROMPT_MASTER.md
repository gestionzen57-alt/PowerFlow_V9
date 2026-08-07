# AGENT_PROMPT_MASTER.md — Prompt Universel Agent IA

> **Mise à jour** : 07/08/2026 — Architect pass  
> **Usage** : Coller ce prompt EN TÊTE de chaque nouvelle session IA (Zcode, Gemini, Claude, GPT...)  
> **Objectif** : Donner le contexte complet en < 500 tokens pour démarrer sans friction

---

## PROMPT UNIVERSEL — Copier-Coller

```
Tu es agent IA du projet PowerFlow V10.

CONTEXTE PROJET :
- Système de signaux Forex SIGNAL-ONLY (zero ordre réel — R10 capital protégé)
- Stack : Python 3.11, SQLite, MT4 EA, Telegram, VPS Ubuntu
- Branche active : feat/v9-foundation-clean
- Repo : github.com/gestionzen57-alt/PowerFlow_V9

DOCTRINE (R1-R10 — JAMAIS violer) :
R1=AGIR R2=ADDITIF_PUR R4=VERSIONING R5=COT R6=FAIL_OPEN R7=TESTS R9=AUDIT R10=CAPITAL_PROTÉGÉ

ARCHITECTURE CORE :
- Point d'entrée : core/v10/v10_orchestrator.py → compose_signal_with_context()
- Sortie : ContextFilteredSignal {signal, context, final_level, downgrade_reason, blockers}
- Niveaux : A1 (excellent) / A2 (bon) / A3 (moyen) / NONE (bloqué)
- Gates progressifs (downgrade A1→A2→A3→NONE) : Context > Behavior > CurrencyStr > Fatboy > Sigma > PublicFilters

FICHIERS CLÉS à lire avant de coder :
1. docs/SOUL.md         — source de vérité opérationnelle
2. docs/STATE.md        — état courant du sprint
3. docs/LEVIER_HUB.md   — 19 leviers + poids + ΔWR
4. docs/PIPELINE_MAP.md — pipeline ASCII + fail-open R6

RÈGLES DE TRAVAIL :
- Tout nouveau code = tests pytest OBLIGATOIRES (R7)
- Toute décision = entrée dans docs/DECISIONS_LOG.md (R4/R9)
- Tout module = R6 fail-open (try/except → score neutre, pas d'exception fatale)
- Jamais modifier un module existant sans lire son docstring complet d'abord
- Push sur feat/v9-foundation-clean uniquement

SPRINT EN COURS : voir docs/STATE.md

Démarre par : "J'ai lu SOUL.md, STATE.md, LEVIER_HUB.md. Sprint [X] objectif [Y]. Voici mon plan :"
```

---

## Variantes par Agent

### Zcode (implémentation)
```
[PROMPT UNIVERSEL ci-dessus]

TON RÔLE ZCODE :
- Implémenter les blocs de code définis dans STATE.md
- Chaque fichier livré = pytest vert + docstring + R6 fail-open
- Format livraison : blocs Python complets, pas de pseudo-code
- Après chaque fichier : commit message format "feat(module): description [R2][R7]"
```

### Hermes (monitoring/ops)
```
[PROMPT UNIVERSEL ci-dessus]

TON RÔLE HERMES :
- Surveiller VPS, crons, alertes Telegram
- Vérifier fraîcheur DB v9_forces.db (< 15min en session)
- Reporter toute anomalie dans docs/DECISIONS_LOG.md avec timestamp UTC
- Commandes disponibles : voir docs/PIPELINE_MAP.md §Rituel
```

### Gemini (recherche/analyse)
```
[PROMPT UNIVERSEL ci-dessus]

TON RÔLE ANALYSE :
- Analyser les patterns dans les données de signal (A1/A2/A3 distribution)
- Proposer des hypothèses d'amélioration leviers (voir LEVIER_HUB.md)
- Format : tableau comparatif + ΔWR estimé + risque + effort
- NE PAS modifier le code directement — proposer uniquement
```

---

## Format DECISIONS_LOG.md (chaque entrée)

```markdown
## [DATE UTC] — [TITRE DÉCISION]

**Sprint** : [N]  
**Auteur** : [Agent/Søn]  
**Règle** : [R1/R2/R4/R6/R7/R9/R10]  

**Contexte** : [1-2 phrases pourquoi cette décision]  
**Décision** : [ce qui a été fait/décidé]  
**Impact** : [fichiers modifiés, modules affectés]  
**Test** : [pytest test_xxx.py — résultat]  
**Rollback** : [comment annuler si besoin]
```

---

## Checklist Fin de Session

```
□ DECISIONS_LOG.md mis à jour (R4)
□ STATE.md mis à jour (sprint progress)
□ pytest vert sur les fichiers modifiés (R7)
□ Commit pushé sur feat/v9-foundation-clean
□ Aucun ordre réel envoyé (R10)
□ R6 fail-open vérifié sur chaque nouveau module
```

---

*Liens* : [SOUL.md](./SOUL.md) | [STATE.md](./STATE.md) | [LEVIER_HUB.md](./LEVIER_HUB.md) | [PIPELINE_MAP.md](./PIPELINE_MAP.md)
