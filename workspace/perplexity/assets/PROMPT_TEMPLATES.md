# PROMPT_TEMPLATES — gabarits de brief

Gabarits prêts à copier pour cadrer un échange avec Claude Code ou tout autre provider
d'implémentation, en cohérence avec `docs/PERPLEXITY.md` §« Interface avec les autres
intervenants » : toute implémentation structurante doit s'ancrer explicitement dans un
document de doctrine existant.

## Brief d'implémentation structurante

```
Contexte : PowerFlow V9, branche feat/v9-foundation-clean.
Ancrage doctrine : [référence explicite à docs/DOCTRINE.md / docs/doctrine/*.md /
  docs/ARCHITECTURE.md justifiant ce travail]
Phase concernée : [numéro de phase ou "hors phase, correctif"]
Objectif : [une phrase]
Contraintes :
- ne pas modifier [périmètre à exclure explicitement]
- ne pas ouvrir [chantier gelé à rappeler si pertinent, ex. Phase 10]
- mettre à jour docs/STATE.md et docs/DOC_REGISTRY.yml si nécessaire
Documents à lire avant de commencer : [liste précise, pas "lire toute la doc"]
Definition of done : tests verts, doc à jour, commit propre si cohérent.
```

## Brief de correctif / bugfix

```
Symptôme observé : [fait constaté, pas une supposition]
Où : [fichier/module/commit]
Hypothèse de cause : [si connue, sinon "à investiguer"]
Contrainte : root cause, pas de contournement (pas de --no-verify, pas de shim
  permanent sans justification doctrine)
Documenter dans : workspace/perplexity/INCIDENTS.md après résolution
```

## Brief de synthèse/reprise (pour Perplexity ou tout provider de continuité)

```
Rôle : synthèse et continuité, pas d'implémentation.
Lire dans l'ordre : voir REPRISE_TEMPLATE.md.
Produire : [ex. mise à jour BOARD.md / mini-checkpoint / arbitrage doctrine]
Ne pas : coder, trancher une divergence doc/code sans investigation, ouvrir un
  chantier gelé.
```

## Règle commune à tous les gabarits
Ne jamais commencer un brief par une reformulation de mémoire de conversation sans
l'avoir vérifiée contre `docs/STATE.md`/`git log`. Toujours citer la référence
documentaire précise plutôt qu'un renvoi vague à « la doctrine ».
