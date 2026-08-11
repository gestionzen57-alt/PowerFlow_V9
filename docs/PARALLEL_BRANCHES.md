# PARALLEL_BRANCHES — PowerFlow V10
**Mis à jour :** 2026-08-11 11:33 CEST  
**Auteur :** Perplexity CEO  
**Branche de référence :** `feat/v10-c20-healthy`

> Ce fichier documente l'état de toutes les branches parallèles actives,
> leurs responsabilités, leur état de merge, et les règles de coordination
> entre agents.

---

## 1. Cartographie des branches actives

| Branche | Responsable | État | Base | Merge cible |
|---|---|---|---|---|
| `feat/v10-c20-healthy` | CEO (référence) | ✅ STABLE — 1401 tests | — | `main` (après GO LIVE) |
| `feat/zcode-night` | ZCode | 🔄 ACTIF — sessions nocturnes | `feat/v10-c20-healthy` | `feat/v10-c20-healthy` |
| `feat/hermes-live` | Hermes | ✅ mergé PR #7 + PR #8 | `feat/v10-c20-healthy` | mergé ✅ |

---

## 2. Règles de coordination inter-branches (R2 additif)

### Règle GOLD — Une branche = un agent
- `feat/zcode-night` : **ZCode uniquement** — `core/v10/`, `tests/`, `scripts/`
- `feat/hermes-live` : **Hermes uniquement** — `scripts/`, crons, pipeline live
- **Jamais deux agents sur le même fichier en même temps**
- Conflit détecté → stop + ping CEO Perplexity immédiatement

### Règle SILVER — Merge strict
```
1. pytest tests/test_v10_*.py -q --tb=no   → tous verts
2. ruff check core/ scripts/ tests/        → 0 erreur
3. PR créée → review Perplexity CEO
4. Merge squash → feat/v10-c20-healthy
5. SHA du merge → SOUL.md mis à jour
```

### Règle BRONZE — Branche à jour
```bash
# Avant chaque session ZCode / Hermes :
git fetch origin
git rebase origin/feat/v10-c20-healthy
# En cas de conflit → stop + ping CEO
```

---

## 3. État feat/zcode-night (11/08/2026)

### Fichiers actifs sur cette branche

| Fichier | Sprint | Statut |
|---|---|---|
| `scripts/run_live_health_check.py` | Z2 | ✅ bug-fixed (11/08) |
| `scripts/run_grammar_audit.py` | Z4 | ✅ nouveau (11/08) |
| `core/v10/v10_live_health_checker.py` | Z2 | ✅ (à vérifier merge) |
| `core/v10/v10_grammar_canonical.py` | Z4 | ✅ (à vérifier merge) |

### Sprints ZCode planifiés

| Sprint | Mission | Priorité |
|---|---|---|
| **Z2** | `live_health_check` — fix import + exit codes | 🔴 CRITIQUE |
| **Z4** | `grammar_audit` — 20 patterns canoniques C22 | 🔴 CRITIQUE |
| **Z5** | WFA 6 fenêtres hors-sample (robustesse) | 🟡 HAUTE |
| **Z6** | Spread simulé dans `_simulate_pnl` | 🟡 HAUTE |
| **Z7** | IBKR LiveConnector test mock | 🟢 NORMALE |

---

## 4. Délégation ZCode — tâches que Perplexity ne peut pas faire

Perplexity (agent GitHub MCP) peut créer/modifier des fichiers sur GitHub,
mais **ne peut pas** :
- Exécuter pytest localement
- Vérifier les imports Python en runtime
- Simuler l'exécution du code
- Accéder à la DB `v9_forces.db` locale

### Ce que ZCode doit faire après ce push

```bash
# 1. Se mettre sur feat/zcode-night
git fetch origin
git checkout feat/zcode-night
git pull origin feat/zcode-night

# 2. Vérifier les 2 scripts poussés
python scripts/run_live_health_check.py
python scripts/run_grammar_audit.py

# 3. Tests
pytest tests/test_v10_*.py -q --tb=no 2>&1 | tail -5

# 4. Ruff
ruff check scripts/run_live_health_check.py scripts/run_grammar_audit.py

# 5. Si tout vert → PR vers feat/v10-c20-healthy
# Si erreurs → fix + re-push + ping CEO
```

---

## 5. Dashboard branches

```
╔══════════════════════════════════════════════════════╗
║      PARALLEL BRANCHES — ÉTAT 11/08/2026 11:33       ║
╠══════════════════════════════════════════════════════╣
║  feat/v10-c20-healthy  : ✅ STABLE   1401 tests      ║
║  feat/zcode-night      : 🔄 ACTIF    Z2+Z4 pushés    ║
║  feat/hermes-live      : ✅ MERGÉ    PR #7 + PR #8   ║
╠══════════════════════════════════════════════════════╣
║  PROCHAINE ACTION CEO                                 ║
║  → Attendre ZCode : pytest + ruff OK                  ║
║  → Merge feat/zcode-night → feat/v10-c20-healthy     ║
║  → Connecter IBKR port 7497                          ║
╚══════════════════════════════════════════════════════╝
```

---

## 6. Anti-patterns branches (historique)

- ❌ **Deux agents sur le même fichier** → conflit `v10_fatman_wave_predictor.py` (10/08) — résolu PR #7
- ❌ **Commit sur mauvaise branche** → Hermes sur `main` au lieu de `feat/hermes-live` (09/08)
- ❌ **Merge sans pytest** → 62 erreurs import cascade C10-C20 (10/08)
- ❌ **Branch stale > 48h sans rebase** → divergence silencieuse
