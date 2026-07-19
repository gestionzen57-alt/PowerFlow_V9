# Checklist pré-réouverture — 2026-07-19 §23h UTC

> **Objet** : filet de sécurité live avant la réouverture forex de ce soir
> (~22h UTC DST US). Livraison Opus « pré-réouverture » (3 chantiers R22).
> **Statut** : code prêt, **non poussé** (R28 — push via Hermes).
> **Doctrine** : R2 additif · R6 défensif · R7 tests verts · R30 recommande-ne-mute-pas.

---

## 1. Statut des 5 P0 (audit edgefund 2026-07-19)

| P0 | Description | Statut | Détail |
|----|-------------|--------|--------|
| **P0.1** | 4 tokens Telegram exposés (`8656…`, `8790…`, `8932…`, `8948…`) | ⚠️ **ACTION CEO** | Rotation @BotFather requise avant 22h UTC. Hors périmètre code. |
| **P0.2** | Watchdog sans appelant/cron/alerte/arrêt | ✅ **RÉSOLU** | Runner `scripts/v9_live_watchdog_run.py` + cron `V9_LiveWatchdogLoop` (5 min) + alerte Telegram + reco `V9_PAPER_TRADE_HALT`. |
| **P0.3** | Action critique = `V9_GBPUSD_LONG_ONLY=0` (désactive le garde, pas un arrêt) | ✅ **RÉSOLU** | Reco P0 = `V9_PAPER_TRADE_HALT=1` + `V9_NO_BAISSIERE=1`. `V9_GBPUSD_LONG_ONLY=0` blacklisté dans le runner. |
| **P0.4** | Modules critiques lisent `os.environ` au lieu de `kill_switches` | ✅ **RÉSOLU** | `v9_loop_breaker.py` + `v9_live_watchdog.py` lisent `core.v9.kill_switches` (fallback `os.environ`). |
| **P0.5** | Tâches Windows en échec (PaperTradeLoop lancé sans charger le `.env`) | ⚠️ **ACTION SØN** | `install_v9_paper_trade_loop_wrapper.bat` fourni (refit via wrapper). À exécuter sur le VPS après pull. |

---

## 2. Rotation des 4 tokens Telegram (action CEO uniquement)

> **Ne peut être fait que par Søn.** Le code ne stocke aucun token en clair après rotation.

1. Ouvrir Telegram → `@BotFather`.
2. Pour chaque bot concerné : `/revoke` → sélectionner le bot → confirmer.
3. `/token` → récupérer le nouveau token.
4. Mettre à jour `config/telegram.json` (valeur locale, **non commitée**).
5. (Optionnel) désindexer `config/telegram.json.bak.20260717` si nettoyage d'historique souhaité.

Tokens à révoquer : `8656…`, `8790…`, `8932…`, `8948…`.

---

## 3. Installation des 2 tâches Windows (action Søn, sur le VPS, après pull Hermes)

```bat
cd C:\projet\V9
git pull

REM 1) Cron watchdog live (5 min) — nouvelle tâche
scripts\install_v9_live_watchdog_cron.bat

REM 2) Refit PaperTradeLoop pour charger le .env (P0.4/P0.5) — backup auto
scripts\install_v9_paper_trade_loop_wrapper.bat
```

> Les deux scripts acceptent `--dry-run` pour afficher les commandes `schtasks`
> sans rien modifier (déjà validé côté dev).

---

## 4. Smoke test post-install (obligatoire avant 22h UTC)

```bat
.venv\Scripts\python.exe -X utf8 scripts\v9_live_watchdog_run.py --once --json
```

**Attendu** : `status` = `ok` **ou** `no_data` (post-réouverture, < 10 trades GBPUSD long
→ `no_data` est normal).

**NO-GO** : si `status` = `critical` **ou** `db_error` → **NE PAS OUVRIR**. Motion CEO pour
désactiver `V9_LIVE_WATCHDOG_ENABLED` ou investiguer la DB (télémétrie muette = danger).

Résultat smoke test côté dev (2026-07-19 10:19 UTC, DB live actuelle) :
`status=ok`, `wr_long_only_gbpusd=1.0` (50 trades), `net_pnl_24h_pips=-28.0`. ✅

---

## 5. Plan d'observation 24h (post-réouverture)

- **WR par heure** : `wr_long_only_gbpusd` doit rester ≥ 80 % (segment GBPUSD haussiere).
- **P&L net 24h** : `net_pnl_24h_pips` ne doit pas franchir −200 pips.
- **Alertes Telegram** : une alerte `WARN` ou `P0` = investiguer immédiatement.
- **Journal** : `logs/v9_live_watchdog.log` (JSONL, 1 ligne / run / 5 min).
- **Seuils** (dans `config/v9_kill_switches.env`) : DD −200, WR warn 0.80, WR crit 0.60, fenêtre 50.

Verdict du watchdog par statut :

| status | signification | code sortie | action |
|--------|---------------|-------------|--------|
| `disabled` | switch OFF | 4 | vérifier `V9_LIVE_WATCHDOG_ENABLED=1` |
| `no_data` | < 10 trades GBPUSD long | 0 | attendre, normal en début de session |
| `ok` | edge sain | 0 | RAS |
| `warn` | WR < 80 % ou P&L < −200 | 1 | surveiller de près |
| `critical` | WR < 60 % | 2 | **HALT** — appliquer `V9_PAPER_TRADE_HALT=1` |
| `db_error` | télémétrie muette | 3 | investiguer DB — traiter comme P0 |

---

## 6. Critères de NO-GO post-réouverture (à compléter en append-only après 23h UTC)

> Section vivante. Documenter ici, après 23h UTC, tout signal de NO-GO observé.

- [ ] Smoke test = `critical` ou `db_error` avant ouverture → NO-GO.
- [ ] WR GBPUSD long-only < 60 % sur ≥ 10 trades dans les 2 premières heures → HALT.
- [ ] P&L net 24h < −200 pips → couper `V9_TRADER_MINI_ENABLED`.
- [ ] Densité de trades anormale (loop breaker déclenche > 3×/h) → investiguer boucle.

_(observations 23h UTC → …)_

---

## 7. P0 résiduels (détectés hors périmètre de cette session — NE PAS fixer ici)

> Si un P0 supplémentaire est détecté, le documenter ici. Fix = motion CEO distincte (R22).

- _(aucun à ce stade)_

---

## 8. Blocages session

- _(aucun)_

---

**Rappel R28** : cette session prépare les commits ; **Hermes pousse**.
