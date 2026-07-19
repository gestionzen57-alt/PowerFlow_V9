# 🎯 PROMPT OPUS CLAUDE CODE — Réouverture live 2026-07-19 §23h UTC

> **Auteur** : Perplexity (architecte externe V9) — 2026-07-19 16h53 CEST  
> **Source de vérité** : HEAD `cd21b11` — `feat/v9-foundation-clean`  
> **Doctrine** : R2 · R6 · R7 · R22 · R26 · R28

---

## ✅ MOTION CEO — À LIRE EN PREMIER

> **« go session réouverture 23h UTC — refit PaperTradeLoop + observation live + zone_diagnostics si stable »**  
> — Søn, 2026-07-19

Cette motion autorise :
1. Refit cron `V9_PaperTradeLoop` (P0.5)
2. Observation et monitoring live post-réouverture
3. Analyse `zone_diagnostics` **si et seulement si** les conditions de stabilité sont remplies (cf. §4)
4. Mise à jour documentaire (DECISIONS_LOG + STATE + BOARD)

Cette motion **n'autorise pas** :
- Activation des chantiers A/B/C (REGIME_GATE / CVaR / CVD)
- Activation de `V9_POSITION_MANAGER_ENABLED` ou `V9_MARKET_REGIME_GLOBAL_ENABLED`
- Toute modification de `core/v9/`, YAML principes, `config.py`, `order_executor.py`
- Phase 10, Phase 12 (gelées doctrine)

---

## 0. INITIALISATION OBLIGATOIRE

```bash
cd C:\projet\V9
git pull
.venv\Scripts\python.exe -X utf8 -m pytest tests/ -q --tb=line
```

**Baseline attendue** : ≥ 2283 tests collectés, 0 nouvelles régressions (10 fails préexistants tolérés, inchangés).  
**Si nouvelles régressions** → STOP immédiat, escalade Søn avant toute action.

Puis smoke test watchdog :

```bash
.venv\Scripts\python.exe -X utf8 scripts\v9_live_watchdog_run.py --once --json
```

**Attendu** : `status=ok` ou `status=no_data` (normal si < 10 trades GBPUSD long avant réouverture).  
**NO-GO** : si `status=critical` ou `db_error` → ne pas continuer, documenter et escalader.

---

## 1. CONTEXTE RÉEL (lire avant tout)

### Documents dans l'ordre

1. `docs/STATE.md` — état exécutif complet (sessions 17-19/07)
2. `workspace/perplexity/BOARD.md` — board de coordination
3. `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` — checklist P0/P1/P2
4. `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` — verdict MARGINAL→GO conditionnel
5. `workspace/perplexity/memory/DECISIONS_LOG.md` — 50 dernières lignes

### Kill switches au 19/07 13h UTC

| Kill switch | État | Toucher ? |
|---|---|---|
| `V9_GBPUSD_LONG_ONLY` | **1 (ON)** | ❌ Ne jamais désactiver |
| `V9_LIVE_WATCHDOG_ENABLED` | **1 (ON)** | ✅ Laisser ON |
| `V9_PAPER_TRADE_HALT` | 0 (OFF) | ✅ Seulement si watchdog alerte critical |
| `V9_BEAR_PERCEPTION_ENABLED` | 0 (SHADOW) | ❌ Ne pas activer ce soir |
| `V9_REGIME_GATE_ENABLED` | 0 (OFF) | ❌ Chantier A — ne pas toucher |
| `V9_KELLY_CVAR_ENABLED` | 0 (OFF) | ❌ Chantier B — NO-GO walk-forward |
| `V9_CVD_ENABLED` | 0 (OFF) | ❌ Chantier C — migration DB requise |
| `V9_POSITION_MANAGER_ENABLED` | 0 (OFF) | ❌ Décision CEO distincte |
| `V9_MARKET_REGIME_GLOBAL_ENABLED` | 0 (OFF) | ❌ Décision CEO distincte |
| `V9_EXECUTION_ENABLED` | **0 (INTERDIT)** | ❌ Fondateur — jamais |

### Performance de référence (smoke test 19/07 10h19 UTC)

- WR GBPUSD long-only : **100 %** (50 trades)
- P&L net 24h : **−28 pips** (marché fermé weekend — normal)
- Capture server : vivant port 31685
- `V9_PaperTradeLoop` : ⚠️ **KO depuis 12h50 UTC** (FILE_NOT_FOUND code -2147024894) → P0.5 à régler

---

## 2. ACTION P0 — Refit V9_PaperTradeLoop (priorité absolue)

> **En CMD admin sur le VPS.**

```bat
cd C:\projet\V9
git pull
scripts\install_v9_paper_trade_loop_wrapper.bat
```

**Vérification** :
```bat
schtasks /query /tn "V9_PaperTradeLoop" /fo LIST
```
Attendu : `Status: Ready`, `Last Result: 0`.

Si le script `.bat` échoue (erreur admin / chemin) :
1. Documenter l'erreur dans DECISIONS_LOG.md
2. Escalader à Søn — ne pas contourner manuellement

---

## 3. MONITORING POST-RÉOUVERTURE (à partir de 22h UTC)

### Check T+0 (réouverture immédiate)

```bash
# Premier snapshot frais ?
.venv\Scripts\python.exe -X utf8 scripts\v9_live_watchdog_run.py --once --json

# Capture server vivant ?
# Vérifier port 31685 LISTENING
```

Attendu : au moins 1 forces_snapshot dans les 10 min post-réouverture.

### Check T+1h

