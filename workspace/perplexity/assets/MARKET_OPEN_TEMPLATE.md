# MARKET_OPEN_TEMPLATE — checklist d'ouverture marché

Ouverture de référence : **dimanche 23h Paris / 22h UTC** (voir
`docs/deployment/V9_DEPLOYMENT_GUIDE.md` pour la procédure complète de déploiement —
ce gabarit n'en est que la checklist d'observation temporelle, ne pas dupliquer la
procédure ici).

## Pré-requis avant T-30
- EA compilés avec `ServerPort=31690` (voir `ea/V9_Sonde_README.md`).
- `scripts/deploy_v9.py --check` passé sans erreur bloquante.

## T-30 (22h30 UTC / 23h30 Paris... à ajuster si l'heure de référence change)
- [ ] `scripts/deploy_v9.py --check` (Python, imports `core/v9/`, DB + 5 tables, port
      disponible).
- [ ] Vérifier qu'aucun process `capture_server` stale n'occupe déjà le port (voir
      `../INCIDENTS.md` — incident déjà rencontré).
- [ ] `scripts/deploy_v9.py --start`.
- [ ] `scripts/v9_dashboard.py --once` pour un premier statut à froid.

## T0 (ouverture)
- [ ] Confirmer réception des premiers snapshots EA (`scripts/validate_ea_output.py`).
- [ ] `scripts/v9_dashboard.py` en observation continue (pas de `--watch` spécifique
      encore, juste le tableau de forces).
- [ ] Vérifier cohérence timestamp UTC déclaré vs `capture_time` broker reconverti
      (détecte un `BrokerUTCOffsetHours` incorrect).
- [ ] Vérifier plausibilité AUD (doit rester entre EUR et NZD ± 15 unités — signale une
      inversion de buffer SDI potentielle).

## T+15
- [ ] `scripts/v9_dashboard.py --watch comportements` — premiers comportements qualifiés
      apparus ?
- [ ] `scripts/live_integration_test.py` si pas encore lancé — chaîne complète Scènes →
      Comportements → Fenêtres → Exploitabilité sur DB de test dédiée, lecture seule sur
      la prod.
- [ ] Noter tout écart de latence vs la cible de 200ms/couche (référence Phase 9 :
      189,58ms/snapshot en moyenne, 8 couches, sur données rejouées).

## T+60
- [ ] `scripts/v9_dashboard.py --watch signals` / `--watch decisions` — premiers
      signaux/décisions générés par la chaîne étendue (Régime/Principes/Signal/Décision).
- [ ] Vérifier la fréquence de dégradation gracieuse liée à `zone_diagnostics` non
      alimentée (9/27 principes concernés — attendu, pas une anomalie).
- [ ] Premier passage `scripts/v9_calibration.py --stats` pour un état des lieux brut.
- [ ] Rédiger le mini-checkpoint post-open (voir gabarit ci-dessous).

## Format du mini-checkpoint post-open
Utiliser le gabarit générique de `CHECKPOINT_TEMPLATE.md` §« Mini-checkpoint », rempli
a minima pour chacun des horizons T-30/T0/T+15/T+60 observés :

```
## Mini-checkpoint — {date} — Market open
### T-30
Observé : ...
### T0
Observé : ...
### T+15
Observé : ...
### T+60
Observé : ...

### Écarts vs attendu
...

### Anomalies à consigner dans INCIDENTS.md
...

### Décisions structurantes déclenchées (si applicable → memory/DECISIONS_LOG.md et
checkpoint de phase officiel dans docs/checkpoints/)
...

### Suite immédiate
...
```

## Rappel de portée
Aucune action ici ne doit engager de logique d'exécution d'ordre (interdit fondateur
avant Phase 12) ni ouvrir la Phase 10. Ce test live sert uniquement à observer et
calibrer les seuils existants (`scripts/v9_calibration.py --analyze`/`--principes`).
