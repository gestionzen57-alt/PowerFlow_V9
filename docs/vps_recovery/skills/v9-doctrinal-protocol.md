# V9 Doctrinal Protocol — Incident & Extension

> Skill compact. Voir `v9-doctrinal-incident-and-extension-protocol` pour l'intégral.

## MODE D — Incident doctrinal

**Trigger** : Søn conteste la lecture pipeline (biais HTF-first, cascade-only, etc.)

**Workflow** :
1. Reformuler verbatim les constats Søn (≥3 phrases)
2. Pointer la tension avec DOCTRINE.md existante
3. Lister implications techniques (lecture seule, pas de code)
4. Poser 4 questions max (Q1-Q4 binaires/choix fermés)
5. Créer brouillon `workspace/perplexity/BRAINSTORM_<TOPIC>_<DATE>.md`
6. Logger dans DECISIONS_LOG.md
7. Livrer en 2 chantiers parallèles : (a) import doctrinal, (b) code extension

## MODE D-bis — Audit DOCTRINE vs CHARTE

**Trigger** : Søn conteste une règle précise de DOCTRINE.md

**Workflow** :
1. Relire CHARTE_COGNITIVE_V9.md (source de vérité)
2. Relire règle par règle DOCTRINE.md
3. Produire tableau : Règle | CHARTE § | Type (🔴contradiction/🟡tension) | Sévérité
4. 3 options par 🔴 : A (aligner) / B (maintenir+justifier) / C (supprimer)
5. NE PAS patcher sans validation Søn

## Extension périmètre + backups MD5

**Trigger** : Søn dit "fait un backup et continue"

```bash
# 1. Backup daté
mkdir -p workspace/perplexity/memory/backups_$(date +%Y%m%d)
cp core/v9/<file>.py workspace/perplexity/memory/backups_<DATE>/<file>.py.bak

# 2. Vérifier MD5
md5sum core/v9/<file>.py backups_<DATE>/<file>.py.bak

# 3. Ajouter au .gitignore
echo "workspace/perplexity/memory/backups_*/" >> .gitignore

# 4. Patcher + tester
python -m pytest tests/ -q

# 5. Si casse : revert MD5 immédiat
```

## MODE Y+X — Capture des enseignements Søn

**Trigger** : Søn veut capturer ses lectures sans contester la doctrine

**Différence avec MODE D** : Y+X = capture, pas contestation. 0 ouverture de chantier gelé.

**Workflow** :
1. Créer `workspace/perplexity/teachings/` (1 commit, 0 modif core/v9/)
2. Y = Søn écrit librement dans `brutes/<ts>_<topic>.md`
3. X = Quand motif émerge 3×, formulaire guidé 8 champs
4. Hermes propose YAML/PR (1 par enseignement, jamais d'auto-merge)
5. Søn valide ou refuse

## Règles absolues

- ❌ JAMAIS inventer un seuil absent de la lecture Søn (R25')
- ❌ JAMAIS toucher `principles/*.yaml` sans validation explicite
- ❌ JAMAIS merger une proposition X sans PR review Søn
- ✅ Les fichiers bruts Y sont immuables
- ✅ La promotion X → PR = 1 lecture = 1 PR
