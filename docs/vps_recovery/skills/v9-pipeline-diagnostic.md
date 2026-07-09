# V9 Pipeline Diagnostic — Multi-goulet

> Skill compact. Voir `powerflow-v9-pipeline-bottleneck-diagnostic` pour l'intégral.

## Méthode en 3 étapes

### Étape 1 — Volume DB

```sql
SELECT COUNT(*) FROM forces_snapshots;
SELECT COUNT(*) FROM scenes;
SELECT COUNT(*) FROM behaviors;
SELECT COUNT(*) FROM windows;
SELECT COUNT(*) FROM exploitability;
SELECT COUNT(*) FROM principle_evaluations;
SELECT COUNT(*) FROM signals;
SELECT COUNT(*) FROM decisions;
```

### Étape 2 — Tracer `raison_absence`

```sql
SELECT substr(raison_absence, 1, instr(raison_absence, ':')-1) AS cat,
       COUNT(*) FROM signals
WHERE raison_absence IS NOT NULL
GROUP BY cat ORDER BY COUNT(*) DESC;
```

### Étape 3 — Fix chirurgical (1 paramètre à la fois)

## Patterns de fix

| Pattern | Symptôme | Fix |
|---------|----------|-----|
| 1. Filtre config trop strict | 100% `regime_inadequat:X` | Retirer X de REGIMES_INADEQUATS |
| 2. Window=absente → non_exploitable | 100% `exploitabilite_non_exploitable` | Exception dans `_determine_status` |
| 3. Principes non chargés | `principes_source_json = '[]'` | Charger triggered AVANT build signal |
| 4. Re-evaluation DB figée | Pipeline utilise exploitability figée | Re-eval in-memory dans generate() |
| 5. Tri par pertinence vs récence | Signal directionnel mais décision neutre | ORDER BY pertinence DESC dans _load_signal |

## Piège critique — `_load_shared_context` retourne dict enveloppant

```python
shared = engine._load_shared_context(conn, snap_id)
ctx = shared["context"]  # ← les vrais champs sont ici, pas dans shared
```

## Piège critique — Fallbacks écrasent propagation

Les fallbacks placés APRÈS `context.update(cross_tf_context)` écrasent silencieusement les valeurs propagées. Initialiser les fallbacks AVANT la propagation.

## Piège critique — INERT_MARKET (3e verdict)

Un principe inerte a 3 causes : BUG_CODE, BUG_YAML, INERT_MARKET.
INERT_MARKET = code OK + YAML OK + marché ne fournit pas le régime.
NE PAS patcher — réévaluer après changement de régime.
