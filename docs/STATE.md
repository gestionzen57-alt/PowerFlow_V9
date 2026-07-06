# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-06 14h30 CEST — Calibration live + Tuning YAML (343 tests, ANTAGONIST_NODE bug ouvert)

## Session Calibration Live + Tuning YAML (2026-07-06)

Session livrée sur `feat/v9-foundation-clean` (3 commits + push).
**343 tests verts** (339 baseline + 4 nouveaux test_context_propagation).

### Préliminaires — correction régression test_context_propagation
Commit [`046b285`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/046b2853260bc726485c974d663fb211cddf1f38) :
- 3 bugs corrigés dans la fixture `db_with_chain` (init_db manquant, INSERT schéma invalide, WAL Windows)
- `_load_shared_context` : fallbacks étendus à TOUS les champs de EXPECTED_CONTEXT_FIELDS
  (avant : seuls les 13 champs Tâche C/Anomalies étaient initialisés avant le bloc `if scene_row`)
- 4 nouveaux tests `test_context_propagation.py` — 343 tests verts

### Mission 1 — Calibration live
**Marché OUVERT** — session overlap_london_ny au moment de la calibration.
- **2245 snapshots** capturés depuis l'ouverture (hier soir 23h Paris)
- **1708 scènes** générées
- **0 signaux / 0 décisions** — comportements produits mais aucun ne déclenche
- Comportements fréquents : rotation_leadership=831, annulation=264, bascule=185

**Suggestions scanner vs décision :**
| Seuil | Actuel | Suggéré | Décision |
|---|---|---|---|
| COALITION_THRESHOLD | 5.0 | 3.96 (-20.8%) | ❌ reporté — attendre n>5000 scènes + WIN/LOSS |
| ANTAGONISM_THRESHOLD | 31.39 | 31.33 (-0.2%) | ❌ marge d'erreur, non appliqué |
| PLIURE_THRESHOLD | 1.7 | 1.68 (-1%) | ❌ marge d'erreur, non appliqué |
| STALE_THRESHOLDS_MS | — | 9-10x actuels | ❌ bug script, ignoré |

`config.py` inchangé. Seuils validés sur sessions 2026-06/07 conservés.

**Hit rates principes ACTIVE observés (paper-trading, 1708 scènes) :**
- PRICE_LAG_AT_NODE_BIRTH : 4.5%
- NODE_BIRTH_FAST : 3.4%
- POWER_ANGLE_BREAK_TO_PRICE_IMPACT : 3.0%
- COALITION_NODE : 2.7%
- Autres ACTIVE : 0%-2%
- **ANTAGONIST_NODE : 0/1728 — anomalie structurelle** (voir bug ouvert ci-dessous)

### Mission 2 — Tuning principes YAML
Commit [`35939aa`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/35939aacb7a9819883f45c3272585bd4c303e554) :
8 fichiers YAML enrichis pour exploiter les 13 nouveaux champs du contexte :

**4 NODE_RULE ACTIVE — conditions filtrantes ajoutées :**
- `COALITION_NODE` : +coalition_mtf_score>=3, +risk_sentiment not_in [MIXTE]
- `NODE_BIRTH_FAST` : +bascule_detectee not_in [true], +coalition_rotation_detectee not_in [true]
- `RAW_NODE_BIRTH` : mêmes 2 filtres
- `GRAVITY_RESPRING_NODE` : +coalition_mtf_depth in [H1,H4,D1], +risk_sentiment not_in [RISK_ON]

**4 GRAMMAR — bounds informatifs + notes (kind=grammar non-émetteur) :**
- `GRAMMAR_CONTEXTE`, `GRAMMAR_REGIME`, `GRAMMAR_BREAK`, `GRAMMAR_PULLBACK`

27/27 YAML valides. Aucun SHADOW promu.

