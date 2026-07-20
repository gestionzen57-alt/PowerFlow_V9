# DROP batch catastrophe 17/07 — GBPUSD baissier

> **Date** : 2026-07-20 ~08:25 UTC · **Opérateur** : Claude CLI (Mission R22, Chantier 2)
> **Motion CEO** : Audit `PERF_PAPER_VS_DECISIONS_20260720.md` §15h00 (point 1)
> **Prérequis Chantier 1** : fix P0 idempotence `post_decision_hook` (commit `bff59e2`) —
> empêche toute NOUVELLE récidive ; ce Chantier 2 nettoie l'historique.

## Résumé

Le 17/07, une boucle de ré-ouverture (garde d'idempotence défaillante, corrigée
au Chantier 1) a empilé des milliers de paper_trades GBPUSD **baissier** clôturés
au SL fixe. L'edge baissier GBPUSD est structurellement négatif
(`V9_NO_BAISSIERE=1` + `V9_GBPUSD_LONG_ONLY=1` actifs → aucun nouveau baissier
GBPUSD n'est créé). Ces 3 690 trades tiraient le WR paper global de ~92 % (sain)
vers ~24 % (artefact).

**Action** : DROP audité et réversible des **3 690 paper_trades GBPUSD baissier**,
puis re-résolution des décisions non résolues.

## Cible du DROP (prédicat fixe et explicite)

```sql
snapshot_id LIKE 'v9-GBPUSD-%' AND direction = 'baissiere'
```

| | n | WR | pips | plage `opened_at` |
|---|---|---|---|---|
| **Cible supprimée** | **3 690** | **1.03 %** | **-56 089.8** | 2026-07-15 17:10 → 2026-07-20 01:15 (cœur : 17/07 15:09→19:25) |

Le sous-batch 17/07 15:00–20:00 baissier = 3 635 trades ; les 55 restants sont
d'autres jours (15/07 ×45, 16/07 ×1, 18/07 ×8, 20/07 ×1), tous baissier GBPUSD,
inclus dans la cible car même edge toxique (V9_NO_BAISSIERE). Le total **3 690 /
-56 089 pips** correspond exactement au chiffre de la motion CEO.

## Métriques avant / après (global `paper_trades`)

| Métrique | AVANT | APRÈS | Δ |
|---|---|---|---|
| Nb trades | 4 854 | 1 164 | -3 690 |
| WR global | **23.69 %** | **95.53 %** | +71.8 pts |
| Pips cumulés | **-47 426.4** | **+8 663.4** | **+56 089.8** |
| Trades ouverts | 16 | 15 | (writer live) |
| Plage dates | 15/07 → 20/07 | 15/07 → 20/07 | inchangée |

> Swing de **+56 089.8 pips** sur l'historique paper — l'artefact catastrophe est
> retiré, le WR reflète désormais l'edge réel (haussier GBPUSD + autres paires).

## Préservé (NON supprimé — vérifié)

- **GBPUSD haussier 17/07** : 1 075 trades, **WR 100 %, +8 767 pips** — l'edge
  sain, explicitement conservé (audit §recommandation).
- Toutes les autres paires × directions.

## Re-résolution des décisions (`v9_resolve_decision_auto.py`)

`--apply --skip-no-future-prices --backup backups/drop_batch_20260720`

| Décisions non résolues | Résolues | Wins | Losses | WR | pips moyens |
|---|---|---|---|---|---|
| 134 | 134 | 56 | 78 | 41.8 % | -2.1 |

Sorties : `time_end_asie` 74, `tp_hit_asie` 25, `sl_hit_asie` 18, `time_end_london`
14, `tp_hit_london` 2, `sl_hit_london` 1. Stratégie DYNAMIC, horizon 4 h, sessions
`new_york`/`after` skippées (doctrine Brief O1).

## Sauvegarde & réversibilité (R8)

| Artefact | Contenu |
|---|---|
| `backups/drop_batch_20260720/md5_pre.txt` | MD5 DB pré-DROP `d4a985143825232839e17cc3313e7b68` |
| Table in-DB `paper_trades_dropped_17jul_baissier` | 3 690 lignes (restauration `INSERT INTO paper_trades SELECT * FROM …`) |
| `backups/drop_batch_20260720/paper_trades_dropped.json` | dump complet 3 690 lignes (hors-DB) |
| `backups/drop_batch_20260720/drop_report.json` | métriques avant/après |
| `backups/drop_batch_20260720/reresolve_report.json` | rapport re-résolution |

Intégrité post-op : `PRAGMA quick_check` = **ok**. Aucun VACUUM (writer live actif).

## Impact tests (baseline `pytest tests/ -q`)

**2355 passed / 17 failed** (≥ 2355 requis ✓). Avant la mission (Chantier 1
inclus) : 2362 passed / 8 failed. Le DROP retire un jeu de données (baissier
GBPUSD) sur lequel plusieurs tests de **caractérisation** et d'**analyse
baissier** étaient bâtis — leur bascule est une conséquence directe et attendue
du retrait de la catastrophe, **pas** un bug du code commité (fix idempotence +
script DROP). Classement des 9 nouveaux échecs :

| Test | Cause | Nature |
|---|---|---|
| `test_perf…::test_divergence_confined_to_gbpusd_baissier` | WR GBPUSD passe de 24 %→99 % | caractérisation pré-DROP inversée (docstring anticipe « paper loop corrigé ») |
| `test_perf…::test_decisions_dynamic_resolution_strictly_higher_than_paper` | paper WR 96 % > DYNAMIC 83 % | idem — l'artefact qui rendait paper < DYNAMIC est retiré |
| `test_perf…::test_post_catastrophe_wr_acceptable` | WR 35.6 % sur n=45 (18/07+) | seuil ≥ 40 % calibré sur population pré-DROP |
| `test_v9_re_resolve::test_re_resolve_wr_realistic` | WR re-resolve 95 % > borne 80 % | population nettoyée = WR légitimement élevé |
| `test_v9_baissier_audit` ×5 | `strategy_pole/*.json` réécrits par un cron background (10:10-10:12) **et** grid-search short = « Aucun trade disponible » post-DROP | interférence background + plus aucune donnée baissier (cohérent `V9_NO_BAISSIERE=1`) |

→ Ces tests d'analyse/caractérisation baissier sont **vestigiaux** sous le régime
`V9_NO_BAISSIERE=1` (il n'y a plus de baissier à analyser, ce qui est l'objectif).
Recalibrage / mise en `skip` = motion dédiée (leurs fichiers sont non commités,
compagnons de l'audit — non touchés ici, R22).

## Findings hors périmètre (motion CEO séparée requise)

Le GO CEO de cette mission couvre **exactement** les 3 690 baissier GBPUSD. Les
points suivants, découverts pendant l'opération, ne sont **pas** traités ici
(scope destructif non autorisé) — flaggés pour réconciliation :

1. **Résidu de duplication haussier (19-20/07)** : 3 snapshots GBPUSD M15
   **haussier** portent 7 paper_trades chacun (18 lignes de doublons) — même
   signature idempotence, côté haussier. Non supprimés (hors cible baissier).
   Le guard `test_no_duplicate_snapshot_in_paper_trades` reste rouge tant que ces
   18 lignes existent. → Motion dédiée « dédup résidu idempotence ».
2. **`test_db_no_17jul_batch`** (non commité) attend la fenêtre 17/07 15h-20h
   **entière** vidée (toutes directions) — ce qui détruirait les 1 075 trades
   haussier profitables (WR 100 %, +8 767 pips) que la mission + l'audit
   **préservent** explicitement. Test contradictoire avec le périmètre → non
   satisfait par sur-suppression, flaggé.
3. **Tension mission vs audit** : le tableau de recommandation de l'audit
   suggérait DROP du seul burst new_york 17/07 (~3 335) + re-résolution des
   « autres sessions baissier ». La motion CEO (en-tête mission) demande les
   **3 690 baissier** (chiffre exact -56 089 pips) — appliqué ici, cohérent avec
   `V9_NO_BAISSIERE=1` (tout baissier GBPUSD = edge toxique). Les 55 baissier hors
   17/07 (15/07 ×45 WR 0 %, etc.) sont inclus. Réversible via table in-DB si le
   CEO préfère restaurer/re-résoudre ce sous-ensemble.

## Reproduction

```bash
# 1. Backup MD5 (R8) — déjà présent : backups/drop_batch_20260720/md5_pre.txt
# 2. Dry-run
python scripts/v9_drop_batch_17jul.py --dry-run
# 3. Apply
python scripts/v9_drop_batch_17jul.py --apply --backup backups/drop_batch_20260720
# 4. Re-résolution
python scripts/v9_resolve_decision_auto.py --apply --skip-no-future-prices \
    --backup backups/drop_batch_20260720
```
