# Diagnostic resolver WIN/LOSS — 2026-07-08

## Constat de départ

L'énoncé de tâche mentionnait un cron 5min pour
`scripts/v9_resolve_decision_auto.py` et 8321 décisions `preparer_entree`
« en attente ». Vérification faite : **cette prémisse était obsolète.**

## Ce qui a été vérifié

- **Aucune tâche planifiée Windows** ne référence
  `v9_resolve_decision_auto.py` ou `v9_resolve_decision_auto_daemon.py`
  (`Get-ScheduledTask` — seules tâches V9 présentes :
  `V9_DailyReport`, `V9_HeartbeatAlert`, `V9_HeartbeatCheck`,
  `V9_TelegramNotifier`). La seule tâche « resolver » du système
  (`PowerFlow_C6A_SequenceResolver`) est un legacy **V8**, **Disabled**,
  912 exécutions manquées.
- La distribution de `resolved_at` (arrondi à la minute) ne montre que
  **2 timestamps distincts** : `2026-07-08T12:28` (47 décisions) et
  `2026-07-08T12:38` (8323 décisions). Ce sont deux runs manuels
  ponctuels (`--apply`), pas un cron continu.
- Le nombre 8321 de l'énoncé correspond en fait au **compte de WIN**
  du premier run manuel (8321 wins / 8370 résolues à ce moment-là), pas
  à des décisions en attente.
- Sur les 53 décisions `preparer_entree` encore non résolues à l'ouverture
  de ce chantier, un `--dry-run` a montré qu'elles étaient **toutes
  résolubles immédiatement** (prix futurs disponibles, aucun skip).
  Elles ont été résolues via `--apply` (backup MD5 vérifié) :
  **44 wins / 9 losses (83.0%), +11.6 pips moyens**.
- **100% des décisions `preparer_entree` sont désormais résolues**
  (8423/8423, contre 8370/8423 en début de chantier).

## Conclusion

Le script `v9_resolve_decision_auto.py` fonctionne correctement — la
logique de résolution (`_fetch_unresolved`, `resolve_one`,
`apply_resolutions`) n'a nécessité aucune correction. Le seul problème
réel est **l'absence d'automatisation** : le resolver doit être
déclenché manuellement, il n'y a pas de cron/tâche planifiée qui le
fait tourner en continu.

## Recommandation (hors périmètre de ce chantier)

Créer une tâche planifiée Windows (`schtasks`) pointant vers
`scripts/v9_resolve_decision_auto.py --apply --backup <dir>` toutes les
5 minutes, sur le modèle de `V9_HeartbeatCheck`. Non fait ici car cela
dépasse le périmètre « vérifier le resolver » de ce chantier et
nécessite une décision explicite sur la stratégie de backup MD5
récurrente (un backup DB de 3.8 GB à chaque cycle de 5 min n'est pas
soutenable — probablement besoin d'un backup allégé ou d'un
`--skip-backup` assumé pour les runs automatiques).
