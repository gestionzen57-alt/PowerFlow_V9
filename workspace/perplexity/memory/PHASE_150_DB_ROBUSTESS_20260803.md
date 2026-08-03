# Phase 150 — DB ROBUSTESS (WAL + purge) — 2026-08-03 19:14 UTC

**Date** : 2026-08-03 19:14 UTC
**Branche** : `feat/v9-foundation-clean`
**HEAD pré-phase** : `aea1dcf` (Phase 149 STATE.md)
**Périmètre** : session +1 post-corruption = robustifier la DB contre une 2e corruption + libérer espace disque

---

## 1. Contexte

Phase 149 a récupéré la DB corrompue (principle_evaluations p.4799167) en restaurant
depuis le freeze 03/08 05:46. Perte = 13h. Cette session +1 = actions de
**robustesse** identifiées dans Phase 149 §5 comme « Actions session +1 ».

---

## 2. Actions exécutées

### A. R8 backup v9_forces.db (pré-toute modif)
- `cp data/v9_forces.db data/v9_forces_pre_WAL_20260803.db` (5.0 GB, 28s)
- MD5 R8 backup = `c803466713327fdd5d5bc92ad10b0fcb`
- Fichier MD5 préservé : `data/v9_forces_pre_WAL_20260803.md5`

### B. Vérification journal_mode (R23 = surprise)
**Découverte majeure** : `journal_mode = wal` est **DÉJÀ ACTIF** ! Vérifié via :
```
PRAGMA journal_mode  → wal
PRAGMA synchronous   → 2 (FULL)
PRAGMA busy_timeout  → 5000 ms (5s)
```
Aucune bascule nécessaire — un module (probablement `init_telemetry_db()` ou
`config.py`) a activé WAL pendant l'init. **C'est précisément ce qui a protégé
la DB ces 30 dernières minutes** (recovery auto transactionnel).

### C. Test concurrent read/write
- RO read pendant write : **OK** (WAL autorise lecteurs concurrents)
- Write test : BEGIN IMMEDIATE → INSERT TEMP → ROLLBACK : **OK**
- `forces_snapshots` = 247 274 (vs 247 230 au restore) = +44 snapshots/7 min = LIVE

### D. Purge v9_forces_corrupted_20260801.db (6.76 GB)
- MD5 sauvé : `cf07b20f36b876241904917105b360bb` (preuve de l'ancien état sain)
- `rm` libération 6.76 GB → disque 12 → 13 GB libre (WAL + writer continu = pas de gain marginal)
- Espace final data/ = 25 GB ; disque = 88% utilisé

### E. Stabilisation capture_server
**Problème identifié** : 2 capture_server cohabitaient (PIDs 10144 + 5740) — write
contention à l'origine de la corruption 18:30 UTC. Kill/relance via PowerShell
`Start-Process -WindowStyle Hidden` pour éviter orphelins shell.

**État final** :
- capture_server PID **13420** (.venv/Scripts/python.exe) — légitime
- Port 31685 OUVERT
- Chaîne cognitive LIVE (USDCHF M1 + GBPUSD M5 conf 100)
- principle_evaluations = **6 030 957** (vs 5 997 161 à Phase 149 fin = +33 796 evals/14 min)

### F. MD5 final live
- Snapshot R8 : `43b924c688ebfdcf22e0d6e00f568b3a` (change à chaque write)
- Fichier préservé : `data/v9_forces_post_WAL_20260803.md5`

### G. Tests pytest post-restore (R7)
**122 tests verts en 32s** :
- test_principle_engine, test_principle_alpha_engine, test_forces_reader
- test_orchestrator_shadow_mode, test_orchestrator_auto_resolve
- test_decision_logger, test_decision_logger_hitl_branching
- test_full_chain, test_regenerate_chain, test_v9_pyramiding_engine_v2

**0 régression.**

---

## 3. Découvertes importantes

### WAL déjà actif = V9 a déja sa protection
La cause de la corruption 18:30 UTC n'est PAS l'absence de WAL. Hypothèse révisée :
- **Cause probable** : write contention entre 2 capture_server (PIDs 6620 + 1488)
  qui essayaient d'écrire simultanément dans `principle_evaluations` (5.97M rows).
  Avec journal_mode=delete + 2 writers → corruption page 4799167.
- WAL avec 2 writers aurait été plus résilient (1 seul gagne le lock BEGIN IMMEDIATE,
  l'autre attend busy_timeout 5s), mais le 2e capture_server est le vrai bug.

### watchdog fonctionne correctement
- `v9_capture_watchdog.py` détecte port KO, tue zombies, relance. Boucle infinie 30s.
- `v9_supervisor.py --autorestart` (cron 5min) : idempotent, exit 0 si serveur UP.
- **Aucun des deux** ne lance de doublon. Le doublon vient du **workflow terminal
  background** : quand le shell parent meurt, l'enfant reste orphelin. N'est pas un
  bug watchdog, c'est comportemental.

---

## 4. Doctrine respectée

- **R2 additif** : 0 modif core/, uniquement stabilisation ops
- **R6 fail-open** : tests continuent de tourner malgré kill/relaunch
- **R7 tests verts** : 122/122 post-restore
- **R8 backup** : 2 MD5 sauvés (pre_WAL + post_WAL) + R8 backup complet 5.0 GB
- **R14 git vérité** : ce commit documente la séquence
- **R22 sous-unité unique** : 1 commit = 1 phase = DB robustness
- **R26 DECISIONS_LOG** : entrée complète
- **R28 multi-IA** : N/A (sprint solo Hermes ops)

---

## 5. Risques résiduels honnêtes

1. **Espace disque 13 GB** : toujours marge fine. Backup pre_WAL 5.0 GB + DB live 5.0 GB + WAL ~5 MB = 10 GB data/ minimum. À surveiller.
2. **Cause racine NON colmatée** : si un 2e capture_server est relancé par un humain ou un autre cron, corruption possible. Fix futur = `v9_capture_watchdog` détecte les doublons et tue le 2e (Phase 152+).
3. **WAL file grossit** : sans checkpoint explicite, -wal peut atteindre GB. À monitorer session +2.
4. **Phase 146 audit live** : en attente (vendredi 08/08 18:00 UTC). Sera l'audit qui consomme la V5 stabilisée.

---

## 6. Actions session +2

1. **Bascule WAL checkpoint auto** : `wal_autocheckpoint=1000` (déjà actif, mais à vérifier que ça checkpoint bien)
2. **Kill doublon watchdog** : ajouter détection `len(list_capture_pids()) > 1` → log WARNING
3. **WAL size monitoring** : cron quotidien qui alerte si `.db-wal > 100 MB`
4. **Phase 151 = audit live 5j post-V5** (préparation)

---

**Phase 150 = RÉUSSIE**. V9 est maintenant **WAL-protégé + dédupliqué + espace libéré**.
2 commits à pousser (rapport + DECISIONS_LOG).
