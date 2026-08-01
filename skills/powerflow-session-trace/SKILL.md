---
name: powerflow-session-trace
category: productivity
description: "Pipeline complet session PowerFlow — trace + checkpoint + STATE + JOURNAL + push auto"
trigger: Fin de session PowerFlow V8 (fix, analyse, déploiement)
tools_needed: [write_file, read_file, execute_code, terminal, skill_manage]
statut: actif-v9
derniere_maj: 2026-07-31
version: 0.0.1
---
## 🎯 OBJECTIF

Clôturer une session PowerFlow V8 avec trace complète : checkpoint, docs mis à jour, commit + push auto.

## 📋 RITUEL DE CLÔTURE (5 ÉTAPES)

### Étape 1 : Rapport détaillé (mini 10 lignes)

```markdown
## SESSION <NOM> — <DATE>

**Auteur :** <agent> (<modèle>)  
**Durée :** <start> → <end>  
**Fichiers modifiés :** <N> fichiers  
**Lignes modifiées :** +<N> / -<N>

### Problème traité
<Description du problème en 2-3 lignes>

### Root cause
<Cause racine identifiée>

### Solution appliquée
<Actions correctives détaillées>

### Validation
- [ ] Tests passants
- [ ] Logs vérifiés
- [ ] Gateway redémarré si nécessaire
- [ ] WR partiel > 60% (si applicable)
```

### Étape 2 : Checkpoint `docs/checkpoints/`

```bash
# Nom du fichier : CHECKPOINT_YYYY_MM_DD_<slug>.md
# Exemple : CHECKPOINT_2026_06_22_PATCH_P0.md

# Front-matter obligatoire :
---
title: "<Titre court>"
date: YYYY-MM-DD
tags: [fix, analysis, deployment, ...]
statut: VALIDE
checkpoint_type: FIX_CRITICAL | ANALYSIS | DEPLOYMENT
severity: P0 | P1 | P2
---
```

### Étape 3 : MAJ `docs/STATE.md`

```bash
# Ligne à patcher : "**Dernière mise à jour :**"
# Format : 2026-06-22 23:50 UTC — <nom session> (<résumé>)

# Section "État système" à refresh :
# - Gateway status
# - pf_analyst status
# - analyst_memory.db status
# - live_pipeline status
```

### Étape 4 : MAJ `docs/JOURNAL.md`

```bash
# Ajouter entrée en TOP du fichier (après front-matter)
# Format :

## YYYY-MM-DD — SESSION <NOM> (<slug>)

**Auteur :** <agent>  
**Tâches traitées :** <liste>  
**Décisions clés :**
- <décision 1>
- <décision 2>

**Artefacts :**
- Checkpoint: `docs/checkpoints/<nom>.md`
- Commits: `<sha1>`, `<sha2>`
- Skills créées: `<nom>`

**Enseignements :**
<1-3 insights à retenir>
```

### Étape 5 : MAJ `docs/index/INDEX_DOCS.md`

```bash
# Si nouveau checkpoint créé :
| <date> | <nom> | <type> | <lien> |

# Si doc créé/archivé :
| <nom> | <statut> | <date> | <lien> |
```

## 🚀 COMMIT + PUSH AUTO

```bash
# Script : scripts/aaa.py
# Usage : python scripts/aaa.py --name "<nom session>"

# Ce que le script fait :
# 1. git add docs/ + fichiers modifiés
# 2. git commit -m "chore(session): <nom session>"
# 3. git pull --rebase
# 4. git push
# 5. Affiche résumé + links
```

## 📁 ARBORESCENCE TYPE

```
D:\Projet\V8\
├── docs/
│   ├── STATE.md              # MAJ timestamp + état système
│   ├── JOURNAL.md            # Nouvelle entrée session
│   ├── INDEX_DOCS.md         # MAJ si nouveau doc/checkpoint
│   └── checkpoints/
│       └── CHECKPOINT_YYYY_MM_DD_<slug>.md  # NOUVEAU
├── core/
│   └── pf_analyst.py         # Si patch appliqué
├── federation/
│   └── agent_registry.py     # Si patch appliqué
└── scripts/
    └── bridge_watchdog.py    # Si nouveau script
```

## ✅ CHECKLIST FINALE

- [ ] Rapport détaillé écrit (mini 10 lignes)
- [ ] Checkpoint créé dans `docs/checkpoints/`
- [ ] `docs/STATE.md` mis à jour (timestamp + état)
- [ ] `docs/JOURNAL.md` mis à jour (nouvelle entrée)
- [ ] `docs/index/INDEX_DOCS.md` mis à jour (si besoin)
- [ ] Commit + push via `scripts/aaa.py`
- [ ] Skill créée si workflow réutilisable (optionnel)
- [ ] TODO list nettoyée

## ⚠️ PIÈGES CONNUS

1. **Oublier checkpoint** : Toujours créer le checkpoint AVANT commit
2. **Timestamps UTC** : Utiliser UTC partout (pas UTC+2 broker)
3. **Front-matter** : Checkpoint DOIT avoir YAML front-matter valide
4. **Ordre des MAJ** : Checkpoint → STATE → JOURNAL → INDEX → commit
5. **Cross-profile** : Ne PAS modifier profil `free4` depuis session `powerflow`

## 🔗 LIENS

- Template checkpoint: `docs/checkpoints/CHECKPOINT_2026_06_22_PATCH_P0.md`
- Script auto: `scripts/aaa.py`
- Doc gouvernance: `docs/DOC_GOVERNANCE.md`