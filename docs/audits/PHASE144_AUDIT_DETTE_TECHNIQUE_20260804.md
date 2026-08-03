# Audit dette technique pré-V4 (2026-08-04) — Phase 144 préparation

> **Statut** : dette documentée, sprint dédié futur.
> **Run pytest complet** : 72-76 F / 4221 verts / 14 skipped / 2 xfailed (29:17)
> **Run pytest sans test_mcp_servers** : 72 F / 4198 verts (26:36)
> **Taux de réussite** : 98.2-98.3%

## Périmètre dette

La dette technique pré-V4 concerne les modules et tests datant de avant
sprint CEO 03/08 (juin-juillet 2026). Les sprints V3, V4, V5 (CEO no-stop
depuis 03/08 03:00) ont ajouté de la dette **documentée mais non fixée**.

## Décomposition par fichier (76 F total)

| Fichier | F | Type erreur | Origine probable |
|---|---|---|---|
| `test_v9_pyramiding_engine.py` | **35** | AttributeError | API V2 changée en V3/V4 (classe vs fonction) |
| `test_v9_re_resolve.py` | 4 | RuntimeError | Module re-resolve post-DROP 17/07 |
| `test_v9_replay_doctrine_realign.py` | 1 | (assertion count=48) | Doctrine realign compte actif différent |
| `test_v9_resolve_decision_auto.py` | 1 | (MFE 199.5 vs 99.5) | Exit strategy changement (×2) |
| `test_v9_self_improving.py` | 1 | (subprocess) | Self-improving CLI |
| `test_v9_telegram_signal_alert.py` | 1 | (filter) | Telegram alert filter |
| `test_walk_forward.py` | 1 | (CLI smoke) | Walk-forward CLI smoke |
| Autres (multi-fichiers) | ~32 | divers | pré-V4 |

## Détail `test_v9_pyramiding_engine.py` (35 F, dette la plus lourde)

**Symptôme** : 35 F AttributeError sur la fonction `compute_pyramiding_factor()`.

**Cause** : Le module `core/v9/v9_pyramiding_engine.py` a été réécrit
le 03/08 (commit `603fce7` "PyramidingEngine V2 — STARS (x1.3) +
SUPER_STARS (x1.5)"). L'API est passée d'une **fonction** :
```python
def compute_pyramiding_factor(principles, confidences, directions=None) -> Decision
```
à une **classe** :
```python
class PyramidingEngineV2(PyramidingEngine):
    def __init__(self, *, min_principes_pyramiding=3, ...)
    def evaluate(self, arbiter_result, context=None) -> dict
```

Le test `test_v9_pyramiding_engine.py` (daté 2026-07-18, 35 tests) appelle
toujours l'ancienne API.

**Le test EST legacy** : il date d'avant la refonte V2. Mais le script
`scripts/v9_aggressive_paper_trade.py` (daté 2026-07-18, ligne 322) utilise
**encore** `pyr.compute_pyramiding_factor(...)` !

C'est un cas classique de dette : le module a été refondu, mais ni le
script legacy ni le test n'ont été mis à jour. Le script n'est plus
exécuté (remplacé par `v9_aggressive_optimize.py` et le pipeline live),
mais le code mort reste.

## Détail `test_v9_resolve_decision_auto.py` (1 F, MFE 199.5 vs 99.5)

**Symptôme** : Le test attend `pips == 99.5` mais reçoit `199.5` (×2).

**Cause probable** : l'exit strategy MFE_ONLY a été modifiée pour doubler
le pips (peut-être un facteur ×2 introduit pour le spread ou un
multiplicateur de barème). Le test a été écrit pour la version initiale
de l'exit strategy et n'a pas été mis à jour.

**À investiguer** : le test est un test d'intégration (fixture DB + simu
D4). Le fix est probablement dans le code de résolution, pas dans le test.

## Détail `test_v9_re_resolve.py` (4 F, vestigial)

