# 📊 Monitoring V9_GBPUSD_LONG_ONLY — Suivi opérationnel


> **Note CEO 2026-07-18** : MT4 = plateforme de lecture de l'indicateur SDI (ticks/volumes spécifiques). MT5 n'est PAS implémenté.

> **Créé le** : 2026-07-18 09:14 UTC
> **Motion CEO** : « Activer V9_GBPUSD_LONG_ONLY=1 en priorité »
> **Référence** : `DECISIONS_LOG.md` §6.10
> **Statut** : 🟢 ACTIF (kill switch ON)

---


> **NOTE 2026-07-18 09:31 Paris (samedi)** : Le marché Forex est **FERMÉ**
> depuis vendredi 22:00 UTC (= samedi 01:00 Paris CEST). **Pas un bug** —
> le capture server est sain, le marché dort. **Réouverture dimanche 22:00 UTC**
> (= lundi 00:00 Paris CEST). Ne pas alerter avant cette date.
>
> **Infrastructure VPS** : tout le runtime PowerFlow V9 (capture_server, daemon,
> cron, EA MT4) tourne sur le VPS depuis ~1 semaine, plus sur le PC local.
> Quand Søn dit « je vais redémarrer », c'est du VPS qu'il parle.

---

## 🎯 Objectif du monitoring

Suivre l'impact de `V9_GBPUSD_LONG_ONLY=1` sur la performance GBPUSD après
activation, pour décider :

1. **Maintenir** l'activation si l'edge haussier se confirme (WR ≥ 95%)
2. **Désactiver** si l'edge casse (WR < 80%)
3. **Ajuster** si la volatilité augmente (réduire sizing, etc.)

---

## 📊 Métriques à tracker

### Métriques primaires (toutes les 24h)

| Métrique | Formule | Cible | Seuil critique |
|---|---|---|---|
| **WR GBPUSD haussier** | wins / total | ≥ 95% | < 80% |
| **Pips GBPUSD cumulé** | SUM(pips_simulated) | > 0 (croissant) | < -1000 pips/jour |
| **Trades GBPUSD ouverts** | COUNT WHERE closed_at IS NULL | 0-3 | > 10 |
| **Drift GBPUSD** | drift quotidien calculé | > 0 (haussier) | < -20 pips/jour |
| **long_only_override_count** | COUNT dans paper_trades | 1-10 / jour | > 50 / jour |

### Métriques secondaires

| Métrique | Pourquoi |
|---|---|
| **Corrélation haussier GBPUSD vs autres paires haussières** | Détecter si l'edge est isolé ou général |
| **P95 amplitude M5 GBPUSD** | Détecter changement de régime |
| **Vol_regime moyen** | Basse vol = edge fragile |
| **Session breakdown** (new_york / overlap / london / asie) | Identifier la session la plus rentable |
| **Time exit moyen** (avant TP/SL) | Adapter le sizing |

### Métriques de garde (anti-régression)

| Métrique | Seuil | Action |
|---|---|---|
| Crash ou exception dans trade_engine | 0 par jour | Alerte immédiate |
| Kill switch désactivé involontairement | non | Alerte si V9_GBPUSD_LONG_ONLY!=1 |
| Trades GBPUSD ouverts > 24h | 0 | Skip / close manuel |

---

## 📅 Timeline de validation

### Phase immédiate (T+0 à T+7 jours)

- **T+0** (2026-07-18 09:14 UTC) : activation du kill switch
- **T+1h** : batch paper-trade de validation (déjà 0 trade ouvert — capture server mort)
- **T+24h** : 1er snapshot de métriques (dès que capture server tourne)
- **T+7j** (2026-07-25) : revue hebdomadaire, décision maintenir/désactiver

### Phase court terme (T+7 à T+30 jours)

- **T+14j** : 2e revue, mesure dérive WR haussier
- **T+30j** (2026-08-17) : 1er rapport mensuel long-only
- Métriques cibles :
  - WR haussier ≥ 95% sur les 30 jours
  - Pips cumulés > +500
  - Drift GBPUSD reste > 0

### Phase moyen terme (T+30 à T+90 jours)

- **T+60j** : décision activation Phase B (BearPerception SHADOW → ON)
- **T+90j** (2026-10-17) : 1er rapport trimestriel
- Si WR haussier reste > 95% : activer Phase B
- Si edge casse : désactiver long-only, audit root cause baissier

---

## 🔧 Commandes de monitoring

### Snapshot live (instantané)

