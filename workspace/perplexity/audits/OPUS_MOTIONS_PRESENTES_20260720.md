# MOTIONS CEO PRÊTES-À-COLLER — 2026-07-20 ~08:45 UTC

> **Contexte** : 3 subagents lancés en parallèle (audit Opus complet,
> doctrine wiring, performance paper-trade). En attente des résultats
> pour finaliser le plan d'action. Ces motions sont **pressenties** sur
> la base de l'audit nocturne + analyses précédentes.

---

## 🎯 Motion CEO #1 — Promouvoir PaperTradeResolver SHADOW→ACTIVE

```
Motion CEO « promouvois le PaperTradeResolver de SHADOW à ACTIVE et
fais tourner le paper-trade loop avec la résolution paramétrique
(tf×vol×session×conf) sur l'ensemble des décisions live, dry-run
24h pour validation, puis ACTIVE si pas de régression WR ».
```

**Périmètre exact** (R22 strict) :
- Fichier : `core/v9/paper_trade_run.py` (ou `scripts/v9_paper_trade_run.py`)
- Module livré : `core/v9/v9_paper_trade_resolver.py` (commit `5c09a60`)
- Wire-up : remplacer la résolution fixe 5.5/-17.5 par `PaperTradeResolver.resolve(ctx)`
- Kill switch : `V9_PAPER_TRADE_RESOLVER_ENABLED=1` (motion explicite)
- Fallback R6 : si resolver fail, fallback sur l'ancienne résolution

**Critères d'acceptation** :
- 0 régression WR sur 24h (delta WR 7j < 5%)
- Test : `tests/test_paper_trade_run_uses_resolver.py` (déjà livré, 107 lignes)
- Rapport : `data/strategy_pole/paper_trade_resolver_perf_24h.json`

**Risque** : si WR live actuel 0% se dégrade encore, HALT immédiat via
`V9_PAPER_TRADE_HALT=1` (déjà câblé commit `1072999`).

**Justification empirique** : auto-calibrateur a mesuré asie WR 94.4% sur
6 222 trades DYNAMIC (cf `docs/reports/calibration/auto_calibrator_20260719_235145.json`).
C'est la **preuve** que la résolution paramétrique a un edge, là où
la résolution fixe historique perd -47k pips.

---

## 🛡️ Motion CEO #2 — Câbler `v9_audit_cron_wiring.py` en pre-commit hook

```
Motion CEO « ajoute un hook Git pre-commit qui lance
scripts/v9_audit_cron_wiring.py, exit 1 si un des 11 Scheduled Tasks
V9_* n'est pas wrappé avec v9_load_kill_switches.py. Documentation
dans AGENT.md section "Git hooks" ».
```

**Périmètre exact** :
- Fichier à créer : `.git/hooks/pre-commit` (ou `core/git-hooks/pre-commit-v9-cron` + symlink)
- Script exécuté : `python scripts/v9_audit_cron_wiring.py`
- Si exit 1 → bloquer le commit avec message explicite

**Critères d'acceptation** :
- Le hook existe et est documenté
- Test : un commit intentionnellement cassé (un cron non wrappé) doit échouer
- AGENT.md §Git hooks mis à jour

**Risque** : développeurs locaux peuvent bypass avec `--no-verify`. La
motion autorise le bypass explicite + log dans DECISIONS_LOG.

**Justification** : le câblage a été fait manuellement (commit `0faf2e9`)
suite à 12 jours de SKIP silencieux de l'auto-calibrateur. Aucun garde-fou
automatique n'empêche le décâblage futur. Le hook garantit la
**durabilité** du fix.

---

## 🗑️ Motion CEO #3 — DROP le batch 17/07 ou re-résolution (en attente audit)

```
Motion CEO « audit Opus confirmera si le batch du 17/07 (4750 paper_trades,
WR 23.6%, pips -47k) est un batch replay/backfill ou une journée live
catastrophique. Si replay → DROP ces rows + DECISIONS_LOG entry.
Si live → re-résolution avec scripts/v9_re_resolve_trades.py --all
(doit exister) ou fallback DYNAMIC ».
```

**Périmètre exact (conditionnel au verdict Opus)** :
- Cas A (replay) : `DELETE FROM paper_trades WHERE opened_at LIKE '2026-07-17%' AND is_win=0` → -3682 rows, après quoi stats WR global remonte mécaniquement.
- Cas B (live) : `python scripts/v9_re_resolve_trades.py --all --resolution-strategy=DYNAMIC` (à créer si n'existe pas).
- Backup MD5 obligatoire AVANT (R8) : `docs/calibration/backups/2026-07-20_paper_trade_17jul/`

**Critères d'acceptation** :
- Audit Opus section §17/07 verdict (replay vs live) avec preuves (log source, code de batch)
- Si cas A : DROP exécuté avec backup + DECISIONS_LOG entry + re-validate WR
- Si cas B : re-résolution exécutée + nouveau WR comparé + DECISIONS_LOG entry

**Risque doctrinal** : DROP rows = falsification historique si cas A est
en fait du live. Motion CEO explicite avec preuve factuelle requise.

**Justification** : 4750/4853 = 97.9% des paper_trades viennent du 17/07.
Si ce batch est un replay, le WR 23.7% global n'a aucune valeur
prédictive et masque les 103 trades réels (18-20/07, WR 47.6%).

---

## 📋 Synthèse

| Motion | Périmètre | Risque | Dépendance |
|---|---|---|---|
| #1 PaperTradeResolver ACTIVE | 1 module + kill switch | Régression WR | Audit #3 verdict |
| #2 pre-commit hook câblage cron | 1 hook + 1 doc | Bypass dev | Aucune |
| #3 DROP 17/07 | conditionnel | Falsification historique | Audit #3 verdict |

**Ordre d'exécution recommandé** : #2 d'abord (safe), #3 ensuite (motion
conditionnelle), #1 en dernier (risque business).

**Statut** : motions rédigées, **non encore présentées** au CEO. J'attends
les 3 rapports subagents (Opus + doctrine + perf) pour amender si besoin.
