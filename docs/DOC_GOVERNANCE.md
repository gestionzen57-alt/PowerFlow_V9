# DOC_GOVERNANCE — PowerFlow V9

## Règle absolue
**Le code est la source de vérité, pas la documentation.** Si un document et le code
divergent, c'est le document qui est présumé faux — sauf si l'investigation montre que le
code est un bug, auquel cas c'est le code qu'il faut corriger et documenter le correctif.
Ne jamais ajuster silencieusement l'un pour cacher une divergence avec l'autre.

## Règles de gouvernance

1. **Chaque PR touchant du code doit mettre à jour la doc concernée.** Un module nouveau
   ou modifié dans `core/v9/` implique une mise à jour d'au moins un de :
   [ARCHITECTURE.md](ARCHITECTURE.md), [architecture/DB_SCHEMA.md](architecture/DB_SCHEMA.md),
   la doc de phase (`docs/phases/PHASEn_*.md`), ou [STATE.md](STATE.md).
2. **[DOC_REGISTRY.yml](DOC_REGISTRY.yml) est la source de vérité pour l'état des documents**
   (chemin, type, statut, dernière mise à jour). Tout document créé doit y être ajouté.
   Tout document supprimé doit en être retiré.
3. **Un document sans mise à jour depuis 30 jours est marqué `STALE`** dans le registre
   (voir `tools/doc_sync.py --stale`). Un statut `STALE` n'est pas une faute en soi — un
   document stable peut rester correct longtemps — mais il doit être revérifié avant d'être
   cité comme source dans une nouvelle tâche.
4. **Les checkpoints sont obligatoires à la clôture de chaque phase.** Utiliser
   [docs/checkpoints/CHECKPOINT_TEMPLATE.md](checkpoints/CHECKPOINT_TEMPLATE.md).
5. **Le lexique doit être enrichi à chaque nouveau terme métier.** Ajouter la définition
   complète dans `docs/lexicon/LEXICON_V9.md`, puis la ligne d'index correspondante dans
   [LEXIQUE.md](LEXIQUE.md). Ne jamais introduire un terme métier dans le code sans
   l'ajouter au lexique dans la même PR.
6. **La nomenclature ([NOMENCLATURE.md](NOMENCLATURE.md)) doit être respectée dans tout
   nouveau code.** Si une convention doit être rompue pour une bonne raison, documenter
   l'écart explicitement dans NOMENCLATURE.md plutôt que de laisser la divergence implicite
   (voir par exemple la table `exploitability`, singulier assumé).
7. **Si doc et code divergent** et que la cause n'est pas triviale (pas juste un oubli de
   mise à jour), consigner l'écart dans le document concerné (section « Écart constaté »)
   et, si la divergence est structurante, ouvrir une issue GitHub.
8. **Pas de duplication de contenu détaillé entre document pivot et document source.** Les
   fichiers pivots à la racine de `docs/` ([DOCTRINE.md](DOCTRINE.md), [LEXIQUE.md](LEXIQUE.md))
   sont des index de synthèse qui renvoient vers les documents détaillés
   (`docs/doctrine/*.md`, `docs/lexicon/LEXICON_V9.md`). En cas de divergence entre un index
   et sa source, la source fait foi.
9. **Le code de la Phase 9 (ou de toute phase en cours sur une autre session) peut être lu
   pour documentation d'inventaire, jamais modifié depuis une autre session/branche.** Les
   documents qui le référencent doivent porter la mention explicite « en cours,
   non finalisé » tant que la phase n'est pas clôturée et son checkpoint écrit.

## Vérification automatisée

- `tools/doc_sync.py --check` : vérifie la cohérence doc/code (voir docstrings, registry, staleness)
- `tools/doc_sync.py --update` : régénère les champs `last_update` de [DOC_REGISTRY.yml](DOC_REGISTRY.yml) pour les fichiers modifiés
- `tools/doc_sync.py --stale` : liste les documents sans modification depuis 30 jours
- `.github/workflows/doc-freshness.yml` : exécute ces vérifications à chaque push sur
  `feat/v9-foundation-clean` et `main`, échoue si un fichier `.py` nouveau n'a pas de
  docstring de module ou si `DOC_REGISTRY.yml` ne référence pas un document existant

## Ce que cette gouvernance ne fait pas
Elle ne vérifie pas l'exactitude sémantique d'un document (un docstring peut être présent
et faux). La vérification de fond reste une responsabilité humaine/IA à chaque session,
via le rituel de lecture décrit dans [README.md](../README.md).