```bash
# Vérifier l'activation
source config/v9_kill_switches.env && echo "V9_GBPUSD_LONG_ONLY=$V9_GBPUSD_LONG_ONLY"

# Stats baissier live
PYTHONPATH=. python -c "
from core.v9.v9_bear_dashboard import bear_stats
import json
print(json.dumps(bear_stats(r'C:\projet\V9\data/v9_forces.db', 'GBPUSD'), indent=2, default=str))
"

# Dashboard API (si uvicorn tourne)
curl http://127.0.0.1:8765/api/bear-stats | python -m json.tool
```

### Batch paper-trade (rejouer le cycle)

```bash
source config/v9_kill_switches.env
python scripts/v9_supervisor.py --paper-trade
```

### Test isolation long_only

```python
import os; os.environ['V9_GBPUSD_LONG_ONLY'] = '1'
from core.v9.trade_engine import _gbpusd_long_only_enabled
assert _gbpusd_long_only_enabled() == True
```

---

## 📋 Critères GO / NO-GO

### 🟢 GO — Maintenir l'activation

- WR haussier GBPUSD ≥ 95% sur 30 jours
- Pips cumulés > +500
- Drift GBPUSD reste > 0
- Pas de crash ou d'exception
- Vol_regime reste dans la normale

### 🟡 HOLD — Surveiller de près

- WR haussier GBPUSD entre 85% et 95%
- Pips cumulés entre 0 et +500
- Drift GBPUSD faiblit (< +10 pips/jour)
- Vol_regime change

### 🔴 NO-GO — Désactiver immédiatement

- WR haussier GBPUSD < 80% sur 14 jours consécutifs
- Pips cumulés < -1000 pips
- Drift GBPUSD devient baissier (< -20 pips/jour)
- Crash ou boucle d'erreur dans trade_engine

---

## 🔄 Procédure de désactivation (si NO-GO)

```bash
# 1. Désactiver le kill switch (instantané)
sed -i 's/V9_GBPUSD_LONG_ONLY=1/V9_GBPUSD_LONG_ONLY=0/' config/v9_kill_switches.env

# 2. Documenter dans DECISIONS_LOG §6.11
# "Désactivation V9_GBPUSD_LONG_ONLY, motif : WR < 80% sur 14 jours"

# 3. Rollback : tous les trades GBPUSD reprennent direction normale
# (l'arbiter peut maintenant émettre baissier de nouveau)

# 4. Audit root cause baissier
python scripts/v9_re_resolve_trades.py
PYTHONPATH=. python core/v9/v9_movement_analyzer.py --symbol GBPUSD --report
PYTHONPATH=. python core/v9/v9_speed_bias_analyzer.py --all
```

---

## 📚 Références croisées

| Document | Section |
|---|---|
| `DECISIONS_LOG.md` | §6.10 (activation), §6.9 (Phase A baissier) |
| `docs/LECTURE_MARCHE_ASYMETRIE_2026-07-18.md` | section "Activation long-only GBPUSD" |
| `docs/audit/BAISSIER_AUDIT_FINAL_2026-07-18.md` | 9 sections, métriques avant |
| `core/v9/v9_bear_dashboard.py` | source du dashboard baissier |
| `core/v9/trade_engine.py` | section 1b (code long_only) |
| `config/v9_kill_switches.env` | ligne `V9_GBPUSD_LONG_ONLY=1` |

---

## 🎯 Métriques live (snapshot au 2026-07-18 09:14 UTC)

```
V9_GBPUSD_LONG_ONLY : 1 ✅ ACTIF
V9_BEAR_PERCEPTION_ENABLED : 0 (shadow, Phase B)
V9_CONSTITUTIVE_CURRENCY_FILTER : 0 (gated R22)
V9_DYNAMIC_RISK_ENABLED : 1 ✅ ACTIF
V9_BLACKLIST_SYMBOLS : USDCAD

WR GBPUSD haussier : 100% (1088 trades historique)
WR GBPUSD baissier : 1.0% (3689 trades) — puits neutralisé par long_only
Drift GBPUSD actuel : -33.5 pips/jour (drift actuel < 30 = skip Phase B inactif)

Capture server : MORT depuis 9h (dernier bar M5 = 23:57 UTC)
Action requise : redémarrer capture_server.py
```

---

*Document de monitoring créé le 2026-07-18 09:14 UTC par Hermes sur motion CEO.*
*À mettre à jour quotidiennement pendant 7 jours, puis hebdomadairement.*
*"Mesurer ce qui compte, désactiver ce qui ne marche pas, activer ce qui marche."*