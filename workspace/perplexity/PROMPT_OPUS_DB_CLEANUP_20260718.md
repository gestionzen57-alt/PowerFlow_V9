# PROMPT OPUS — NETTOYAGE & RATIONALISATION DB HOT V9 (`v9_forces.db`)

> Assemblé le 2026-07-18 par Claude CLI. Corps de mission (« premier prompt »)
> + ADDENDUM P0 (audit indépendant) verbatim en fin de document.
> Faits ci-dessous **vérifiés en lecture seule** avant assemblage.

## FAITS VÉRIFIÉS (2026-07-18 ~10:05, read-only)

- `data/v9_forces.db` = **3 121 971 200 o ≈ 2,91 GiB**, mtime du jour → **écriture récente**.
- `journal_mode = wal`.
- **Writer live confirmé** : `core.v9.capture_server` (PID 9208) écoute le **port 31685**.
- **14 tâches planifiées V9 « Ready »** : V9CaptureWatchdog, V9_ArbiterRecal,
  V9_AutoCalibrator, V9_AutoRestart, V9_CalibrationLoop, V9_HeartbeatAlert,
  V9_HeartbeatCheck, V9_LearningLoop, V9_MetaAgentScan, V9_PaperTradeLoop,
  V9_ResolveLoop, V9_StrategyPoleRecompute, V9_TelegramAgent, V9_TelegramWatch.
