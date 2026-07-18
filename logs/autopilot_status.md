# Status V9 — 2026-07-17 11:50 UTC (Hermes — surveillance post-activation DRM)

## TL;DR

- **6 paires live** : AUDUSD frais (351 snapshots, 0.9 min), 5 autres <1 min aussi ✅
- **Serveur** : PID 1764 actif, port 31685 LISTENING ✅
- **Tests** : 1556 verts / 1 skipped / 0 fail ✅
- **Crons** : 12 Ready + V9CaptureWatchdog Running ✅
- **LOCK + RESPIRATION ACTIVE** : 191 / 191 décls sur 24h ✅
- **🔴 Anomalie bloquante** : `V9_DYNAMIC_RISK_ENABLED=1` mais aucun câblage
  APPLY dans `core/v9/trade_engine.py` → SL/TP restent à 8/15 statique sur les
  décisions récentes. Ce n'est pas une régression, c'est un hiatus motion/code.
  Détail + ci-dessous.

## Anomalie bloquante — DRM en APPLY fantôme

### Constat factuel

| Signal mesuré | Valeur |
|---|---|
| `V9_DYNAMIC_RISK_ENABLED` dans `config/v9_kill_switches.env` | `1` ✅ |
| `signals.tp_pips_recommended` sur 15 dernières décisions `preparer_entree` | **toutes = 8.0** |
| `signals.sl_pips_recommended` sur 15 dernières décisions | **toutes = 15.0** |
| Stratégie sur 15 dernières décisions | `DYNAMIC` (= profil session, **pas** DRM) |
| Présence de `dynamic_risk` dans `contexte_complet_json` | **0 / 5** décisions récentes |
| `RR statique réalisé` (dashboard risk) | 0.53 (le RR « dynamique 1.63 » reste planifié / calculé par le module, jamais appliqué) |

### Cause

Commit `c6afebb feat(v9): activation DynamicRiskManager — motion CEO Søn 2026-07-17`
(créé par Søn le 17/07 à 12:03) modifie **uniquement** `config/v9_kill_switches.env`
et **uniquement** la ligne `V9_DYNAMIC_RISK_ENABLED=1`. Le commit-message dit
explicitement « cycles/phases SL/TP adaptatifs **en APPLY** », mais le code n'a
pas de chemin APPLY câblé :

- `core/v9/trade_engine.py:63-69` documente explicitement : « Kill switch du
  DynamicRiskManager (Phase 13.3). Défaut ON **en mode SHADOW** : le module
  ÉVALUE la gestion de risque adaptative et attache le résultat au diagnostic
  (`result["dynamic_risk"]`), mais n'APPLIQUE rien — le SL/TP réellement utilisé
  reste celui calculé par la chaîne existante. L'activation (mode APPLY) est
  une décision CEO, **non câblée ici** ».
- `grep "dynamic_risk_manager.evaluate\|dynamic_risk_manager.compute\|result\[\"dynamic_risk\"\]" core/v9/trade_engine.py`
  retourne 0 occurrence. Le singleton `dynamic_risk_manager` est créé (ligne 151-156)
  mais jamais appelé par `TradeEngine.process()`.
- `signals.tp_pips_recommended`/`sl_pips_recommended` continuent à être peuplés
  par `signal_generator` via les profils `DYNAMIC_PROFILES` (par session) et non
  par `DynamicRiskManager`.

### Interprétation (au choix de Søn)

- **Hypothèse A — Motion CEO correcte, code à compléter** : Søn a voulu APPLY.
  Il faut câbler le chemin APPLY (probablement ~50 LOC dans `TradeEngine.process()`
  + tests). Effort estimé ~2h, chantier dédié distinct avec backup R8.
- **Hypothèse B — Motion CEO imprécise, état actuel conforme** : Søn a voulu
  « activer l'évaluation SHADOW » (= ce que le code fait déjà). Le commit
  `c6afebb` est alors un no-op effectif (`.env` ON alors qu'il l'était déjà,
  check `git diff c6afebb~1 c6afebb -- config/v9_kill_switches.env`).
- **Hypothèse C — Phase APPLY code manquant** : le code APPLY a été oublié
  dans le commit `e91838b` (qui n'a livré que le SHADOW) et le commit
  `c6afebb` a transposé l'env=1 sans patcher le wiring.

### Constat empirique : aucune régression

Les décisions restent cohérentes avec le pipeline pré-DRM (TP=8 / SL=15 / RR=0.53).
Pas de crash, pas de décision aberrante, pas d'effet de bord. Si l'hypothèse A est
la bonne, il n'y a **rien à défaire** côté risque — juste à câbler l'APPLY en
plus. Si l'hypothèse B, rien du tout.

## Surveillance LOCK + RESPIRATION (P1)

| Principe | Évaluations 24h | Triggers | Taux |
|---|---|---|---|
| GRAMMAR_LOCK | 2297 | 191 | 8.3 % |
| GRAMMAR_RESPIRATION | 2297 | 191 | 8.3 % |

Déclenchements = 191 / 191 (mêmes snapshots → ils sont corrélés par construction).
Aucun signal STALE ou NULL après promotion (au sens « ACTIVE a rejoint l'évaluation
standard »). Le pipeline les utilise.

## Dashboard risque (P2)

```
6 paires / Total : 8688 trades  profit cumulé : +46711.2 pips
GBPUSD 8555 | WR 85.3% | RR 0.89 | esp +5.47 (n=8555)
EURUSD   34 | WR 47.1% | RR 0.84 | esp -1.14
USDCHF   33 | WR 66.7% | RR 1.09 | esp +3.06
USDJPY   33 | WR 54.5% | RR 0.55 | esp -2.41
USDCAD   18 | WR 16.7% | RR 1.50 | esp -3.04
AUDUSD   15 | WR 26.7% | RR 0.47 | esp -0.93
```

⚠ AUDUSD à 26.7 % WR / RR 0.47 → esp −0.93 sur 15 trades : petit sample (1 jour
de live post-add AUDUSD). GBPUSD écrase toujours la moyenne (87 % de l'effectif).
USDCAD à 16.7 % reste préoccupant mais n=18.

## Weekend (P3)

- Tous crons Ready + watchdog Running.
- Marché ferme **vendredi 21h UTC, rouvre dimanche 22h UTC**.
- **MT4 = seul vrai risque** (pas de relance auto GUI).
- Vérif manuelle MT4 dimanche 22h UTC obligatoire.

## Garde-fous respectés

- `core/v9/*` non touché.
- Aucun `restart` capture_server.
- Aucune activation/désactivation de kill switch (j'ai lu le `.env`, je n'y
  touche pas).

## Action attendue de Søn

1. **Confirmer l'intention** : APPLY complet (hypothèse A) ou rester en SHADOW
   (hypothèse B) ? Le code ne fait que B actuellement.
2. Si A : chantier dédié (câblage APPLY + tests + backup R8), prochaine session.
3. Sinon, push du commit `2b67eda` toujours en attente (R28 par défaut = CEO).
