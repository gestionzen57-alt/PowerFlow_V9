# 🏦 AUDIT PROMPT — Edge Fund Quantique Institutionnel — PowerFlow V10

> **Document :** Prompt d'audit autonome (format exécutable par IA ou auditeur humain)
> **Version :** 1.0 — 2026-08-06
> **Cible :** Évaluation objective de la préparation institutionnelle de PowerFlow V10
> **Doctrine de référence :** AGENTS.md (R1-R10), SOUL.md, HERMES_PROMPT_AUTOPILOT_QUANT.md

---

## 1. OBJECTIF DE L'AUDIT

Évaluer — sans complaisance et sans fabrication (R9) — dans quelle mesure le
système PowerFlow V10 est :
1. **Rigoureux quantitativement** (méthodes, backtesting, walk-forward, non-overfit)
2. **Protégé en capital** (R10 : DD max, position max, levier, kill switch)
3. **Auditable et reproductible** (chaque chiffre = 1 query SQL traçable, R6/R9/R14)
4. **Prêt pour un passage institutionnel** (gouvernance, transparence, reporting, scale)

L'audit ne doit **jamais** conclure sur la base d'un chiffre annoncé : il doit
**vérifier à la source** (DB, rapports JSON, git). C'est la règle d'or R9.

---

## 2. PÉRIMÈTRE D'AUDIT

| # | Domaine | Fichiers / sources de vérité |
|---|---------|------------------------------|
| A | Doctrine & gouvernance | `AGENTS.md`, `SOUL.md`, `DECISIONS_LOG.md` |
| B | Données & pipeline | `data/v9_forces.db`, `forces_snapshots`, `v10_signals_clean` |
| C | Stratégies & edge | `core/v10/v10_*.py`, `reports/v10_replay_batch_*.json` |
| D | Apprentissage & R8 | `v10_learning_state.db`, `reports/v10_learning_loop_*.json` |
| E | Risque (R10) | `v10_risk_shield.py`, `v10_net_exposure.py`, `v10_decision_pipeline.py` |
| F | Reporting & décisions | `data/v10_decisions.db`, `reports/v10_*.json` |
| G | Exécution live | crons Hermes, `v10_live_decision.py`, `v10_decision_log.py` |
| H | Reproducibilité & git | `git log`, tags, commits atomiques (R14) |

---

## 3. MÉTHODOLOGIE D'AUDIT (5 phases)

### Phase 1 — REVUE DE DOCTRINE (R1-R10)
- [ ] Vérifier que chaque règle R1-R10 est documentée et implémentée.
- [ ] Vérifier que R10 (seul vrai garde-fou) est strict : DD max 10%, position max
      2%, levier max 5x, kill switch manuel. **Zéro ordre réel sans `V9_EXECUTION_ENABLED==1`**.
- [ ] Identifier toute dérive entre doctrine documentée et code réel.

### Phase 2 — INTÉGRITÉ DES DONNÉES
- [ ] `count()` au lieu de `PRAGMA integrity_check` (DB > 5GB).
- [ ] Fraîcheur : `MAX(timestamp)` par `timeframe` dans `forces_snapshots`.
- [ ] Cohérence symboles : vérifier que `symbol`/`pair` est homogène (pas de casse
      variable, pas de doublons (closed_at, direction, pnl)).
- [ ] TZ : vérifier UTC ISO 8601 partout, jamais d'heure locale sans TZ.

### Phase 3 — VALIDITÉ QUANTITATIVE (anti-overfit)
- [ ] **Walk-forward** : les résultats replay sont-ils validés sur échantillon
      hors-échantillon ? (pas de look-ahead bias).
- [ ] **Taille d'échantillon** : chaque edge ≥ 50% est-il soutenu par n ≥ 30 trades ?
      (sinon → bruit).
- [ ] **Delta significatif** : chaque edge a-t-il Δ ≥ 2.0 pips ? (sinon → bruit, R10).
- [ ] **Replay vs live** : la performance live résolue (v10_decisions) est-elle
      cohérente avec le replay ? (si écart > 10 pts → méfiance).
- [ ] **Honnêteté R9** : tout WR/PnL annoncé est-il recalculé à la source ?
      (ex. PRICE_LAG annoncé WR100% mais en réalité perdant -805p/7j → exclu).

### Phase 4 — ROBUSTESSE DU RISQUE (R10)
- [ ] Vérifier que le bouclier R10 bloque : DD > 10%, position > 2%, levier > 5x,
      exposition nette par devise, doubles positions opposées, corrélation > 0.7.
- [ ] Vérifier que l'edge selector ne trade que les edges validés (WR ≥ 50%,
      n ≥ 30, Δ ≥ 2.0, direction dominante).
