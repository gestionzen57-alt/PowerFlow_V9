# PROMPT PERPLEXITY PHASE 2 — Recherche 10 nouveaux leviers SQL

**Branche** : `feat/v9-foundation-clean` (HEAD `c55d916`, 18 commits Phase 1-8)
**Accès Perplexity** : Git only (no DB, no MCP, no runtime)
**Mission** : Proposer 10 leviers additionnels non-explorés.

---

## CONTEXTE DÉJÀ EXPLORÉ (Phase 1-8)

Hermes a implémenté **9 leviers SQL-driven** basés sur audit direct de `data/v9_forces.db` :

| L | Levier | Source |
|---|---|---|
| L1 | GBPUSD haussière 11-13h UTC | audit 90j, 74 trades WR 94.6% +336p |
| L2 | KILL_HOUR UTC 00-09h | -265p / 60 trades GBPUSD haussière |
| L3 | TIME_EXIT < 5min | trades 5-30min = -239p |
| L4 | STARS-ONLY (PRICE_LAG/POWER_ANGLE/GRAVITY) | 76 trades WR 100% +440p |
| L5 | BLACKLIST GRAMMAR+ELASTIC_BREATH | 21 trades WR 33% -39p |
| L6 | SIZING_BOOST 13h UTC x1.5 | 34 trades WR 94.1% +184p |
| L7 | BLACKLIST 5 paires (USDCAD/AUDUSD/USDJPY/EURUSD/USDCHF) | -474p non-GBPUSD |
| L8 | BLACKLIST regime NEUTRE | 494 trades WR 25.1% -1623.5p |
| L9 | BLACKLIST hors london_ny 11-14h | asia/other = -129p |

**Tables DB exploitées** : `paper_trades`, `forces_snapshots`, `decisions`, `regime_snapshots` (regime_type, vol_regime, palier_duration_bars, delta_vol), `behaviors`, `signals`, `principles`, `cognitive_journal`.

---

## TABLES NON-EXPLORÉES (candidates L10-L19)

Tu peux trouver 10 nouveaux leviers en explorant ces zones :

### Zone A — CVD / Micro-structure (fort potentiel)

- `cvd_snapshots` (Customer Volume Delta) : déployé mais **non consommé** par les principes YAML
  - L11 (Perplexity Phase 1) : condition YAML optionnelle `cvd_divergence >= 0.3` sur PRICE_LAG
  - **À creuser** : corrélation CVD × outcome trade ? CVD divergence → retournement ?
  - **Question** : y a-t-il un seuil `cvd_zscore > X` qui prédit WR ≥ 80% ?

### Zone B — Comportement (`behaviors.qualification`)

- Jointure `paper_trades × behaviors` via `snapshot_id`
  - Schéma : `behaviors` (id, scene_id_ref, snapshot_id, qualification, ...)
  - **À creuser** : y a-t-il un `qualification` (ex: `high_quality`, `low_quality`, `noise`) qui prédit WR ?
  - **Question** : filtrer sur qualification `high_quality` ?

### Zone C — Palier / Consolidation

- `regime_snapshots.palier_duration_bars`, `palier_level`, `palier_start_ts`
  - **À creuser** : `palier_duration_bars > 100` (long palier) vs < 20 (court) sur GBPUSD haussière 11-14h ?
  - **Question** : sortir d'un palier long → breakout → meilleur WR ?

### Zone D — Coalition / HTF (Higher Time Frame)

- Tables `scenes` et `windows` contiennent les informations de coalition multi-TF
  - **À creuser** : trade avec coalition HTF (D1/H4) alignée vs sans ?
  - **Question** : `coalesced_strength > X` → WR plus élevé ?

### Zone E — `cognitive_journal` (events narratifs)

- Table qui stocke les events du système (calibration, promotion, etc.)
  - **À creuser** : corrélation entre événements récents et WR des trades suivants
  - **Question** : trades qui suivent un `auto_calibrator` event sont-ils plus/win ou moins/win ?

### Zone F — Symboles non-blacklistés

- `AUDUSD`, `EURUSD`, `USDCHF` sont blacklistés (L7), MAIS :
  - **À creuser** : `EURUSD baissière 13-15h UTC` (rare, peut être profitable)
  - **À creuser** : `AUDUSD haussière 06-08h UTC` (session Sydney) — spéculatif mais Perplexity Phase 1 l'a suggéré
  - **Question** : quel edge existe-t-il hors GBPUSD haussière ?

