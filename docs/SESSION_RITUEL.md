# SESSION_RITUEL.md — Rituel de Démarrage & Fin de Session

> **Mise à jour** : 07/08/2026 — Architect pass  
> **Usage** : Søn exécute ce rituel à chaque session de trading ou de développement.

---

## DÉMARRAGE SESSION TRADING (< 5 minutes)

### Étape 1 — Vérification Infrastructure

```bash
# DB fraîche ?
sqlite3 data/v9_forces.db \
  "SELECT symbol, timeframe, bar_time, is_closed_bar \
   FROM forces_snapshots ORDER BY bar_time DESC LIMIT 8;"
# ✅ Si bar_time < 15min → OK
# ❌ Si bar_time > 15min → vérifier cron MT4 EA

# Cron actif ?
crontab -l | grep v9
# ✅ Doit afficher entrée toutes les 5min

# Telegram actif ?
python scripts/test_telegram_alert.py
# ✅ Message test reçu sur téléphone
```

### Étape 2 — Lecture Contexte Marché

```
□ Session active ? (voir SOUL.md §7 table sessions)
□ News dans les 30min ? (forexfactory.com — rouge = NO TRADE)
□ Spread normal sur paires cibles ?
□ VIX / DXY tendance ? (contexte macro)
```

### Étape 3 — Lancer Scanner

```bash
# Scanner comportemental (signaux A1/A2/A3)
python scripts/run_scanner.py --session live --pairs EURUSD,GBPUSD,USDJPY

# Dashboard live
python scripts/dashboard_server.py
# Ouvrir : http://localhost:8080
```

### Étape 4 — Lecture Signaux

```
A1 → Alerter Søn immédiatement (WhatsApp + Telegram)
A2 → Surveiller + valider structure manuelle
A3 → Observer seulement, noter dans journal
NONE → Ignorer
```

---

## DÉMARRAGE SESSION DÉVELOPPEMENT (< 3 minutes)

```bash
# 1. Pull derniers commits
git fetch origin && git checkout feat/v9-foundation-clean && git pull

# 2. Lire state
cat docs/STATE.md
cat docs/SOUL.md | head -80  # sections 1 et 2

# 3. Smoke test
pytest tests/unit/ -x -q --tb=short 2>&1 | tail -20
# ✅ Doit être vert

# 4. Ouvrir DECISIONS_LOG.md pour contexte
tail -50 docs/DECISIONS_LOG.md
```

---

## PENDANT LA SESSION TRADING

```
⚡ Signal A1 reçu :
  1. Vérifier heure (session active ?)
  2. Vérifier news prochaines 30min
  3. Regarder structure manuelle sur TF signal
  4. Regarder TF supérieur (H4/D1) — trend aligné ?
  5. Entrée UNIQUEMENT si tous les points ✅
  6. Noter dans journal : heure, paire, niveau, raison

🚫 NE PAS trader si :
  - News rouge dans 30min
  - Session Asia hors USDJPY/AUDUSD
  - Spread > 2× normal
  - Dead Zone (21h-23h UTC)
  - Doute sur structure
```

---

## FIN DE SESSION TRADING

```
□ Fermer toutes les positions ouvertes (micro-lots Phase H seulement)
□ Screenshot dashboard signaux du jour
□ Note dans journal : N signaux A1/A2/A3, conditions marché
□ Envoyer rapport Telegram si configuré
```

---

## FIN DE SESSION DÉVELOPPEMENT

```bash
# 1. Tests finaux
pytest tests/ -x -q --tb=short

# 2. Mise à jour docs
# - docs/STATE.md : progress sprint
# - docs/DECISIONS_LOG.md : décisions prises

# 3. Commit
git add -A
git commit -m "[type](scope): description [R2][R7]"
git push origin feat/v9-foundation-clean

# 4. Vérifier sur GitHub
# https://github.com/gestionzen57-alt/PowerFlow_V9/tree/feat/v9-foundation-clean
```

---

## Contacts Urgence

| Situation | Action |
|-----------|--------|
| DB stale > 1h | Redémarrer EA MT4 + vérifier cron |
| Telegram muet | `python scripts/test_telegram_alert.py` |
| pytest rouge | Ne PAS pusher — fix d'abord (R7) |
| Signal A1 hors session | Ignorer (R10 — pas de revenge trade) |
| VPS down | Voir docs/vps_recovery/ |

---

## Journal Session (template)

```markdown
## Session [DATE] — [08:00-12:00 UTC London]

**Infrastructure** : DB fraîche ✅ | Cron OK ✅ | Telegram OK ✅
**Contexte macro** : DXY [tendance] | Session [London/NY]
**News importantes** : [EUR CPI 09:30 ⚠️]

**Signaux reçus** :
| Heure | Paire | Niveau | Direction | Action |
|-------|-------|--------|-----------|--------|
| 08:14 | EURUSD | A1 | BEARISH | Surveillé |
| 09:45 | GBPUSD | A2 | BULLISH | Ignoré (news) |

**Bilan** : N signaux | N validés manuellement | N exécutés
**Notes** : [observations marché, anomalies pipeline]
```

---

*Liens* : [SOUL.md](./SOUL.md) | [PIPELINE_MAP.md](./PIPELINE_MAP.md) | [LEVIER_HUB.md](./LEVIER_HUB.md)
