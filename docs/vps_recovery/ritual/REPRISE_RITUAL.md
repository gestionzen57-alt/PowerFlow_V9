# Rituel de reprise — PowerFlow V9

> Exécuter dans l'ordre à chaque nouvelle session Hermes.
> Temps estimé : 3-5 minutes.

```bash
# ── 1. État du repo ──
echo "=== GIT LOG ==="
git log --oneline -10
echo ""
echo "=== GIT STATUS ==="
git status
echo ""

# ── 2. Docs fondateurs ──
echo "=== STATE.md (état courant) ==="
head -50 docs/STATE.md
echo ""
echo "=== DOCTRINE.md (règles) ==="
head -80 docs/DOCTRINE.md
echo ""

# ── 3. Décisions récentes ──
echo "=== DERNIÈRES DÉCISIONS ==="
tail -30 workspace/perplexity/memory/DECISIONS_LOG.md
echo ""

# ── 4. Tâches en cours ──
echo "=== TÂCHES ACTIVES ==="
cat workspace/perplexity/ACTIVE_TASKS.md 2>/dev/null || echo "(aucune)"
echo ""

# ── 5. Pipeline live ──
echo "=== PIPELINE LIVE ==="
python scripts/v9_ops.py status 2>/dev/null || echo "(serveur non démarré)"
echo ""

# ── 6. Tests ──
echo "=== TESTS ==="
python -m pytest tests/ -q --tb=no 2>/dev/null | tail -3
```

## Après le rituel

1. Tu sais où on en est (STATE.md)
2. Tu connais les règles (DOCTRINE.md)
3. Tu sais ce qui a été décidé récemment (DECISIONS_LOG.md)
4. Tu sais ce qu'il reste à faire (ACTIVE_TASKS.md)
5. Tu sais si le pipeline tourne (v9_ops.py status)
6. Tu sais si les tests passent (pytest)

## Si le pipeline est DOWN

```bash
python scripts/v9_ops.py boot
```

## Si les tests échouent

```bash
python -m pytest tests/ -v --tb=long 2>&1 | head -60
```