### Zone G — Jour de la semaine / Effet calendrier

- `strftime('%w', opened_at)` retourne jour semaine (0=dim, 6=sam)
  - **À creuser** : mardi/jeudi sont-ils plus profitables que vendredi ?
  - **Question** : effet "mercredi FOMC" ou "vendredi NFP" visible dans les pips ?

### Zone H — Conflits entre principes (cross-correlation)

- 2 principes stars ensemble = meilleur WR ? Ou trop de bruit ?
  - **À creuser** : `PRICE_LAG + POWER_ANGLE` (audit Phase 1 = 100% sur 17 trades) → confirmer
  - **Question** : 3 stars ensemble = win ou dilution ?

### Zone I — Volatilité implicite / ATR

- `regime_snapshots.vol_atr_pips`, `vol_regime_level`
  - **À creuser** : trades pris pendant `vol_regime_level=high` (forte volatilité) ?
  - **Question** : high vol → run continu → plus de profit ?

### Zone J — Recovery post-drawdown

- Trades qui suivent une série de pertes
  - **À creuser** : si 3 pertes d'affilée (déjà filtré par J2 anti-série), que se passe-t-il trade 4 ?
  - **Question** : revenge trading pattern observable ?

---

## FORMAT DU RAPPORT ATTENDU

Crée `PERPLEXITY_LEVIERS_PHASE_2.md` avec ce format :

```markdown
# Perplexity Phase 2 — 10 Nouveaux Leviers SQL-Driven

## Méthodologie

Audit statique feat/v9-foundation-clean (c55d916). Pas d'accès DB.
Leviers proposés basés sur inférence architecturale + patterns hedge fund
quantitatifs connus.

## Leviers proposés

### L10 — [Nom court]
**Zone** : [A-J ci-dessus]
**Hypothèse** : [1 phrase]
**SQL théorique** : [snippet SQL]
**Impact attendu** : [qualitatif : -X% volume, +Y% WR]
**Risque** : [edge case qui pourrait casser]
**Implémentation estimée** : [combien de temps + fichiers touchés]

### L11 — ...

## Bugs latents restants

[Si tu trouves d'autres bugs non-P1-P5]

## Risques non-explorés

[Nouveaux risques pour Phase 12 LIVE]

## Recommandation priorité

[Top 3 leviers à implémenter en premier]
```

---

## COMMANDES POUR PERPLEXITY

```bash
cd /tmp
git clone -b feat/v9-foundation-clean https://github.com/gestionzen57-alt/PowerFlow_V9.git v9-audit-p2
cd v9-audit-p2
git log --oneline -25
git show HEAD:core/v9/v9_mega_edge_filter.py | head -300
git show HEAD:config/v9_kill_switches.env | head -50
git show HEAD:core/v9/principle_engine.py | head -200
```

---

## CONTRAINTES

- ❌ Pas de code Python (tu n'as pas l'env)
- ❌ Pas de tests pytest (sans exécution)
- ❌ Pas de modification de fichiers
- ✅ Audit statique uniquement
- ✅ Inférence depuis code + docs + audit patterns
- ✅ Ponde `PERPLEXITY_LEVIERS_PHASE_2.md` à la racine du repo
- ✅ `git format-patch -1 --stdout > /tmp/perplexity_leviers.patch`
- ✅ Envoie à Søn via Telegram (pas push origin, R28)

---

## AIDE À L'EXÉCUTION POUR SØN

1. **Copie ce prompt** dans Perplexity (mode Kimi K3)
2. **Ajoute** : "Voici mon prompt. Tu n'as accès qu'au Git. Pondre le rapport .md et le patch. Réponds avec le contenu du patch + le rapport."
3. **Attends** 5-10 min
4. **Colle** la réponse ici → je review et merge les 10 leviers si pertinents
5. **Phase 9** = implémentation des top 3 leviers Perplexity Phase 2

---

**Date** : 2026-07-31
**Auteur** : Hermes (Phase 8 livré, checkpoint complet)
**Mission Perplexity** : 10 nouveaux leviers SQL-driven sur zones non-explorées