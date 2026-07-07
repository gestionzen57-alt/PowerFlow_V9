# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (dernière mise à jour 2026-07-07 20h55). Ce fichier ne fait
qu'organiser la même information par statut d'exécution pour une reprise rapide.

## En cours (mode A — VEILLE)
- **Observation live post-RULE29** — pipeline GBPUSD M5/M15/H1/H4/D1 vivant
  (port 31685, DB v9_forces.db, MT4 redémarré). Surveillance _detect_zone_type
  sur snapshots live, attente première fenêtre `naissance_isolee` en live.
- **Tests xfail consolidés** — 3 tests sur fichiers `test_v9_arbiter_rule29.py`
  marqués honnêtement avec raison traçable. À résoudre Phase 13 (refactor
  fixtures in-memory + arbiter.py).

## Prochaines actions
1. **Surveillance COALITION_THRESHOLD 5.38** — `python scripts/v9_calibration.py --principles`
   toutes les 2h — hit rate COALITION_NODE / POWER_ANGLE_BREAK / ZONE_RETEST.
2. **ANTAGONISM_THRESHOLD / PLIURE_THRESHOLD** — réévaluation à n>10 000 scènes live.
3. **Premier paper trade** — **NFP vendredi 7 août 2026** (1er vendredi du mois, typique UTC 12:30). Aucune news HIGH entre 2026-07-10 et 2026-08-04 (cf. `data/economic_calendar.json`). Marché range.
4. **WIN/LOSS ≥ 50** — collecte via `scripts/v9_resolve_decision.py` pour Phase 13.
5. **Premier événement `bascule/rupture/extension`** sur M15 GBPUSD → déclenchement
   `naissance_isolee` en live → vérification via dashboard watch fenetres.

## Gelé (ne pas démarrer)
- **Phase 11** — fusion multi-paires (gelée par décision Søn 2026-07-07 14h58).
- **Phase 12** — exécution d'ordre réelle (interdit fondateur, règle HITL avant ordre).
- **Phase 13** — agentique globale / federation multi-providers, gelée par règle 22
  + WIN/LOSS insuffisant. **Recalibrage pondérations règle 29** = chantier Phase 13.
- **Phase 10 (fédération)** — gelée par règle 19 (doctrine, stabilisation empirique).

## Terminé récemment (juillet 2026)
- ✅ **Règle 29 LIVRÉE** (2026-07-07 17h45 → 20h55) — 14 commits, doctrine §3.1+§3bis+§6+§8
  import V8 → V9, zone_type persistence, naissance_isolee window, HITL renforcé,
  arbiter pondération zone-type×session, tests dédiés (32+ verts).
  Ref. : `docs/checkpoints/CHECKPOINT_20260707_RULE29.md`.
- ✅ **Dette 10/10 résolue** (2026-07-07) — F-10 à F-19 (CHANGELOG, LICENSE, CI, etc.).
- ✅ **Phase 9.9 CONSOLIDATION-COMPLETE** (2026-07-07) — 14 sous-chantiers C-1→F-9.
- ✅ **Phase 9.7 + 9.8 livrées** (2026-07-07) — paper-trade simulator + heartbeat VPS-READY.
- ✅ **Phase 9 livrée** (2026-07-05) — chaîne cognitive 9 couches complète, 214 tests.
- ✅ **Phase 9.5** (2026-07-05) — outillage ops + mini-checkpoints + runbook, 40 tests.
- ✅ **2026-07-06** — ZoneDetector + Grammaire (9/9 node_rule ACTIVE), 283 tests.
- ✅ **2026-07-06** — Stabilisation live Phase 9 confirmée (flux EA MT4).
- ✅ **2026-07-06** — Session 4 YAML news-aware (4 principes enrichis, commit `a87d88f`).
- ✅ **2026-07-06** — Inventaire migration V8→V9 (audit MIGRATION_POLICY_V9.md).
- ✅ **2026-07-06** — Nettoyage 7 docs stales (alignement zone_diagnostics).
- ✅ **2026-07-07** — COALITION_THRESHOLD 5.0 → 5.38 (London open, commit `fb5383a`).
- ✅ **2026-07-07** — Telegram Notifier GBPUSD live (scripts/v9_telegram_notifier.py).
- ✅ **2026-07-07** — Fix signal_generator currency gap (commit `8697d84`).

## Recommandation pour chantier futur distinct (non démarré)
- **Refactor arbiter.py** : accepter conn optionnelle en paramètre (permet
  tests in-memory propres). Chantier Phase 13 si WIN/LOSS ≥ 50.
- **Décision DST-aware `market_calendar.py`** — chantier distinct, non bloquant.
