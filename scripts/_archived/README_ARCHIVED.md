# scripts/_archived/ — Zone d'archivage PowerFlow V10

> Audit senior du 2026-08-08 — Nettoyage Sprint 24

## Fichiers archivés

| Fichier | Raison | Remplacé par |
|---|---|---|
| `v10_resolve_outcomes_native.py` | Doublon fusionné | `v10_resolve_outcomes.py --mode native` |
| `v10_behavior_resolve_outcomes.py` | Doublon fusionné | `v10_resolve_outcomes.py --mode behavior` |
| `v10_night_cron_LEGACY.sh` | Double-cron dangereux | `v10_night_cron_s24.sh` |
| `v10_currency_behavior_demo.py` | Zone morte (non branché) | — |
| `v10_currency_strength_demo.py` | Zone morte (non branché) | — |
| `v10_strategy_demo.py` | Zone morte (non branché) | — |
| `v10_vsa_demo.py` | Zone morte (non branché) | — |

## Règle d'archivage

Un fichier archivé ici :
- Ne doit **jamais** être exécuté directement
- Contient un `raise DeprecationWarning` pour prévenir toute exécution accidentelle
- Est conservé à des fins d'historique uniquement
- Peut être supprimé définitivement à la promotion S25 → LIVE
