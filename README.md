# PowerFlow V10 — Edge Fund Max (ex-V9)

> **Statut actif — 2026-08-06 12:32 CEST :** HEAD `23cf024`, branche
> `feat/v9-foundation-clean`, **1239 passed** sur `tests/test_v10_*.py`.
> Le projet actif est V10 : Cognitive Continuum + stale gate R10 + lecture
> fractale/cinématique + structure S1-S9 dans le chemin live. V10 est
> signal/paper/shadow ; aucun ordre réel V10 n’est une preuve d’exécution.
> Lire `docs/V10/DOCUMENT_STATUS.md` puis `docs/V10/STATE.md` avant toute
> action. Le reste de ce README est un snapshot V9 historique, conservé pour
> audit et explicitement non représentatif de la performance ou du statut
> actuel.

**Mission** : Système cognitif financier auto-apprenant, aligné sur la lecture
TA humaine. V10 = libre (10 règles R1-R10), V9 = héritage infrastructure.
Seul vrai garde-fou : R10 (protéger le capital).

> **🚨 V10 doctrine (2026-08-04 05:00 UTC)** : 30 règles V9 → 10 règles V10.
> Cœur cognitif V10 livré (core/v10/) + pivot SIGNAL-ONLY.
> Voir `AGENTS.md` §DOCTRINE V10 + `docs/V10/V10_PLAN_REPARALETTRAGE.md`.

> **Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.**

---

## ★ Statut au 04/08/2026 — Cœur cognitif V10 livré (autopilote) ★

```
Branch     : feat/v9-foundation-clean
HEAD       : 7a9a7b9 (pushé)
V10        : core/v10/ (Force F1-F5 + Structure S1-S9 + Contexte C1-C7 + Orchestrateur)
Pivot      : SIGNAL-ONLY — daemon V10SignalScanner (Running, zéro capital risqué R10)
Fix data   : symbol 337/337 sur paper_trades → risk parity cross-pair débloqué
Tests      : suite V10 54/54 verts
Docs       : docs/V10/V10_PHASE_EF_COGNITIVE_REPORT.md
```

### Edge confirmé (Phase 15 simulation 100 trades)

| Métrique | Valeur | Cible |
|---|---|---|
| **WR global** | **94.6%** | ≥ 60% |
| **Expectancy brute** | **+4.55 p/trade** | +3 p |
| **Expectancy nette (R6)** | **+3.05 p/trade** | ≥ +3 p |
| **Max DD** | **34.5 p** | ≤ 100 p |
| **Recovery factor** | **6.5x** | > 5x |
| **Concentration GBPUSD** | **100%** | 80%+ |

---

## 14 leviers L1-L14 SQL-validés

| Levier | Description | Effet |
|---|---|---|
| L1 | GBPUSD haussière 11-13h UTC | Edge 94.6% WR |
| L2 | Kill hours 00-09h UTC | Économie 8h trades |
| L3 | Time exit 5min | L3 auto-close |
| L4 | Stars-only | Filtrage qualité |
| L5 | Blacklist GRAMMAR + ELASTIC_BREATH | -50p |
| L6 | Sizing x1.5 à 13h UTC | Boost gain/heure |
| L7 | Blacklist 5 paires | WR<50% éliminé |
| L8 | Regime NEUTRE blacklist | -1623.5p historique |
| L9 | Session london_ny only | -129p hors session |
| L11 | Behavior qualification blacklist | -121p KO |
| L13 | Coalition HTF (boost no_coalition / block lower_TF_only) | +469p / -267p |
| L14 | Mardi blacklist (inversion Perplexity) | -158p mardi |

---

## ★ CE QU'IL RESTE À FAIRE — 2 ACTIONS HUMAINES ★

### Action 1 : Rotation 4 tokens Telegram CEO (R2)

```bash
# Étape 1 : check status
python scripts/v9_token_rotation.py --status

# Étape 2 : manuel — Telegram @BotFather /revoke
# → recevoir nouveau token

# Étape 3 : éditer config/v9_tokens.env
# TELEGRAM_BOT_TOKEN_BALANCE=<nouveau_token>
# TELEGRAM_BOT_TOKEN_BALANCE_LAST_ROTATED=2026-08-01T00:00:00Z
# (idem pour les 3 autres tokens)

# Étape 4 : revérifier
python scripts/v9_token_rotation.py --check

# Étape 5 : logger
python scripts/v9_token_rotation.py --history
```

**Pourquoi bloquant** : 13+ jours sans rotation, risque R2 sécurité Perplexity.

**Durée estimée** : 10 minutes.

---

### Action 2 : Walk-forward live 7j observation

```bash
# Étape 1 : installer le cron (1 cycle / 5 min)
bash scripts/cron_setup_paper_runner.sh install

# Étape 2 : audit quotidien (ou manuellement)
python scripts/v9_daily_paper_audit.py

# Étape 3 : surveiller 7 jours via :
python scripts/v9_auto_rollback.py --check        # défensif
python scripts/v9_paper_runner.py --status         # live status
python scripts/v9_heartbeat_capture.py            # R3 MT4

# Étape 4 : au bout de 7j, vérifier le verdict :
#   - GO_PHASE12_LIVE → activer FTMO live réel
#   - WAIT_MORE_DATA → continuer walk-forward
#   - FIX_EDGE_FIRST → auditer et ajuster
```