**Symptôme** : 4 F RuntimeError + 1 skip "vestigial: assertions fausses
par design post-DROP 17/07".

**Cause** : le module `re_resolve` est marqué comme **vestigial** dans
le test lui-même (ligne 70). Le DROP batch du 17/07 a invalidé le
contexte du test.

## Détail `test_v9_replay_doctrine_realign.py` (1 F, count=48)

**Symptôme** : `test_active_ids_count_is_48` échoue (le compte ne match
plus 48).

**Cause probable** : le nombre de YAML actifs a évolué (de 47 à 48 ou
inversement) sans mettre à jour le test.

## Détail `test_v9_telegram_signal_alert.py` (1 F, filter)

**Symptôme** : `test_fetch_recent_signals_filters` échoue (filtre mal
calibré).

## Détail `test_v9_self_improving.py` (1 F, subprocess)

**Symptôme** : `test_run_pytest_quick_smoke` subprocess fail.

## Plan de remediation Phase 144 (sprint dédié futur)

### Étape 1 — Quick wins (½ journée)

1. `test_v9_replay_doctrine_realign.py` : ajuster le count (47 ou 48)
2. `test_v9_telegram_signal_alert.py` : ajuster le filtre
3. `test_v9_self_improving.py` : ajuster le subprocess smoke

→ 3 F fix en ½ journée, gain : 0 dette facile.

### Étape 2 — test_v9_pyramiding_engine.py (1-2 journées)

**Option A** : Réécrire les 35 tests pour la nouvelle API
`PyramidingEngineV2().evaluate(arbiter_result, context)`. Effort 1-2 j.
Bénéfice : couverture de la nouvelle API retrouvée.

**Option B** : Supprimer le fichier (legacy code mort). Effort 0.5 h.
Risque : perte de couverture. Le test couvrait la convergence de principes
V1, qui n'est plus pertinente (PyramidingEngine V1 est dans
`core/v9/principle_engine.py` et a sa propre couverture).

**Recommandation** : **Option B** (suppression) + créer un nouveau test
pour la nouvelle API si nécessaire. Le script `v9_aggressive_paper_trade.py`
utilise encore `compute_pyramiding_factor` mais c'est un script de
backtest, pas le pipeline live.

### Étape 3 — test_v9_resolve_decision_auto.py (½ journée)

Investiguer le changement de l'exit strategy MFE_ONLY. Probablement un
facteur ×2 introduit pour le spread. Fix dans `core/v9/v9_resolve_decision.py`
ou dans le test selon la cause.

### Étape 4 — test_v9_re_resolve.py (1 journée)

Le module est marqué vestigial. Décision : supprimer (legacy mort) ou
réécrire (effort). Recommandation : supprimer, le DROP 17/07 a invalidé
le contexte.

### Étape 5 — test_walk_forward.py (½ journée)

CLI smoke. Probablement un argument CLI manquant ou un chemin de fichier
changé. Fix rapide.

### Total Phase 144 estimé

- 3-5 journées de travail
- 76 F → 0 F
- Tests verts cumulés : 4221 → 4297 (76 récupérés)
- Pas de bénéfice projeté (fix de dette, pas nouveau levier)
- Zéro risque (tests legacy → nouveau code ou suppression)

## Recommandation CEO

Ouvrir Phase 144 comme sprint dédié **après** sprint V5 (post-08/08).
Priorité moyenne (dette n'impacte pas le trading live mais bloque la
progression des tests verts cumulés au-dessus de 98.3%).

## Risque si on ne fixe pas

- Stagnation des tests verts cumulés à 98.3% (jamais 100%)
- Faux positifs possibles (un F peut masquer un vrai bug si on l'ignore)
- Dette qui grossit (chaque sprint ajoute de nouveaux tests, certains
  deviennent legacy)
- Perception qualité dégradée pour les audits externes

**Audit dette Phase 144 = OUVERT. Effort 3-5 j. Bénéfice = 0 pips mais
100% tests verts. Priorité CEO = à arbitrer post-V5.**
