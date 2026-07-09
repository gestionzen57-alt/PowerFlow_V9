# vps_recovery/ — Kit de reprise Hermes vierge sur VPS

> **Statut** : Généré le 2026-07-09, branche `feat/v9-foundation-clean`
> **Usage** : Un Hermes frais (nouvelle install, nouveau profil) arrive sur ce projet.
> Il lit ce dossier en premier, puis suit la procédure.

## Contenu

| Fichier | Rôle |
|---------|------|
| `NEW_HERMES_PROCEDURE.md` | **Procédure principale** — lire en premier |
| `ritual/` | Rituels de reprise, fermeture, diagnostic |
| `skills/` | Skills Hermes V9 essentielles (à importer dans le profil) |
| `checklist/` | Checklists opérationnelles |

## Principe

Ce dossier contient **tout ce qu'un Hermes vierge doit savoir** pour reprendre le projet
PowerFlow V9 sans connaissance préalable. Zéro legacy V8/V7. Zéro dépendance à la mémoire
de conversation. Tout est dans le Git.

## Rituel de reprise (résumé)

```
1. Lire ce README
2. Lire NEW_HERMES_PROCEDURE.md
3. Lire docs/STATE.md (état courant)
4. Lire docs/DOCTRINE.md (30 règles)
5. Lire docs/V9_FONCTIONNEMENT.md (mode d'emploi)
6. Lire workspace/perplexity/memory/DECISIONS_LOG.md (décisions récentes)
7. Lire workspace/perplexity/ACTIVE_TASKS.md (tâches en cours)
8. git log --oneline -10 && git status
9. python scripts/v9_ops.py status (état pipeline live)
```

## Liens rapides

- `docs/STATE.md` — état exécutif courant
- `docs/DOCTRINE.md` — 30 règles immuables
- `docs/V9_FONCTIONNEMENT.md` — mode d'emploi global
- `docs/ROADMAP.md` — phases restantes
- `docs/doctrine/CHARTE_COGNITIVE_V9.md` — charte fondatrice
- `docs/architecture/CHAINE_COGNITIVE.md` — détail 9 couches
- `docs/architecture/DB_SCHEMA.md` — schéma SQLite
- `docs/architecture/PIPELINE_LIVE.md` — flux EA → DB
- `docs/architecture/CONTEXT_CONTRACT.md` — contrat propagation
- `docs/architecture/GAPS_RESIDUELS.md` — écarts connus
- `docs/deployment/VPS_RUNBOOK.md` — runbook VPS
- `docs/deployment/V9_DEPLOYMENT_GUIDE.md` — déploiement EA MT4