```bash
.venv\Scripts\python.exe -X utf8 scripts\v9_live_watchdog_run.py --once --json
```

Résultat à documenter dans DECISIONS_LOG.md :
- `status` (ok / warn / critical / no_data / db_error)
- `wr_long_only_gbpusd`
- `net_pnl_24h_pips`
- `n_trades_window`

### Seuils d'alerte

| Signal | Seuil | Action |
|---|---|---|
| WR GBPUSD long-only | < 60 % sur ≥ 10 trades | `V9_PAPER_TRADE_HALT=1` immédiat |
| WR GBPUSD long-only | < 80 % sur ≥ 50 trades | WARN — surveiller toutes les 15 min |
| P&L net 24h | < −200 pips | `V9_TRADER_MINI_ENABLED=0` |
| `db_error` watchdog | n'importe quand | Investiguer DB — traiter comme P0 |
| Loop breaker | > 3 déclenchements/heure | Investiguer boucle re-entry |
| Capture server mort | > 15 min sans snapshot | Restart + alerte Telegram |

---

## 4. CHANTIER OPTIONNEL — zone_diagnostics

**Conditions d'entrée** (toutes requises) :
- [ ] Smoke test T+0 = `ok` ou `no_data` ✅
- [ ] PaperTradeLoop refité, statut Ready ✅
- [ ] Premier snapshot frais reçu post-réouverture ✅
- [ ] WR long-only ≥ 80 % sur les premiers trades ✅

Si une condition manque → **ne pas ouvrir ce chantier ce soir**.

### Contexte

14 principes SHADOW débloqués (session ZCode 2026-07-15) mais jamais évalués sur données fraîches post-fix vote-devise (17/07). Potentiel de diversification identifié dans l'audit edgefund Axe 3 (EURUSD, USDJPY).

### Tâches (lecture avant écriture, R2 additif strict)

1. Identifier les 14 principes SHADOW dans `core/v9/principles/` (grep `status: SHADOW`)
2. Compter `n_triggered` live depuis le 17/07 (fix vote-devise)
3. **Si n_triggered < 20 sur tous** → documenter « signal insuffisant » et clore proprement
4. **Si n_triggered ≥ 20 sur au moins 1** → analyser WR par principe, lister candidats à promotion
5. Aucune promotion ACTIVE sans motion CEO distincte (R25'')

**Livrable** : section `## zone_diagnostics §[heure]` en append dans `workspace/perplexity/memory/DECISIONS_LOG.md`  
(pas de nouveau fichier si < 200 lignes)

---

## 5. LIVRABLE OBLIGATOIRE DE CETTE SESSION (R26)

Avant de clore la session, **1 commit** couvrant :

```
docs(v9): bilan réouverture 20/07 T+1h — [ok|warn|halt]
```

Contenu du commit :

1. **`workspace/perplexity/memory/DECISIONS_LOG.md`** — entrée §2026-07-19 23h UTC avec :
   - Résultat refit PaperTradeLoop (P0.5 résolu ou bloqué + raison)
   - Premier bilan T+0 et T+1h (status watchdog, WR, P&L, n_trades)
   - Observations anomalies / NO-GO le cas échéant
   - Résultat zone_diagnostics si exécuté

2. **`docs/STATE.md`** — mise à jour section "Phase actuelle" :
   - Statut cron PaperTradeLoop
   - État opérationnel post-réouverture
   - Verdict T+1h

3. **`workspace/perplexity/BOARD.md`** — resync date + statut global

---

## 6. CRITÈRES D'ESCALADE (STOP → Søn)

Si l'un de ces scénarios se produit → **STOP, documenter, attendre motion CEO** :

- WR live < 60 % sur les 10 premiers trades dès réouverture
- Capture server mort malgré restart watchdog
- Loop breaker > 3×/h
- PaperTradeLoop impossible à refiter (erreur admin persistante)
- Anomalie DB (corruption, tables manquantes)
- Découverte d'un nouveau P0 non documenté

Format d'escalade dans DECISIONS_LOG.md :
```
## ESCALADE §[heure UTC] — [description courte]
- Constat : ...
- Preuve : ...
- Action en attente : motion CEO
```

---

## 7. ANTI-HUBRIS

- **`no_data` en début de session est normal** — le marché vient de rouvrir, < 10 trades = insuffisant pour juger.
- **Un WR dégradé se documente sans minimiser.** Si T+1h montre WR < 80 %, dis-le clairement.
- **Tu peux proposer HALT.** Le watchdog recommande, il ne mute pas — mais ta recommandation d'appliquer `V9_PAPER_TRADE_HALT=1` est une action courageuse, pas un échec.
- **L'honnêteté prime sur le narratif rassurant.**

---

## 8. PÉRIMÈTRE GELÉ (rappel)

| Interdit | Raison |
|---|---|
| `core/v9/*.py` (sauf scripts/) | R22 — hors périmètre ce soir |
| Chantiers A/B/C (activation) | Kill switches OFF — validation T+7j |
| `config/v9_kill_switches.env` (sauf HALT si watchdog) | R30 |
| `core/v9/config.py` | R30 strict |
| `core/v9/order_executor.py` | Phase 12 gelée |
| YAML principes | R23 strict |
| Phase 10 / Phase 12 | Doctrine — ne jamais ouvrir |

---

*Prompt rédigé le 2026-07-19 16h53 CEST par Perplexity (architecte externe V9).*  
*Motion CEO intégrée : « go session réouverture 23h UTC »*  
*HEAD de référence : `cd21b11` — `feat/v9-foundation-clean`*
