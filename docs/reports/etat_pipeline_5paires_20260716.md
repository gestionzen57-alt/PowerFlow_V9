# État pipeline 5 paires — Reprise session 2026-07-17

> Session de reprise après reboot Søn. Périmètre : purge NZD (vue),
> **fix vote-devise (cause racine trouvée)**, vérification pipeline cognitif
> multi-paires.

## Résumé exécutif

Le biais NZD résiduel (~97 %/jour malgré le fix DIVERSIFY du 15-16/07) avait
une **cause racine unique et précise** : un **index UNIQUE tronqué** sur
`principle_evaluations`. Le moteur cognitif était déjà correct ; c'est la
couche de persistance qui écrasait 7 devises sur 8. Fix appliqué, vérifié,
verrouillé par test de non-régression.

## P0 — État après reboot

| Contrôle | Résultat |
|---|---|
| Pipeline (`v9_supervisor --health`) | OK — 15 modules, DB OK, marché OUVERT (sydney) |
| Snapshots 5 paires | Frais (dernier ~22:18 UTC) |
| Port capture 31685 | libre (serveur signalé inactif, mais flux frais actif) |

## P1 — Fix vote-devise (LE chantier) ✅

### Diagnostic

- **Symptôme** : 96-99 % des `principle_evaluations` portent `currency='NZD'`,
  quel que soit le symbole du snapshot (GBPUSD, USDJPY, USDCAD…). Or aucune
  des 5 paires n'implique NZD.
- **Le moteur est correct** : `PrincipleEngine.evaluate_principles(sid)`
  retourne **440 évals = 55/devise, 44 ACTIVE/devise** — parfaitement
  équilibré sur les 8 devises. Vérifié en live sur snapshots USDJPY et EURUSD.
- **La persistance collapse** : après écriture, la DB ne contenait que
  `NZD` (44 ACTIVE) + quelques SHADOW.

### Cause racine

```
CREATE UNIQUE INDEX idx_pe_snapshot_principle
    ON principle_evaluations(snapshot_id, principle_id)   -- SANS currency
```

Index ajouté le **2026-07-06** (dédup DB, cf. DECISIONS_LOG) pour l'idempotence,
à une époque où le vote-devise assignait **tout à une seule devise** par
snapshot. `_write_evaluations_to_db()` utilise `INSERT OR REPLACE` : les 8
évaluations par-devise d'un même principe entrent en collision sur le triple
tronqué et se **collapsent en une seule — la dernière du loop**
`DEVISES = [USD, GBP, EUR, JPY, CAD, CHF, AUD, NZD]`. **NZD étant dernier, il
écrase systématiquement les 7 autres.** Le fix DIVERSIFY (15-16/07) a rendu le
moteur multi-devises, mais l'index n'a jamais été mis à jour → biais résiduel.

### Correctif

- Index UNIQUE remplacé par `(snapshot_id, principle_id, currency)`.
- Migration DB live idempotente : `scripts/fix_vote_devise_index_20260717.py --apply`.
- Codifié dans le schéma (`core/v9/principle_db.py`) pour les futures DB.
- Backup R8 : `data/v9_forces.db.bak_20260717_votedevise`
  (MD5 `715ec03d6e17a2dc9651352d2a855fc8`, 1632 MB).

### Vérification post-fix

| Contrôle | Avant | Après |
|---|---|---|
| Devises persistées / snapshot | 1 (NZD) | **8** (45 chacune) |
| Part NZD | ~97 % | **12,5 %** (1/8, équilibré) |
| Idempotence rejeu | OK | OK (0 doublon sur `(principle, currency)`) |
| Vue `v_principle_evaluations_clean` | ~1 587 | 16 583 (alimentée par les 8 devises) |

Aucune modification de `principle_engine.py` : le moteur était déjà correct.

## P2 — Purge NZD (Option A) ✅

Vue `v_principle_evaluations_clean` présente et fonctionnelle (filtre
`currency != 'NZD'`). Historique NZD (~655k lignes) conservé (non-destructif,
Option A actée par Søn). Les nouvelles évaluations post-fix étant équilibrées,
le poids relatif de l'historique NZD décroît naturellement.

## P3 — Pipeline cognitif multi-paires ✅

**Les 4 nouvelles paires SONT lues** par le pipeline cognitif (scènes +
évaluations fraîches à ~22:15 UTC) :

| Paire | Snapshots | Scènes | Évaluations |
|---|---|---|---|
| GBPUSD | 117 779 | 67 973 | 661 142 |
| USDJPY | 879 | 278 | 10 344 |
| USDCAD | 544 | 230 | 11 088 |
| USDCHF | 308 | 202 | 8 414 |
| EURUSD | 585 | 172 | 10 160 |

Aucune paire à 0 scène/éval → orchestrator et stale gate traitent bien les 5
paires. Rien à débloquer côté intégration cognitive.

## P4 — Livrables

- `scripts/fix_vote_devise_index_20260717.py` (migration + doc cause racine)
- `core/v9/principle_db.py` : index UNIQUE `(snapshot_id, principle_id, currency)`
- `tests/test_diversify_revival.py` : +1 test non-régression vote-devise
- Tests : **1502 verts** (1501 + 1)

## Garde-fous respectés

R2 (additif, GBPUSD intact) · R6 (migration défensive, dry-run par défaut) ·
R7 (tests verts) · R8 (backup MD5) · R18 (zéro LLM, index SQL pur) ·
order_executor.py et config.py non touchés.

## Passation Hermes

Rien à finir côté intégration : les 5 paires sont pleinement lues. Le levier
vote-devise est corrigé à la racine. Surveiller sur 24 h que la distribution
`currency` des nouveaux snapshots reste ~1/8 par devise (et non un retour NZD).
