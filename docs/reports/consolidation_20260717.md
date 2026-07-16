# Consolidation post-DIVERSIFY — 2026-07-17

**Auteur** : Opus (mission VALIDATION + CONSOLIDATION)
**Pour** : Søn (CEO / HITL)
**HEAD** : `87c7a74` fix(v9): vote-devise NZD — index UNIQUE tronqué collapse les 8 devises
**Branche** : `feat/v9-foundation-clean`

---

## TL;DR — La vérité chiffrée

Le système est **structurellement sain** et **génère des signaux**. Mais la
question « est-ce que tout tient vraiment la route ? » a une réponse nuancée :

- ✅ **GBPUSD est le seul actif validé** : espérance **+5.53 pips/trade** sur
  8426 trades résolus (WR 85.6 %). Économie réelle et positive.
- ⚠️ **Cette validation est fragile** : **93 % des trades résolus proviennent
  d'une seule journée** (2026-07-08). Le 2026-07-07 fut **perdant** (WR 34 %,
  −0.55 pip). Le système n'est pas encore prouvé sur des régimes variés.
- 🔴 **Les 4 nouvelles paires ne sont PAS validables** : USDJPY, USDCAD,
  USDCHF, EURUSD n'ont **0 trade résolu** (données depuis ~4 h seulement, aucun
  `preparer_entree` encore résolu). Toute comparaison de rentabilité est
  prématurée.
- 🟡 **Les 4 SHADOW restent en observation** : triggering sain mais **0 trade
  résolu** → WR inconnu → **maintenus SHADOW** (règle mission : n<10 → +24 h).
- ✅ **Seuils par paire : non nécessaires côté forces** — les forces devises
  sont sur la **même échelle 0-100** pour les 5 paires. La crainte « USDJPY
  ×100 » est infondée pour les seuils de forces.

**Décision de fond : on ne passe PAS en production (VPS) cette semaine.** Il faut
d'abord ≥24-48 h de trades résolus sur les 4 nouvelles paires + une seconde
journée GBPUSD hors régime du 07-08.

---

## 1. État du système

| Élément | Valeur |
|---|---|
| HEAD | `87c7a74` |
| Snapshots totaux | 121 359 |
| Décisions totales | 69 666 |
| Dernier snapshot | 2026-07-16 23:10 UTC |
| Paires envoyant des données | 5 (GBPUSD + USDJPY + USDCAD + USDCHF + EURUSD) |
| Principes ACTIVE | 44 |
| Principes SHADOW | 9 (dont 4 en observation DIVERSIFY) |
| Boucle fermée | ✅ génère des signaux (72 `preparer_entree` le 07-16) |
| Tests | 1502 passed, 1 skipped ✅ |

---

## 2. Performances par paire

> **Impossible de livrer le tableau comparatif demandé** : 4 paires sur 5 ont
> **0 trade résolu**. Voici la réalité brute.

| Paire | Snapshots | 1er snapshot | Décisions | `preparer_entree` | Trades résolus | WR | Exp. pips |
|---|---:|---|---:|---:|---:|---:|---:|
| **GBPUSD** | 118 014 | 2026-07-05 | 68 054 | 8 498 | **8 426** | **85.6 %** | **+5.53** |
| USDJPY | 1 143 | 2026-07-16 19:01 | 465 | 0 | 0 | — | — |
| USDCHF | 653 | 2026-07-16 19:24 | 413 | 0 | 0 | — | — |
| USDCAD | 731 | 2026-07-16 19:07 | 390 | 0 | 0 | — | — |
| EURUSD | 818 | 2026-07-08 | 345 | 0 | 0 | — | — |

**Lecture** : les 4 nouvelles paires n'ont que ~4 h de vie et n'ont pas encore
produit un seul signal d'entrée résolu. Les questions « USDJPY aussi rentable
que GBPUSD ? », « USDCAD diversifie-t-il ? », « EURUSD/USDCHF redondants ? »
sont **sans réponse chiffrée possible aujourd'hui**. Il faut attendre la
matière.

### 2.1 GBPUSD — anatomie économique (le seul terrain validable)

| is_win | n | avg pips | plage |
|---|---:|---:|---|
| Gagnants | 7 211 | **+7.96** | +0.1 → +9.5 |
| Perdants | 1 215 | **−8.93** | −15.5 → 0 |

- **Espérance = 0.856 × 7.96 + 0.144 × (−8.93) = +5.52 pips/trade.** Positif et
  cohérent avec l'`avg_pips` global (+5.53).