- Comptages têtes-de-liste (concordent avec l'audit) :
  - `forces_snapshots` = 130 368
  - `principle_evaluations` = 2 605 210 — dont `shadow` = 1 984 513 (76,17 %),
    `triggered=1` = 328 990 (~12,6 %)
  - `regime_snapshots` = 607 304 · `zone_diagnostics` = 579 896
  - `scenes` = 76 009 · `decisions` = 75 877 · `paper_trades` = 4 817

> ⚠️ **CONSÉQUENCE IMMÉDIATE : le système n'est PAS quiescent.** Toute opération
> destructive est INTERDITE tant que la quiescence n'est pas prouvée (voir GARDE P0).

## MISSION

Ramener la DB HOT `v9_forces.db` de ~2,91 GiB vers ~0,8–1,3 GiB **sans perte de
vérité utile**, corriger les causes de croissance **à la source**, puis stabiliser
la croissance quotidienne. Cible d'architecture (verdict CEO, à ne PAS devancer) :

1. Dédupliquer l'intrabar supersédé (cause P0-A).
2. Stopper l'explosion SHADOW (cause P0-B).
3. Réparer le schéma (id NULL, colonnes constantes/NULL, sentinelles).
4. **Ensuite seulement** installer `SQLite HOT → Parquet ZSTD COLD → DuckDB analytics`.
5. PostgreSQL/Timescale = NON prioritaire (seulement si multi-writer, HOT > 20 Go
   malgré rétention, locks persistants, ou besoin de réplication).

**Ne PAS migrer le HOT hors SQLite dans cette mission.**

## CONTRAINTES DOCTRINE (bloquantes)

- R7 : tests verts avant tout commit ; toute régression justifiée dans DECISIONS_LOG.
- R14 : Git = source de vérité.
- R18 : pas de LLM dans le cœur cognitif (le nettoyage est de l'outillage/opérations).
- R8/R26 : doc + DECISIONS_LOG + STATE.md à jour ; commits atomiques.
- **Aucune écriture sur `v9_forces.db` en prod** dans les phases 0–2. Tout test de
  déduplication se fait **sur clone**. Archive **avant** toute suppression.

## PHASAGE IMPOSÉ (gate CEO entre P2 et P3)

- **P0 — Quiescence & inventaire writers** (voir GARDE P0). Non destructif.
- **P1 — Audit read-only complet** : confirmer chiffres P0-A/P0-B, cartographier
  la descendance intrabar, sémantique des clés temporelles (capture_time/
  server_time/timestamp/rowid), colonnes constantes/NULL, anomalies.
- **P2 — Benchmark sur clone** : reproduire les scénarios d'économie, mesurer,
  vérifier reconstruction complète de la chaîne après compactage. Produire un
  **plan chiffré + risques** pour le CEO. **STOP ici — attendre GO explicite.**
- **P3 — Correction à la source** (production) : ne persister en HOT que la
  dernière version de barre ouverte + barre clôturée canonique ; remplacer la
  persistance shadow exhaustive par un journal de diff compact.
- **P4 — Compactage HOT** (après GO + backup) : dédup/purge, VACUUM, vérif.
- **P5 — HOT→COLD** : Parquet ZSTD + DuckDB pour l'analytique historique.

Rends un livrable écrit à chaque phase. **Ne franchis jamais le gate P2→P3 sans GO.**

---

## ADDENDUM P0 — RÉSULTATS DE L'AUDIT INDÉPENDANT À CONFIRMER

Un audit read-only parallèle a identifié DEUX sources principales de croissance.

### P0-A — RÉVISIONS INTRABAR SUPERSEDÉES

Dans `forces_snapshots` :
- 107 744 révisions ouvertes supersédées ;
- 82,65 % de la table ;
- 388 clés (symbol, timeframe, bar_time, is_closed_bar) dupliquées ;
- multiplicité maximale : 844 versions de la même barre ;
- principalement GBPUSD/M15 : 77 603 révisions excédentaires ;
- puis GBPUSD/M5 : 30 111 révisions excédentaires.

Cette répétition est propagée dans toute la chaîne :
- `scenes` : 61 599 lignes concernées ;
- `behaviors` : 61 596 ;
- `windows` : 61 595 ;
- `exploitability` : 61 595 ;
- `regime_snapshots` : 492 752 ;
- `zone_diagnostics` : 492 640 ;
- `principle_evaluations` : 566 877 ;
- `signals` : 61 593 ;
- `decisions` : 61 593.

Allocation estimée table + index : environ 1,44 Gio, soit près de 49,7 % de la DB.

MISSION OBLIGATOIRE :
1. déterminer si V9 a besoin de conserver toutes les révisions intrabar ;
2. distinguer vérité tick/intrabar utile et versions supersédées sans valeur ;
3. tracer pourquoi M15/M5 sont persistés des centaines de fois par barre ;
4. corriger la production à la source ;
5. ne conserver en HOT que :
   - la dernière version de la barre ouverte ;
   - la barre clôturée canonique ;
   - éventuellement les changements intrabar significatifs dans une table séparée et compacte ;
6. tester toute déduplication sur clone ;
7. préserver les descendants des snapshots réellement utilisés par une décision résolue ou un paper trade ;
8. archiver avant suppression ;
9. vérifier la reconstruction complète de la chaîne après compactage.

Ne choisis PAS la ligne à garder avec `ORDER BY id DESC` : plusieurs tables live
ont des id NULL à cause de la dérive du schéma. Utilise une règle temporelle et
métier validée : capture_time/server_time/timestamp/rowid selon la sémantique constatée.

### P0-B — EXPLOSION SHADOW

`principle_evaluations` :
- 2 605 210 lignes ;
- 1 984 513 source_type='shadow', soit 76,17 % ;
- fan-out shadow ≈ 199,89 lignes/snapshot ;
- fan-out live ≈ 9,28 lignes/snapshot ;
- 87,37 % de toutes les évaluations ont triggered=0.

Le pass shadow persiste donc une matrice presque complète, principalement des
évaluations ACTIVE non déclenchées. La purge actuelle basée sur v9_status='SHADOW'
ne cible pas ce volume.

MISSION :
- remplacer la persistance shadow exhaustive par un journal compact de diff ;
- garder le détail uniquement si triggered, divergence, changement significatif ou échantillon contrôlé ;
- agréger les négatifs ;
- garantir que shadow ne remplace jamais live ;
- filtrer source_type dans toutes les statistiques d'apprentissage.

### ÉCONOMIES À BENCHMARKER SUR CLONE

Scénarios non additifs :
- retirer la descendance intrabar supersédée : ≈ 1,44 Gio ;
- garder uniquement triggered=1 dans principle_evaluations : ≈ 1,34 Gio ;
- triggers + échantillon 10 % des négatifs : ≈ 1,21 Gio ;
- retirer/archiver source_type='shadow' : ≈ 1,17 Gio ;
- rationaliser les index candidats : jusqu'à ≈ 132 Mio supplémentaires, mais seulement après EXPLAIN QUERY PLAN et benchmark.

Objectif réaliste à tester : ramener la DB HOT de 2,91 Gio vers environ 0,8–1,3
Gio, sans perte de vérité utile, puis stabiliser sa croissance quotidienne.

### AUTRES ANOMALIES À TRAITER

- 9 décisions référencent un signal_id absent ;
- bar_time=99 999 999 observé sur EURUSD/M5 : sentinelle ou donnée malformée ;
- paper_trades_backup_20260717 duplique exactement les 4 817 paper_trades, coût faible ≈ 1,4 Mio, à archiver hors DB si backup déjà validé ;
- decisions.contexte_complet_json est du zlib binaire malgré son nom JSON : ne pas le déclarer corrompu et ne pas le supprimer ;
- zone_diagnostics est réellement produit et consommé : ne pas supprimer la table en bloc ;
- plusieurs colonnes de zone_diagnostics sont cependant constantes ;
- plusieurs colonnes regime_snapshots sont 100 % NULL.

### GARDE CRITIQUE WEEK-END

L'audit read-only a constaté que le mtime de v9_forces.db changeait pendant
l'inspection. Malgré le week-end, un processus externe écrivait probablement.
**[CONFIRMÉ 2026-07-18 : `core.v9.capture_server` PID 9208 écoute :31685 + 14 crons Ready.]**

Donc :
- ne jamais supposer « pas de prod » ;
- identifier tous les writers ;
- vérifier le port 31685, les processus Python et les tâches planifiées ;
- stopper proprement pipeline, shadow loop, resolver, paper-trade loop et crons avant backup/reconstruction ;
- confirmer l'absence d'écriture par deux contrôles espacés de taille, mtime, WAL et compteurs ;
- aucune opération destructive tant que la quiescence n'est pas prouvée.
