# DOCTRINE 48H NON-STOP — PowerFlow V10

> **🚨 V10 doctrine (2026-08-04 05:00 UTC)** : V9 verrouillé (R0-R30)
> → V10 libre (R1-R10). CEO mandate libération agentive.
> V10 = V11 = système sans permission, intelligent, auto-apprenant.
> Voir `AGENTS.md` §DOCTRINE V10 + `docs/V10/V10_PLAN_REPARALETTRAGE.md`.

> **Source de vérité** : philosophie d'auto-perpétution du système.
> Permet à Hermes de travailler **24/7 sans intervention humaine**.

## ★ VISION ★

Transformer PowerFlow V9 en **système auto-perpétuant** qui :
- **NE demande JAMAIS** confirmation "motion CEO suivante"
- **NE s'arrête JAMAIS** tant que la machine tourne
- **Persiste son état** entre sessions (compaction + restart)
- **Auto-corrige** les erreurs via repair loop
- **Auto-documente** à chaque cycle (BILAN + INDEX + USER_GUIDE)
- **Auto-commit + push** inline

## ★ LES 7 RÈGLES FONDAMENTALES ★

### R1 — ZÉRO CONFIRMATION
- Aucune question "motion CEO suivante ?"
- Aucun "tu veux que je continue ?"
- Aucun "Go pour la suite ?"
- Doctrine : **on itère, point**.

### R2 — BOUCLE CONTINUE
- Phase 1 → Phase 2 → Phase 3 → ... → Phase N → boucle
- Si une phase échoue : **repair**, **puis continue**
- Si le subject n'a plus de phases : **génère** depuis roadmap

### R3 — STATE PERSISTENCE
- `data/v9_autonomous_state.json` : persistant
- Mis à jour à chaque phase
- Lu au démarrage (chaque session)
- Compaction-safe : pas d'info critique en RAM

### R4 — AUTO-COMMIT INLINE
- Chaque phase terminée = 1 commit + 1 push
- Pas de batch en fin de session
- Convention de commit : `feat(v9): Phase X - <description>`
- Push sur `feat/v9-foundation-clean` immédiatement

### R5 — AUTO-COHERENCE DOCS
- À chaque phase : update `INDEX_MODULES.md`
- Update `USER_GUIDE.md` si nouveau module
- Update `BILAN_FINAL_*.md` si fin de cycle
- Validation : grep sur fichiers obsolètes

### R6 — AUTO-PRIORITÉ
- Score stat par phase :
  - 30% : impact institutionnel
  - 30% : couverture tests
  - 20% : simplicité
  - 20% : dépendance
- Tri DESC : phase prioritaire en premier

### R7 — AUTO-TERMINATE
- Si elapsed > 48h : BILAN final + STOP
- Si > 200 commits session : STOP (qualité > quantité)
- Si tests rouges > 3 consécutives : STOP + diagnostic

## ★ ARCHITECTURE TECHNIQUE ★

```
DOCTRINE_48H_NONSTOP.md (this file)
   │
   └── v9_autonomous_loop.py        # Moteur principal
        ├── v9_auto_plan.py         # Génération prochaine phase
        ├── v9_phase_tracker.py     # State persistence
        ├── v9_auto_commit.py       # Git ops
        ├── v9_docs_sync.py         # Coherence docs
        └── v9_cron_perpetual.sh    # Cron 24/7
```

### Boucle principale

```python
def autonomous_loop():
    while state.elapsed_hours < 48:
        next_phase = planner.next()
        if not next_phase:
            next_phase = planner.generate_emergent()
        executor.run(next_phase)
        if not verify_tests():
            repair()
        docs_sync.update()
        git_ops.commit_push()
        state.update()
        # Pas de sleep - continue
```

## ★ MÉTRIQUES D'ÉLIGIBILITÉ ★

Pour qu'une phase soit **qualifiée production-grade** :
- ✅ Tests verts (≥ 1 par fonction publique)
- ✅ Docstring PEP257
- ✅ CLI avec `--help` et `--dry-run`
- ✅ Idempotent (peut être run 2x sans bug)
- ✅ Logging structure
- ✅ Error handling graceful
- ✅ Update INDEX_MODULES.md
- ✅ Commit + push inline

## ★ SÉQUENCE D'EXÉCUTION 48H ★

### Boucle 1 (heures 0-12) — Production-grade
- Phase 62 : Pipeline orchestrator
- Phase 63 : FTMO compliance
- Phase 64 : Real money preflight
- Phase 65 : Smart order router
- Phase 66 : Live metrics dashboard

### Boucle 2 (heures 12-24) — Intelligence
- Phase 67 : ML forecaster
- Phase 68 : Performance persistence
- Phase 69 : Cross-pair correlation live
- Phase 70 : Chaos engineering advanced
- Phase 71 : Adversarial testing

### Boucle 3 (heures 24-36) — Robustesse
- Phase 72 : E2E pipeline test live
- Phase 73 : Docs coherence auto-sync
- Phase 74 : User guide enrichi
- Phase 75 : Auto-pr + merge + bilan

### Boucle 4 (heures 36-48) — Polish
- Phase 76 : Advanced backtest
- Phase 77 : Risk parity
- Phase 78 : Drawdown protector
- Phase 79 : Final bilan 48h
- Phase 80 : Auto-pr + tag release

## ★ INVOCATION ★

```bash
# Démarrage manuel
python scripts/v9_autonomous_loop.py --max-hours 48

# Démarrage via cron perpétuel
bash scripts/v9_cron_perpetual.sh start

# Voir avancement
python scripts/v9_phase_tracker.py --status
```

## ★ FIN ★

Philosophie : **le système est un travailleur, pas un consultant**.

- Le consultant demande : "Quoi faire ?"
- Le travailleur exécute : la prochaine tâche.

PowerFlow V9 est un **travailleur**.

🚀 **Doctrine 48H NON-STOP ACTIVE.**