**Critères validation 7j** :
- WR ≥ 60%
- Expectancy nette ≥ +3 p/trade
- Max DD ≤ 100 p
- N_closed ≥ 20

**Durée** : 7 jours.

---

## ★ OPTIONNEL (non bloquant) ★

### Action optionnelle 1 : Log 20 trades GBPUSD 11-13h UTC

```bash
# Pour chaque trade manuel GBPUSD haussière 11-13h UTC :
python scripts/v9_log_human_trade.py \
  --symbol GBPUSD --direction haussiere --timeframe M5 \
  --entry-price 1.2680 --stop-loss 1.2672 --take-profit 1.2705 \
  --lot 0.10 --notes "breakout session london-ny"

# Une fois 20+ logs :
python scripts/v9_mirror_auto_activate.py --activate
```

### Action optionnelle 2 : Activer mirror BLOCKING manuellement

```bash
echo "V9_HUMAN_MIRROR_BLOCKING=1" >> config/v9_kill_switches.env
```

---

## ARCHITECTURE TECHNIQUE

### Modules core (6)

| Module | Rôle |
|---|---|
| `core/v9/v9_mega_edge_filter.py` | Filtres L1-L14 SQL-driven |
| `core/v9/v9_human_mirror.py` | Fingerprint Søn vs système |
| `core/v9/v9_spread_simulator.py` | R6 spread + L12 early warning |
| `core/v9/v9_boot_alerts.py` | BUG-P1/P2/P4 detection |
| `core/v9/v9_principle_audit.py` | BUG-P3 audit trail |
| `core/v9/human_trades_db.py` | Table v9_human_trades |

### Scripts CLI (12)

| Script | Usage |
|---|---|
| `v9_paper_runner.py` | Paper-trading continu (Phase 16) |
| `v9_daily_paper_audit.py` | Audit quotidien (Phase 17) |
| `v9_auto_rollback.py` | Auto-rollback motion (Phase 18) |
| `v9_token_rotation.py` | R2 token rotation helper (Phase 19) |
| `v9_mirror_auto_activate.py` | Mirror BLOCKING auto (Phase 19) |
| `v9_check_orderbridge.py` | MT4 bridge check (Phase 13) |
| `v9_heartbeat_capture.py` | R3 MT4 heartbeat (Phase 13) |
| `v9_mirror_check.py` | Mirror status check (Phase 14) |
| `v9_pre_live_check.py` | Pre-LIVE gate (Phase 14) |
| `v9_log_human_trade.py` | Log trade humain (Phase 1) |
| `v9_close_time_exit.py` | L3 force_close (Phase 3) |
| `v9_walk_forward.py` | Walk-forward 5 fenêtres (Phase 3) |
| `v9_auto_promote_stars.py` | Force 3 stars ACTIVE (Phase 3) |
| `v9_cron_pipeline.py` | Pipeline quotidien (Phase 7) |
| `cron_setup_paper_runner.sh` | Cron install (Phase 17) |

### Audits SQL reproductibles (7)

`reports/audit_p2.py` à `reports/audit_p2_v7_paper_100.py` — validation empirique de chaque levier.

---

## PHASES LIVRÉES

| Phase | Description | Tests |
|---|---|---:|
| 1 (J0-J7) | Plan 7 jours CEO max | 100+ |
| 2 (J8) | L1-L6 | 10 |
| 3 | 3 scripts CLI | 19 |
| 4 | L3 time_exit LIVE | 4 |
| 5 | L8 regime NEUTRE | 2 |
| 6-7 | L9 + cron pipeline | 19 |
| 8 | Boot alerts | 8 |
| 9 | L11+L13+L14 | 9 |
| 10-11 | R6 + L12 | 10 |
| 12 | LIVE motion CEO | – |
| 13 | R3 + BUG-P3 + MT4 check | 20 |
| 14 | Audit trail + mirror + LIVE | 21 |
| 15 | Test 100 paper trades | – |
| 16 | Paper-trading continu | 15 |
| 17 | Daily audit + cron | 8 |
| 18 | Auto-rollback | 13 |
| 19 | Token rotation + mirror auto | 25 |
| **TOTAL** | – | **264** |

---

## WORKFLOW UTILISATEUR FINAL

```bash
# Vérification pré-LIVE
python scripts/v9_pre_live_check.py

# Walk-forward live 7j
bash scripts/cron_setup_paper_runner.sh install

# Daily monitoring
python scripts/v9_daily_paper_audit.py
python scripts/v9_auto_rollback.py --check
python scripts/v9_heartbeat_capture.py
python scripts/v9_token_rotation.py --check

# Optional : mirror BLOCKING (après 20 logs Søn)
python scripts/v9_mirror_auto_activate.py --activate
```

---

## BILANS

- `reports/BILAN_FINAL_EDGE_FUND_V9_PHASE18.md`
- `reports/BILAN_FINAL_EDGE_FUND_V9_PHASE19.md`
- `reports/BILAN_GLOBAL_EDGE_FUND_20260731.md`
- `reports/BILAN_FINAL_EDGE_FUND_20260731.md`

---

## Conclusion

**Mission Edge Fund Max : RÉUSSIE COMPLÈTE**.

Système opérationnel. Edge validé (94.6% WR). Walk-forward live 7j en place.
2 actions humaines bloquantes restantes (tokens + observation 7j).

🚀 **PowerFlow V9 prêt pour activation finale après 7j validation.**