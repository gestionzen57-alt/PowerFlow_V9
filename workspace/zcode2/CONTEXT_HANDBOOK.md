# CONTEXT HANDBOOK — ZCode2 (session +1, parallélisé avec Hermes2)

> **Lecture obligatoire** avant de commencer un chantier ZCode2.
> Héritage de ZCode (sprint CEO 03/08 V3) qui a livré Phase 128 L12
> + Phase 129 L16.

## État du sprint CEO 03/08 finalisé (2026-08-03 07:30 UTC)

**HEAD actuel** : `83677a2` (déjà pushé sur `origin/feat/v9-foundation-clean`).
**Branche locale** : `feat/v9-foundation-clean` (merger après livraison).

**Tes livraisons V3 précédentes** (ZCode) :
- Phase 128 L12 Correlation (commit `7ed5c55`)
- Phase 129 L16 Asymmetry (commit `83677a2`)

## Sprint CEO 03/08+1 (V4) — 2 phases ZCode2

1. **Phase 140 — L18 Edge Decay Sentinel** (ZCode2 C1) : 2-3 j, branche feat/v9-zcode2-l18-edge-decay
2. **Phase 141 — L19 News Shock Attenuator** (ZCode2 C2) : 1-2 j, branche feat/v9-zcode2-l19-news-shock

**Effort total ZCode2** : 3-5 j parallelisable avec Hermes2 (6-8 j).

## Doctrine (héritage ZCode V3, inchangée)

| Règle | Application ZCode2 |
|---|---|
| **R2 additif** | NEW modules uniquement, 0 modif core/ partagé. |
| **R6 fail-open** | JAMAIS d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | 5-15 tests par module. Tests AVANT commit. |
| **R14 git vérité** | Audit SQL live, JAMAIS inventer de chiffres. |
| **R22 sous-unité unique** | 1 phase = 1 module + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO. |
| **R26 DECISIONS_LOG** | Reporter à Hermes2 (qui merge + ajoute entry). |
| **R28 multi-IA** | **ZCode2 = 0 push.** Hermes2 seul merge et push. |

## Modules core/ à NE PAS MODIFIER (sauf additif)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Ajouter fonction accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | NE PAS toucher (sauf si L18 s'intègre, alors additif). |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |
| Modules ZCode1 (Phase 128/129) | NE PAS toucher, déjà mergés. |

## Branche de travail ZCode2

```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode2-<chantier>
# Travail sur la branche ZCode2 (propre, 0 push)
git add <fichiers_du_périmètre>
git commit -m "feat(v9): Phase 14X <description>"
# NE PAS git push origin (R28 strict : Hermes2 seul)
```

## Report à Hermes2 (à la fin du chantier)

1. **Branche** : `feat/v9-zcode2-<chantier>`
2. **Commits atomiques** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode2-<chantier>`
3. **Tests verts** : sortie pytest complète
4. **Diff résumée** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode2-<chantier>`
5. **Audit SQL réel** : chiffres mesurés

Hermes2 merge dans `feat/v9-foundation-clean`, ajoute l'entrée DECISIONS_LOG, push origin (R28 strict).

## Anti-patterns

- ❌ Modifier un fichier core/ partagé sans respecter le pattern existant.
- ❌ `git push origin` (R28 strict, ZCode2 n'est pas opérateur git unique).
- ❌ Commit sans tests verts (R7).
- ❌ Inventer des chiffres (R14).
- ❌ Mélanger 2 phases dans le même commit (R22 strict).

## Compétences à appliquer

- NEW module additif
- Audit SQL live
- Kill switches défauts OFF
- Tests pytest avec monkeypatch.env + reload
- Composition avec modules existants (sans les modifier)

## Skills catalogue V9 (référence)

- `skills/powerflow-v9-edge-decay/SKILL.md` (référence pour L18)
- `skills/powerflow-v9-news-shock/SKILL.md` (à créer pour L19)
- `skills/powerflow-v9-heatmap-l15/SKILL.md` (référence Phase 126)
- `skills/powerflow-v9-correlation-l12/SKILL.md` (référence ZCode C1)
- `skills/powerflow-v9-direction-asymmetry/SKILL.md` (référence ZCode C2)

## Patterns à suivre (look-and-feel code V9)

```python
# ── Phase XXX — Description (2026-08-03) ────────────────────────────
# Audit SQL live 03/08 (n=337) :
#   Cas A : n=X WR=Y% PNL=Z (description)
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

---

**Go. Tu as 3-5 jours. Sprint CEO mode « plein pouvoir » V4. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes2 orchestre. ZCode2 implémente. CEO Søn valide.