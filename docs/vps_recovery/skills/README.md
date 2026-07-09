# Skills V9 — Kit de reprise Hermes vierge

> **Usage** : Copier ces fichiers dans `~/.hermes/profiles/<profil>/skills/` pour
> reconstituer les skills V9 essentielles sur un Hermes frais.
>
> Ces skills sont des **références compactes** (pas les SKILL.md complets).
> Pour le contenu intégral, voir les skills dans le profil powerflow original
> ou les fichiers `references/` liés.

## Skills incluses

| Fichier | Skill original | Rôle |
|---------|---------------|------|
| `v9-operations.md` | `powerflow-v9-operations` | Rituel démarrage, conventions, workflow |
| `v9-consolidation.md` | `powerflow-v9-consolidation` | Playbook consolidation anti-V8 |
| `v9-zone-detector.md` | `powerflow-v9-zone-detector` | ZoneDetector, zone_diagnostics |
| `v9-pipeline-diagnostic.md` | `powerflow-v9-pipeline-bottleneck-diagnostic` | Diagnostic multi-goulet pipeline |
| `v9-principle-context.md` | `powerflow-v9-principle-context-enrichment` | Enrichissement contexte principes |
| `v9-infra-optimization.md` | `powerflow-v9-infra-optimization` | Framework OPT-N optimisation |
| `v9-live-ops.md` | `powerflow-v9-live-ops` | Opérations live V9 |
| `v9-doctrinal-protocol.md` | `v9-doctrinal-incident-and-extension-protocol` | Incident doctrinal, backups MD5 |

## Installation

```bash
# Depuis la racine du projet V9
cp docs/vps_recovery/skills/*.md ~/.hermes/profiles/<profil>/skills/powerflow/
```

Ou un par un via Hermes :
```
skill_manage(action='create', name='powerflow-v9-operations', content=$(cat docs/vps_recovery/skills/v9-operations.md))
```
