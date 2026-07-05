# CHECKPOINT_TEMPLATE (workspace) — renvoi + variante mini-checkpoint

## Checkpoint de phase complet
Pour tout checkpoint de clôture de phase (obligatoire, voir `docs/DOC_GOVERNANCE.md`
règle 4), utiliser le gabarit canonique et le déposer dans `docs/checkpoints/` :
**`docs/checkpoints/CHECKPOINT_TEMPLATE.md`**. Ne pas dupliquer son contenu ici — ce
fichier ne fait qu'y renvoyer et couvre un cas distinct ci-dessous.

## Mini-checkpoint (usage workspace uniquement)
Un mini-checkpoint est plus léger qu'un checkpoint de phase : il sert à documenter une
observation ponctuelle (ex. post-ouverture de marché, cf. `MARKET_OPEN_TEMPLATE.md`)
sans clôturer de phase. Il reste dans `workspace/perplexity/` (jamais dans
`docs/checkpoints/`, qui est réservé aux checkpoints de phase officiels) et n'a pas
besoin d'entrée dans `docs/DOC_REGISTRY.yml`.

```
## Mini-checkpoint — {YYYY-MM-DD HH:MM}
### Contexte
Une phrase : quelle observation, à quel moment (T-30/T0/T+15/T+60 si market open).

### Observé
Faits bruts (dashboard, logs, DB) — pas d'interprétation.

### Écart vs attendu
Ce qui diverge de ce que STATE.md/ROADMAP.md laissait attendre, s'il y a lieu.

### Action immédiate
Rien, ou action ponctuelle non structurante. Toute action structurante doit remonter
vers un vrai checkpoint de phase (docs/checkpoints/) et docs/STATE.md.

### Suite
Où consigner la suite : ACTIVE_TASKS.md, INCIDENTS.md si anomalie, ou
memory/DECISIONS_LOG.md si décision structurante.
```

## Règle de bascule
Si un mini-checkpoint révèle une décision structurante ou un correctif de fond, il ne
reste pas dans le workspace : il déclenche un vrai checkpoint de phase
(`docs/checkpoints/CHECKPOINT_TEMPLATE.md`) et une mise à jour de `docs/STATE.md`.
