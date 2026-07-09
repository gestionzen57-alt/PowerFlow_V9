# Rituel de fermeture de session — PowerFlow V9

> Exécuter avant de quitter une session.
> Règle 22 : une session = un périmètre = une livraison complète.

```bash
# ── 1. Tests ──
echo "=== TESTS ==="
python -m pytest tests/ -q --tb=no
echo ""

# ── 2. Git status ──
echo "=== GIT STATUS ==="
git status
echo ""

# ── 3. Commits ──
echo "=== DERNIERS COMMITS ==="
git log --oneline -5
echo ""

# ── 4. Vérification checklist ──
```

## Checklist de fermeture

- [ ] Tous les tests passent (0 régression)
- [ ] `docs/STATE.md` mis à jour
- [ ] `workspace/perplexity/memory/DECISIONS_LOG.md` — 1 entrée par décision structurante
- [ ] `workspace/perplexity/ACTIVE_TASKS.md` — tâches restantes listées
- [ ] `workspace/perplexity/JOURNAL.md` — delta opérationnel (max 5 lignes)
- [ ] `workspace/perplexity/exchange.md` — message de handoff si nécessaire
- [ ] Commits atomiques (1 par unité logique)
- [ ] `git push origin feat/v9-foundation-clean`
- [ ] Aucun chantier ouvert non livré (R22)
- [ ] Pipeline live vérifié (`python scripts/v9_ops.py status`)

## Si un chantier est incomplet

Ne pas fermer la session. Soit :
- **Terminer le chantier** dans la même session (R22)
- **Découper** en unité livrable autonome et livrer ce qui est fait
- **Annuler** proprement (revert + DECISIONS_LOG)

## Message de handoff (si relais à un autre agent)

Écrire dans `workspace/perplexity/exchange.md` :
```
## Handoff — YYYY-MM-DD HH:MM

État : [ce qui a été fait]
Reste : [ce qui reste à faire]
Pièges : [ce qu'il faut savoir]
Prochaine action : [la première chose à faire]
```
