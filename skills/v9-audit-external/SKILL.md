---
name: v9-audit-external
description: |
  Boucle d'auto-amelioration declenchee par audit externe (Perplexity/Kimi 3).
  Integre les findings, planifie les fixes, verifie les tests.

[Audit External Bootstrap]

Author : Hermes Phase 104 motion CEO 48H non-stop (post-audit Perplexity v2)
Date : 01/08/2026
Source : PowerFlow V9 Edge Fund - audit externe

PRINCIPE
--------
Apres chaque audit externe (Perplexity, Kimi 3, Claude Opus, etc.) :
1. Ingerer les findings (P0/P1/P2/P3 + bugs + anti-patterns + recommandations)
2. Planifier les fixes par ordre de criticite
3. Appliquer atomiquement avec tests obligatoires
4. Verifier la regression fresh pytest apres chaque commit

BOUCLE NATIVE
------------
python scripts/v9_audit_ingest.py <audit_id>
python scripts/v9_audit_v2_fixes.py --apply    (P0 immediats)
python scripts/v9_bug_04_fixer.py --apply      (indentation pathologique)
pytest tests/ -q -p no:cacheprovider             (verification fresh)
git add . && git commit -m "fix(v9): audit v2 P0 fixes" && git push

PIPELINE EN 5 PHASES
--------------------
Phase A : Audit verify (lecture seule)
Phase B : Fix P0 (moins de 2h total)
Phase C : Tests audit (>= 10 verts)
Phase D : Commit + push atomique
Phase E : BILAN audit v2 + tag release candidate

ANTI-PATTERNS R31 COUVERTS
---------------------------
- os.environ.get() direct -> kill_switches.get()
- NameError/OperationalError swallow -> log.warning + retry
- Config hardcoded -> .env via kill_switches
- datetime.now() multiple -> pin now_utc en tete
- COUNT(*) full scan -> LIMIT 1
- Indentation pathologique -> v9_bug_04_fixer.py

BUGS P0 COUVERTS (audit v2)
---------------------------
- BUG-03 : _batch_session_time reset
- BUG-04 : DD protector indentation
- BUG-06 : RiskParityEngine import
- BUG-10 : pyramiding_result safe default
- BUG-02 : _execution_simulation_enabled (deja fixe 046669f)

PROCHAIN AUDIT
--------------
Date : 08/08/2026 (rolling 7j)
Triggers :
  - Nouvelles features livrees
  - Walk-forward OOS results disponibles
  - Modifications trade_engine.py
  - Changement config .env

AUTO-TRIGGERS
-------------
| Trigger | Action |
|---|---|
| weekly_report.sh produces KPI < target | request external audit |
| Phase 12 LIVE motion | mandatory audit before go-live |
| New kill switch added | update anti-pattern R31 list |
| Bug latent trouve en prod | quarantine + audit request |

FIN
---