### Doctrine ajoutée (commit [`2a970cf`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/2a970cf98551c62f2506e20e6699b53d27432763))
`docs/DOCTRINE.md` — 19 → 27 règles :
- Règle 20 : calibration-first si marché ouvert
- Règle 21 : CONTEXT_CONTRACT.md mis à jour au même commit que le champ
- Règle 22 : une session = un périmètre = livraison complète
- Règle 23 : YAML consommateurs mis à jour dans la même session
- Règle 24 : CONTEXT_CONTRACT.md à la clôture de phase
- Règle 25 : promotion SHADOW→ACTIVE sur hit_rate live >= 60% / 50 déclenchements
- Règle 26 : fin de session = commit + DECISIONS_LOG + STATE.md
- Règle 27 : champ DORMANT > 2 phases → réévaluation
Process de session et cycles de vie principal/YAML ajoutés.

---

## ⚠️ Bug ouvert — ANTAGONIST_NODE = 0 déclenchement
**Anomalie** : ANTAGONIST_NODE n'a déclenché aucune fois sur 1728 scènes, malgré le fix
`zone_diagnostics` (commit `db11917`) censé alimenter les champs qu'il lit.
**Statut** : investigation séparée requise — ne pas toucher dans une session de calibration.
**Impact** : 1 principe ACTIVE cognitivement mort. Les 9 autres ACTIVE fonctionnent.
**Prochaine action** : session de diagnostic dédiée :
```
python scripts/v9_replay.py --search qualification=antagonisme
python scripts/v9_calibration.py --principes
```
Identifier pourquoi les scènes avec antagonisme ne franchissent pas les conditions du principe.

---

## Session Coalition Intelligence (2026-07-06) — enrichissement cognitif + gouvernance propagation

Session livrée sur `feat/v9-foundation-clean` (6 commits + push, rebase propre).
**339 tests verts** (318 baseline + 21 nouveaux).
13 nouveaux champs dans `_load_shared_context`, CONTEXT_CONTRACT.md créé, gardien automatique.
Commits : cd50cd7 / 4ebf86a / 24c0653 / 4d6cf53 / 44c8ae4 / 6648d27

---

## Correctif Phase 9.5 (2026-07-06) — observabilité DST US
Correctif limité à `market_status_warning()`. `core/v9/*` inchangé. 269 tests verts.

## Statut Phase 9
PHASE 9 TERMINÉE (2026-07-05). Chaîne cognitive complète :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision.
27 principes YAML (10 ACTIVE / 17 SHADOW). Latence 189ms/snapshot.
Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE9.md`.

## PHASES 1→8 TERMINÉES
Voir `docs/checkpoints/`. Automatisation, monitoring, calibration, déploiement live.

## Décisions actées
- V9 from scratch. GitHub = source de vérité. V8 = migration curée.
- Squelette cognitif : Forces → Décision (9 couches).
- CONTEXT_CONTRACT.md + test_context_propagation.py = gardien de propagation (2026-07-06).
- DOCTRINE.md 27 règles (2026-07-06) — ajout règles 20-27 calibration/session/YAML.
- COALITION_THRESHOLD : reporté à n>5000 scènes + WIN/LOSS (2026-07-06).

## Objectif immédiat
**Observer l'impact du tuning YAML sur les prochaines heures de marché.**
Relancer `v9_calibration.py --principes` dans 2-3h (session New York active).
Parallèle : investigation ANTAGONIST_NODE (session dédiée).

## Chantiers en file
1. **Investigation ANTAGONIST_NODE** — bug : 0/1728, à diagnostiquer
2. **Attente données** — relancer `--principes` à n>500 scènes post-tuning YAML
3. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS
4. **Métriques DORMANT P2** — contexte_temporel.fenetre + declencheur + variante
5. **Promotion SHADOW→ACTIVE** — décision sur base hit_rate live (règle 25)
6. AGENT.md racine V9
7. Inventaire de migration V8 → V9

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code / Hermes / MiniMax : implémentation selon périmètre assigné

## Règle d'or
Aucune implémentation structurante sans ancrage explicite dans la doctrine V9.
Toute nouvelle métrique tracée dans CONTEXT_CONTRACT.md avant ou à la livraison.