- [ ] Vérifier le fail-open R6 : toute erreur → WAIT (pas de crash, pas d'ordre risqué).

### Phase 5 — PRÉPARATION INSTITUTIONNELLE
- [ ] **Gouvernance** : qui décide (CEO Søn = stratégique, Hermes = opérationnel) ?
      kill switch documenté et accessible ?
- [ ] **Transparence** : chaque décision est-elle journalisée (R6) + notifiée
      (Telegram) ? chaque chiffre est-il traçable (R9) ?
- [ ] **Reproductibilité** : chaque changement = 1 commit atomique (R14) ?
      git = source de vérité ?
- [ ] **Reporting** : rapports nocturne / hebdo / edges / bilan existent-ils et
      sont-ils actionnables ?
- [ ] **Scalabilité** : le pipeline supporte-t-il plusieurs paires×TF sans
      dégradation ? (perf, mémoire, DB).

---

## 4. LIVRABLES D'AUDIT

L'audit doit produire **un rapport structuré** avec :
1. **Score global** (0-100) par pilier : Données, Quant, Risque, Gouvernance, Scale.
2. **Verdict par critère** : ✅ PASS / ⚠️ WARN / ❌ FAIL (avec preuve à la source).
3. **Liste des findings** classés par sévérité : Critique / Majeur / Mineur.
4. **Recommandations actionnables** (chacune liée à une règle R#).
5. **Conclusion** : « Prêt pour institution ? OUI / NON / CONDITIONNEL » + justification.

**Règle d'or** : pour chaque affirmation chiffrée, citer la query SQL ou le
rapport JSON exact qui la prouve. Aucun chiffre inventé. Toute donnée
non vérifiable → marquée « NON VÉRIFIABLE ».

---

## 5. EXEMPLE DE GRILLE DE SCORE

| Pilier | Poids | Critère clé | Seuil PASS |
|--------|-------|-------------|------------|
| Données | 15% | Fraîcheur + cohérence | MAX(ts) < 1h, symboles homogènes |
| Quant | 25% | Walk-forward + n ≥ 30 + Δ ≥ 2p | Pas de look-ahead, edges soutenus |
| Risque | 30% | R10 strict exercé | DD halt, position max, opposées bloquées |
| Gouvernance | 15% | Kill switch + git + reporting | Décisions journalisées, R14 |
| Scale | 15% | Perf multi-paires×TF | Pas de dégradation, DB saine |

**Score global = Σ(poids × score_pilier)**, avec pénalité automatique à 0/100
si un FAIL critique R10 est trouvé (capital non protégé = échec institutionnel).

---

## 6. INSTRUCTIONS À L'AUDITEUR (IA ou humain)

> **Tu es un auditeur indépendant d'edge fund quantique.** Tu ne fais confiance
> à aucun chiffre annoncé. Tu vérifies tout à la source. Tu es impitoyablement
> honnête (R9) : toute donnée non vérifiable est marquée comme telle, toute
> performance non reproduisible est un FAIL. Tu produis un rapport Markdown
> structuré, chiffré, et actionnable, destiné au CEO (Søn) pour décision.

---

## 7. CHAMPS OBLIGATOIRES DU RAPPORT

```markdown
# RAPPORT D'AUDIT — PowerFlow V10 — <date>

## Score global : <0-100>/100 — <OUI/NON/CONDITIONNEL>

## 1. Données            : <score>/100 — <verdict>
## 2. Quant              : <score>/100 — <verdict>
## 3. Risque (R10)       : <score>/100 — <verdict>
## 4. Gouvernance        : <score>/100 — <verdict>
## 5. Scale              : <score>/100 — <verdict>

## Findings
### CRITIQUE
- [ ] ...
### MAJEUR
- [ ] ...
### MINEUR
- [ ] ...

## Recommandations (liées aux règles R#)
1. ...

## Conclusion
<OUI / NON / CONDITIONNEL> — <justification chiffrée>
```

---

## 8. VÉRIFICATIONS SOURCE (bonnes pratiques)

| Vérification | Commande / query |
|--------------|------------------|
| Fraîcheur data | `SELECT MAX(timestamp) FROM forces_snapshots GROUP BY timeframe` |
| Compte tests | `python -m pytest tests/test_v10_*.py -q --no-header` |
| État décisions | `SELECT COUNT(*), SUM(is_win) FROM v10_decisions` |
| État edges | `python scripts/v10_replay_batch.py --limit 200` (edge_map) |
| État apprentissage | `python scripts/v10_learning_loop.py --limit 100` |
| Boucle R8 | `python scripts/v10_closed_loop.py` |
| Audit V9→V10 | `python scripts/v10_v9_principles_audit.py` |
| Rapport nuit | `python scripts/v10_night_summary.py` |

---

*Fin du prompt d'audit. L'auditeur est libre de creuser tout domaine au-delà de cette grille si une anomalie est détectée.*
