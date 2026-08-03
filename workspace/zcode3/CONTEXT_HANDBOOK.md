# CONTEXT HANDBOOK — ZCode3 (session V5, parallélisé avec Hermes3)

> **Lecture obligatoire** avant de commencer un chantier ZCode3.
> Héritage de ZCode2 (sprint CEO 03/08+1 V4 finalisé).

## État du sprint CEO 03/08+1 (V4) — FINALISÉ (2026-08-03 17:50 UTC)

**HEAD actuel** : `858fc7c` (déjà pushé sur `origin/feat/v9-foundation-clean`).
**Branche locale** : `feat/v9-foundation-clean` (merger après livraison).

**Tes livraisons V3+ZCode2 précédentes** :
- Phase 128 L12 Correlation (ZCode1 V3, commit `7ed5c55`)
- Phase 129 L16 Asymmetry (ZCode1 V3, commit `83677a2`)
- Phase 140 L18 Edge Decay Sentinel (ZCode2 V4, commit `4dd210e` mergé)

## Sprint CEO 03/08+2 (V5) — 2 phases ZCode3

1. **Phase 141** L19 News Shock Attenuator (ZCode3 C1, RECOMMANDÉ en premier) : 1-2 j, branche feat/v9-zcode3-l19-news-shock
2. **Phase 143** L20 News Heat Map (ZCode3 C2) : 2-3 j, branche feat/v9-zcode3-l20-news-heat

**Effort total ZCode3** : 3-5 jours parallelisable avec Hermes3 (4-5 j).

## Doctrine (héritage ZCode V3+ZCode2 V4, inchangée)

| Règle | Application ZCode3 |
|---|---|
| **R2 additif** | NEW modules uniquement, 0 modif core/ partagé. |
| **R6 fail-open** | JAMAIS d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | 5-15 tests par module. Tests AVANT commit. |
| **R14 git vérité** | Audit SQL live, JAMAIS inventer de chiffres. |
| **R22 sous-unité unique** | 1 phase = 1 module + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO. |
| **R26 DECISIONS_LOG** | Reporter à Hermes3 (qui merge + ajoute entry). |
| **R28 multi-IA** | **ZCode3 = 0 push.** Hermes3 seul merge et push. |

## Modules core/ à NE PAS MODIFIER (sauf additif)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Ajouter fonction accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | NE PAS toucher (sauf si L19+ s'intègre, alors additif). |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |
| Modules V4 Hermes2 (V4 zones, DD tracker, regime live) | NE PAS toucher. |
| Modules ZCode2 (L18 edge decay sentinel) | NE PAS toucher. |

## Branche de travail ZCode3

```bash
cd C:/projet/V9
git checkout -b feat/v9-zcode3-<chantier>
# Travail sur la branche ZCode3 (propre, 0 push)
git add <fichiers_du_périmètre>
git commit -m "feat(v9): Phase 14X <description>"
# NE PAS git push origin (R28 strict : Hermes3 seul)
```

## Report à Hermes3 (à la fin du chantier)

1. **Branche** : `feat/v9-zcode3-<chantier>`
2. **Commits atomiques** : `git log --oneline feat/v9-foundation-clean..feat/v9-zcode3-<chantier>`
3. **Tests verts** : sortie pytest complète
4. **Diff résumée** : `git diff --stat feat/v9-foundation-clean..feat/v9-zcode3-<chantier>`
5. **Audit SQL réel** : chiffres mesurés

Hermes3 merge dans `feat/v9-foundation-clean`, ajoute l'entrée DECISIONS_LOG, push origin (R28 strict).

## Anti-patterns

- ❌ Modifier un fichier core/ partagé sans respecter le pattern existant.
- ❌ `git push origin` (R28 strict, ZCode3 n'est pas opérateur git unique).
- ❌ Commit sans tests verts (R7).
- ❌ Inventer des chiffres (R14).
- ❌ Mélanger 2 phases dans le même commit (R22 strict).

## Compétences à appliquer

- NEW module additif
- Audit SQL live
- Kill switches défauts OFF
- Tests pytest avec monkeypatch.env + reload
- Composition avec modules existants (sans les modifier)

## Skills catalogue V9 (référence — 38 skills)

- 25 skills pré-existants (Phase 9-12)
- `skills/powerflow-v9-heatmap-l15/SKILL.md`
- `skills/powerflow-v9-l11-dow-filter/SKILL.md`
- `skills/powerflow-v9-correlation-l12/SKILL.md`
- `skills/powerflow-v9-direction-asymmetry/SKILL.md`
- `skills/powerflow-v9-vol-realized-tpsl/SKILL.md`
- `skills/powerflow-v9-risk-attribution/SKILL.md`
- `skills/powerflow-v9-pyramiding-v3-mtf/SKILL.md`
- `skills/powerflow-v9-cross-blacklist/SKILL.md`
- `skills/powerflow-v9-edge-decay-sentinel/SKILL.md`
- `skills/powerflow-v9-pyramiding-v4-zones/SKILL.md`
- `skills/powerflow-v9-adaptive-dd-tracker/SKILL.md`
- `skills/powerflow-v9-regime-live-detector/SKILL.md`

## Patterns à suivre (look-and-feel code V9)

```python
# ── Phase XXX — Description (2026-08-04) ────────────────────────────
# Audit SQL live 04/08 (n=X) :
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

**Go. Tu as 3-5 jours. Sprint CEO mode « plein pouvoir » V5. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes3 orchestre. ZCode3 implémente. CEO Søn valide.

*Handbook préparé par Hermes le 2026-08-03 17:50 UTC pour ZCode3 (sprint CEO 03/08+2 V5).*