- Ratio gain/perte ≈ 8 / 9 → la rentabilité tient sur un **WR élevé**, pas sur
  un gros R:R. Le système est donc **sensible à toute dégradation du WR**.
- Par stratégie de résolution : `DYNAMIC` n=8134 WR **88.7 %** ; `SKIPPED`
  n=292 WR 0 % (comptés perdants — tirent le WR agrégé vers le bas).

### 2.2 ⚠️ Le point qui change tout — concentration temporelle

| Jour | Trades résolus | WR | Exp. pips |
|---|---:|---:|---:|
| 2026-07-06 | 3 | 0 % | 0 |
| 2026-07-07 | 605 | **34.4 %** | **−0.55** |
| **2026-07-08** | **7 815** | **89.6 %** | **+6.00** |
| 2026-07-14 | 3 | 100 % | +4.5 |

**93 % des trades résolus (7 815 / 8 426) datent du 2026-07-08.** Le WR global
de 85.6 % est en réalité **le WR d'une seule journée de marché favorable**. Le
07-07, jour précédent, était **perdant**. Conclusion honnête : GBPUSD est
**prometteur mais non robuste** — il n'a pas été prouvé sur plusieurs régimes.

> Les 72 `preparer_entree` du 07-16 sont **en attente de résolution** (batch
> récent, le prix n'a pas encore atteint TP/SL, marché fermé depuis 23:10).
> À surveiller : le résolveur doit les fermer à la réouverture — c'est le test
> de vie de la boucle fermée.

---

## 3. SHADOW — décision (Priorité 0)

Les 4 principes rétrogradés lors de DIVERSIFY, triggering observé depuis
2026-07-16 ~21:50 (fenêtre d'observation ≈ 1 h 20, pas « J-2 ») :

| Principe | Triggers (toutes paires) | Conf. moy. | Trades résolus | WR |
|---|---:|---:|---:|---:|
| ADAPTIVE_VOL_GATE | 1 032 | 72.6 | 0 | — |
| ANTAGONIST_NODE | 264 | 60.0 | 0 | — |
| GRAMMAR_LOCK | 126 | 60.0 | 0 | — |
| GRAMMAR_RESPIRATION | 126 | 60.0 | 0 | — |

**Décision : les 4 restent SHADOW.**

- Critère mission (WR>50 % sur n≥10) : **non satisfiable** — 0 trade résolu.
- Critère config DIVERSIFY (taux de déclenchement sain, R25') : **partiellement
  atteint** — ils se déclenchent tous à des taux normaux et confiance saine.
- Mais promouvoir des principes dans la boucle cognitive live sur **1 h 20 de
  triggers non résolus** serait prématuré et difficilement réversible.

**`config.py` NON modifié** (ni `PRINCIPLE_ACTIVE_IDS` ni
`AUTO_PROMOTION_EXCLUDE`). Garde-fou respecté.

**Re-vérification à lancer après ≥24-48 h de trades résolus :**
```sql
SELECT pe.principle_id, COUNT(d.is_win) n, ROUND(AVG(d.is_win)*100,1) wr
FROM principle_evaluations pe
JOIN decisions d ON d.snapshot_id = pe.snapshot_id
WHERE pe.principle_id IN ('ANTAGONIST_NODE','GRAMMAR_LOCK',
      'GRAMMAR_RESPIRATION','ADAPTIVE_VOL_GATE')
  AND pe.triggered=1 AND d.is_win IS NOT NULL
GROUP BY pe.principle_id;
```
Si WR>50 % sur n≥10 → retirer de `AUTO_PROMOTION_EXCLUDE` + réintégrer dans
`PRINCIPLE_ACTIVE_IDS`.

---

## 4. Seuils par paire (Priorité 2)

**Constat structurel** : les forces devises (`force_usd`, `force_jpy`, …) sont
sur la **même échelle 0-100 pour les 5 paires** (moyennes 07-16 21h+) :

| Paire | force_usd | force_jpy | force_cad | force_eur | force_chf | force_gbp |
|---|---:|---:|---:|---:|---:|---:|
| USDJPY | 49.2 | 43.2 | 45.1 | 41.9 | 43.3 | 48.5 |
| USDCAD | 47.8 | 40.5 | 47.8 | 43.8 | 43.3 | 46.4 |
| USDCHF | 53.1 | 45.8 | 52.7 | 43.6 | 40.3 | 50.2 |
| GBPUSD | 52.8 | 50.6 | 55.6 | 44.1 | 40.3 | 48.6 |
| EURUSD | 51.7 | 41.8 | 48.8 | 42.9 | 40.7 | 52.7 |

**Conséquence** : les seuils basés sur les forces
(`COALITION_THRESHOLD=5.38`, `ANTAGONISM_THRESHOLD=31.39`) opèrent sur des
grandeurs **comparables entre paires** → **pas de rescaling ni de seuils par
paire nécessaires** côté forces. Le « ×100 JPY » concerne le **prix** (pips),
pas les forces.

**Ce qui reste réellement pair-spécifique** : valeur du pip, spread, et les
distances TP/SL en pips. Mais avec **0 trade résolu** sur les 4 paires, une
calibration TP/SL par paire serait **du bruit**. → **Reporté** jusqu'à matière
suffisante. **Aucun seuil modifié cette session.**

`v9_calibration.py --analyze --symbol <X>` sur les nouvelles paires renverrait
des distributions sur ~700 snapshots / 4 h → non exploitable pour décider.

---

## 5. Dette technique nettoyée (Priorité 3)

| Action | État |
|---|---|
| Suppression backup `data/v9_forces.db.bak_20260717_votedevise` (1.6 GB) | ✅ supprimé (fix committé en `87c7a74`, 1.6 GB récupérés) |
| Règle `.gitignore` pour les backups DB | ✅ ajout `data/*.bak_*` |
| Fichier parasite `query` (contenu `V9CaptureWatchdog`, résidu de redirection) | ✅ supprimé |
| `SUPPORTED_SYMBOLS` mort ? | ❌ **NON mort** — `tests/test_exit_simulator_multi_pair.py` en dépend. C'est un **registre informatif passif** (le champ `symbol` reste libre depuis l'EA, aucune liste blanche). **Incohérence bénigne à documenter** : la liste (`GBPUSD, EURUSD, USDJPY, GBPJPY`) ne reflète pas les paires live (manque USDCAD/USDCHF, contient GBPJPY sans données). Non modifié (garde-fou config.py + tests couplés). |
| Stale M5 historique | Lié à l'historique GBPUSD (07-05→). N'impacte pas les nouvelles données (paires démarrées le 16/07). À re-mesurer sur les nouvelles paires seules après 48 h. |

---

## 6. Recommandations — feuille de route

**Court terme (24-48 h, avant toute décision VPS)**
- [ ] Laisser tourner. Objectif : **≥30 trades résolus par nouvelle paire** +
      **une 2ᵉ journée GBPUSD** hors régime du 07-08.
- [ ] Vérifier que le résolveur **ferme les 72 `preparer_entree` du 07-16** à la
      réouverture (test de vie de la boucle fermée).
- [ ] Compléter les flux TF manquants côté EA (USDCHF 3/7, EURUSD 3/7 —
      cf. `etat_pipeline_4paires_20260716.md`).

**Moyen terme (validation)**
- [ ] Re-lancer la requête WR SHADOW (§3) → promouvoir ceux qui passent WR>50 %/n≥10.
- [ ] Refaire le tableau §2 quand les 5 paires ont des trades résolus →
      répondre enfin à corrélation/diversification (USDCAD/pétrole, EUR/CHF).
- [ ] Calibrer TP/SL par paire **seulement si** les distributions de
      `resolution_pips` divergent significativement de GBPUSD.

**Décision GO/NO-GO production (VPS)** — critères de sortie :
- GBPUSD WR ≥ 55 % sur ≥2 journées distinctes ✗ (1 seule journée aujourd'hui)
- Chaque nouvelle paire ≥30 trades résolus, WR ≥ 50 % ✗ (0 aujourd'hui)
- Boucle fermée : résolveur confirmé actif sur batch récent ⏳ (à vérifier)

→ **NO-GO actuel.** Ni production ni Phase 10 tant que ces 3 critères ne sont
pas verts. La priorité n'est pas de bâtir plus, mais de **laisser le système
accumuler la preuve**.

---

## 7. Tests & conformité

- Tests : **1502 passed, 1 skipped** (SIGTERM non-fonctionnel sur Windows) en 186 s. ✅ Base verte (R7).
- `config.py` : **non modifié** (R2 additif, garde-fou respecté).
- Aucun fichier `core/v9/` touché (R8, R18 : zéro LLM cœur cognitif — respecté).
- Seules modifications : `.gitignore` (+1 règle), suppression 2 fichiers non
  versionnés (backup, parasite). **Rien de cognitif touché.**
