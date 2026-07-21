# RESOLUTION DRIFT — DEEP DIVE (Motion #32)

**Date** : 2026-07-20 · **Auteur** : Opus (opérateur, R28 assoupli) · **Mode** : lecture seule (Phase 1)
**DB auditée** : `data/v9_forces.db` (3,94 GiB, writer live actif + 14 crons)

---

## 0. TL;DR — l'incident est déjà remédié, le prompt cible un schéma fantôme

Le prompt Motion #32 décrit une boucle de résolution qui *dérive encore*. La vérification
sur la base live montre l'inverse : **l'incident de duplication a déjà été colmaté** (les
lignes fantômes sont archivées), et **le schéma décrit par le prompt n'existe pas**.

| Affirmation du prompt | Réalité mesurée (live) | Verdict |
|---|---|---|
| Table `paper_trades(snapshot_id, principle_name, side, outcome, profit_pips, resolved_at)` | Colonnes réelles : `trade_id, snapshot_id, direction, confiance, principes_source, opened_at, closed_at, pips_simulated, is_win, risk_go_context` | ❌ **schéma inexistant** |
| Jointure `force_snapshots_v2.snapshot_id` | Table `force_snapshots_v2` **absente** ; la vraie table est `forces_snapshots` | ❌ **table inexistante** |
| Bus `agent_event_bus WHERE event_type LIKE 'paper_trade.%'` | `data/v9_agent_bus.db` n'a pas `agent_event_bus` (tables : `events`, `subscriptions`, …) ; **0** event `paper_trade.*` | ❌ **table inexistante** |
| Doublons `(snapshot_id, principle_name, side)` résolus N fois | **0 doublon** aujourd'hui sur `(snapshot_id, direction)` et sur le triplet incl. `principes_source` | ✅ **déjà colmaté** |
| Pending zombies (snapshot_id disparu) | **0 zombie** contre `forces_snapshots` ; **1** trade `closed_at IS NULL` (trade encore ouvert, normal) | ✅ **non reproduit** |
| WR 90,33 % gonflé par doublons | WR réel **69,10 %** (123 wins / 178) ; **90,33 % non reproductible** sur la table courante | ⚠️ **chiffre non sourcé** |

**Conclusion** : la migration destructive proposée (dédup `DELETE`, `UNIQUE(snapshot_id,
principle_name, side)`, FK `force_snapshots_v2`) **échouerait à la compilation SQL** (colonnes/tables
absentes) et corrigerait un problème **déjà résolu**. Ne pas l'appliquer en l'état.

---

## 1. Constats chiffrés (schéma réel)

### A. Distribution `is_win` / WR
```
is_win=NULL : 1   (trade ouvert, closed_at NULL)
is_win=0    : 54  avg -7.54 pips   [2026-07-17 → 2026-07-20]
is_win=1    : 123 avg +5.21 pips   [2026-07-15 → 2026-07-20]
total=178 · resolved=177 · WR_all=69.10% · WR_resolved=69.49%
```

### B. Doublons — **0**
```
group by (snapshot_id, direction)                    having n>1 → 0 groupes
group by (snapshot_id, direction, principes_source)  having n>1 → 0 groupes
```

### C. Pending — **1** (trade ouvert légitime, `closed_at IS NULL`), **0** zombie
```
LEFT JOIN forces_snapshots ON pt.snapshot_id = fs.snapshot_id WHERE fs.snapshot_id IS NULL → 0
```

### D. Trace de la remédiation déjà effectuée (tables backup présentes)
```
paper_trades                        : 178 lignes (courant, propre)
paper_trades_backup_20260717        : 178 lignes (snapshot pré-nettoyage)
paper_trades_dropped_17jul_baissier : 3690 lignes (batch baissier retiré 17/07, WR 1.0%)
paper_trades_dedup_20260720         : 18 lignes fantômes archivées =
    snapshot v9-GBPUSD-M15-1783530010-112623 · haussiere · ×6
    snapshot v9-GBPUSD-M15-1783530981-113330 · haussiere · ×6
    snapshot v9-GBPUSD-M15-1784051181-073733 · haussiere · ×6
```
→ **3 snapshots résolus 6× chacun** = 18 lignes en trop, **déjà extraites** de la table live
vers `paper_trades_dedup_20260720`. C'est la signature exacte du symptôme « résolus plusieurs
fois » du prompt — mais au **passé**.

---

## 2. Arbre de causalité (3 niveaux)

- **Niveau 1 — symptôme historique** : 3 snapshots GBPUSD M15 haussiers comptés 6× → sur-comptage de profits.
- **Niveau 2 — mécanisme** : la table `paper_trades` n'a **aucune contrainte d'unicité** sur
  `(snapshot_id, direction)` (seul `trade_id` PK + index non-unique `idx_paper_trades_snapshot`).
  Un ré-appel du résolveur/insertion sur le même snapshot recrée une ligne (nouveau `trade_id`)
  au lieu d'être rejeté → duplication silencieuse possible.
- **Niveau 3 — déclencheur** : ré-résolutions multiples (scripts `v9_re_resolve_trades.py`,
  `v9_resolve_loop.py`, daemon auto) rejouées sans idempotence pendant la fenêtre du 17-20/07,
  chevauchant le batch baissier retiré. Aucune race live observée aujourd'hui (writer nominal).

## 3. Hypothèses racines (par vraisemblance)

1. **(Haute) Absence de contrainte d'unicité applicative** sur `(snapshot_id, direction[, principes_source])`.
   Réel, corrigeable ; c'est le **seul** correctif durable pertinent restant.
2. **(Moyenne) Ré-résolutions batch non idempotentes** rejouées manuellement pendant l'incident.
   Déjà éteint (0 dup courant) ; mitigé par une contrainte d'unicité + garde applicative.
3. **(Basse) Race writer live ↔ résolveur async**. Non observée ; `closed_at NULL`=1 seul, cohérent.
   Un lock distribué serait sur-ingénierie pour la volumétrie (178 lignes, 1 writer).

---

## 4. Recommandation

L'essentiel du plan Motion #32 est **inapplicable (schéma fantôme) ou redondant (déjà colmaté)**.
Le **seul correctif durable pertinent** est préventif et matché au schéma réel :

> **`CREATE UNIQUE INDEX IF NOT EXISTS ... ON paper_trades(snapshot_id, direction, principes_source)`**
> (idempotent, non destructif — 0 doublon courant donc création garantie sans échec),
> + garde applicative `INSERT ... ON CONFLICT DO NOTHING` dans le chemin d'insertion.

Écartés comme sur-ingénierie / hors-schéma : FK `force_snapshots_v2`, table `resolve_lock`
distribuée, stress test 1000-concurrent, métriques Prometheus. La dédup `DELETE` est **déjà faite**.

⚠️ Toute création d'index sur `data/v9_forces.db` reste une **écriture sur la prod** (3,94 GiB,
writer live + 14 crons) → **gate CEO** conforme au garde-fou « destruction/DDL prod → GO Søn ».
