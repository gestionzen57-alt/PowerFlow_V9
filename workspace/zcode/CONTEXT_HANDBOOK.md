# CONTEXT HANDBOOK — ZCode Sprint CEO 03/08+1

> **Lecture obligatoire** avant de commencer un chantier ZCode.
> Contexte minimal pour travailler sans supervision.

## État du sprint CEO 03/08 (au 2026-08-03 06:30 UTC)

**HEAD actuel** : `b4d6c3b` (déjà pushé sur `origin/feat/v9-foundation-clean`).
**Branche locale** : `feat/v9-foundation-clean`.

**Commandes utiles** :
```bash
cd C:/projet/V9
git log --oneline -10
git status --short
```

**Tests** : `cd C:/projet/V9 && .venv/Scripts/python -m pytest tests/ -q --tb=short`

## Doctrine (à respecter scrupuleusement)

| Règle | Application |
|---|---|
| **R2 additif** | Tu ne modifies JAMAIS un fichier core/ existant sans additif. Si tu dois le faire, propose un module NEW. |
| **R6 fail-open** | Tout module que tu écris ne doit JAMAIS lever d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | Tu LIVRES un test par cas critique (5+ tests par module). Tests obligatoires AVANT commit. |
| **R14 git vérité** | Chiffres et métriques viennent du SQL réel (DB `data/v9_forces.db`), JAMAIS inventés. |
| **R22 sous-unité unique** | 1 phase = 1 livrable = 1 module NEW + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO explicite. |
| **R26 DECISIONS_LOG** | 1 entrée par livraison dans `workspace/perplexity/memory/DECISIONS_LOG.md`. |
| **R28 Hermes git unique** | ZCode NE PUSH JAMAIS. Commit sur branche propre, Hermes agrège + push. |

## Modules core/ à connaître (ne pas modifier)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Chargeur central kill switches. Ajouter fonction accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | Filtre L1-L11 (L11 = boost/blacklist DOW × pair). ZCode peut ajouter L12 (corrélation) ou L16 (asymétrie direction) en suivant le pattern L11. |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |

## Configuration

**Fichier env** : `config/v9_kill_switches.env` (lecture via `kill_switches.get()`).
**Ajouter un kill switch** = ajouter une ligne `V9_XXX=0` + section commentée explicative.

## Tests

| Pattern | Référence |
|---|---|
| Module L11 (DOW × pair) | `tests/test_v9_mega_edge_l11_dow.py` |
| Module L15 (heatmap) | `tests/test_v9_heatmap_l15.py` |
| Pyramiding V2 | `tests/test_v9_pyramiding_engine_v2.py` |
| Walk-forward L7/L8 | `tests/test_v9_l7_promotion_walkforward.py` + `test_v9_l8_promotion_walkforward.py` |

## DB source

`data/v9_forces.db` (5.1 GB, 27 tables, 64 index).
Lecture OK. Écriture restreinte (voir kill_switches writables).

## Branche de travail ZCode

```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode-<chantier>
# Travail...
git add <fichiers_du_périmètre>
git commit -m "feat(v9): Phase 12X <description>"
# NE PAS git push origin
```

## Report à Hermes

À la fin du chantier, ZCode reporte à Hermes :
1. **Branche** : `feat/v9-zcode-XXX`
2. **Commits atomiques** : liste `<hash> <message>`
3. **Tests verts** : `pytest tests/test_v9_XXX.py -q` (sortie)
4. **Diff résumée** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode-XXX`
5. **Kill switches créés** : liste des `V9_XXX=0` ajoutés à `config/v9_kill_switches.env`

Hermes agrège en mergeant la branche dans `feat/v9-foundation-clean`, en
mettant à jour `docs/ROADMAP.md` + `STATE.md` + `DECISIONS_LOG.md`, puis
en pushant sur origin (R28 strict).

## Anti-patterns (à éviter absolument)

- ❌ Modifier un fichier core/ partagé (mega_edge_filter, kill_switches) sans
  respecter le pattern existant (commentaires Phase XXX, défauts OFF, R6 fail-open).
- ❌ Inventer des chiffres ou métriques (R14 strict).
- ❌ Pousser sur origin (R28 strict, ZCode n'est pas opérateur git unique).
- ❌ Commit sans tests verts (R7 strict).
- ❌ Mélanger plusieurs phases dans un même commit (R22 strict, R26 strict).

## Skills catalogue V9 (référence)

- `skills/powerflow-v9-heatmap-l15/SKILL.md`
- `skills/powerflow-v9-l11-dow-filter/SKILL.md`
- `skills/powerflow-v9-quant-fund/SKILL.md`
- `skills/powerflow-v9-recalibration-audit/SKILL.md`

## Patterns à suivre (look-and-feel code V9)

```python
# ── Phase XXX — Description (2026-08-03) ────────────────────────────
# Audit SQL live 03/08 (n=337) :
#   Cas A : n=X WR=Y% PNL=Z (description)
#   Cas B : n=X WR=Y% PNL=Z (description)
# Gain projete : X pips. Cout : Y%.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def new_module_accesseur() -> bool:
    """Kill switch V9_XXX_ENABLED — Phase XXX (date).

    Description courte (1 phrase du role).
    Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    """
    return get("V9_XXX_ENABLED", "0") == "1"
```

Respecter ce format (commentaires Phase XXX, audit SQL, gain projeté,
doctrine rappelée). Le code V9 est extrêmement bien documenté.