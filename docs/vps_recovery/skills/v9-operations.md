# V9 Operations — Rituel démarrage & conventions

> Skill compact pour reprise Hermes vierge. Voir skill original `powerflow-v9-operations` pour le contenu intégral.

## Rituel de reprise (obligatoire)

1. `git log --oneline -10 && git status`
2. Lire `docs/STATE.md` (état courant)
3. Lire `docs/DOCTRINE.md` (30 règles)
4. Lire `docs/V9_FONCTIONNEMENT.md` (mode d'emploi)
5. `tail -30 workspace/perplexity/memory/DECISIONS_LOG.md`
6. `cat workspace/perplexity/ACTIVE_TASKS.md`
7. `python scripts/v9_ops.py status`

## Conventions

- **R14** : Git = vérité. Doc présumé faux si divergence.
- **R22** : 1 livraison = 1 commit. Pas de batch multi-sujets.
- **R25'** : Pas d'invention de seuil chiffré.
- **R28** : Hermes = unique opérateur git. Søn ne tape pas de git.
- **R6** : STOP à 3 échecs sur même fichier.
- **Modules gelés** : `config.py`, `orchestrator.py`, `principles/*.yaml`
- **DB** : `data/v9_forces.db` (principale)
- **Logs** : `logs/v9_*.log`

## Point d'entrée unique

```bash
python scripts/v9_ops.py <commande>
# start, stop, status, boot, dashboard, watch, signals, decisions,
# calibrate, principles, stats, health, log, validate-ea
```

## Pièges fréquents

- ❌ Confondre "pipeline actif" (serveur écoute) avec "flux live" (EA connecté)
- ❌ Utiliser `deploy_v9.py` directement au lieu de `v9_ops.py`
- ❌ mem0 est DÉSACTIVÉ depuis 2026-07-07
- ❌ Ouvrir Phase 10/11/12/13 sans décision Søn
- ❌ Inventer un seuil non documenté dans DOCTRINE.md
