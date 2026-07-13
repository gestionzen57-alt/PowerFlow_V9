# MEGAPROMPT — PowerFlow V9 — Opus / Fable / Claude Code

*Préparé le 2026-07-13 ~14:30 UTC par la session CEO autopilot Hermes, suite
de MISSION_NEXT_20260713.md close. Auto-suffisant — collez-le en début de
session sur le dépôt local `C:\Projet\V9\` ou `/d/projet/v9/` (Windows),
branche `feat/v9-foundation-clean`. Contexte reproductible : v9_autopilot
CEO + sessions parallèles Claude Code Q1-Q5 ont enchaîné 22 commits le 13/07.*

> **À qui s'adresse** : Opus / Fable / Claude Code / toute IA orientée autonomie
> long-terme qui accepte un mandat CEO structuré (objectifs chiffrés, périmètre
> strict, doctrine R7/R8/R18/R22/R25'/R26/R28 imposée).
>
> **Public cible** : Søn « CEO PowerFlow V9 » — novice en git, déteste git,
> veut du contenu business (lecture de marché, décisions doctrinales, missions
> structurées).
>
> **Périmètre absolu** : PowerFlow V9 = système cognitif de lecture
> comportementale forex. GBPUSD principal (EUR/USD/JPY supportés Brief Q4).
> Pas d'exécution d'ordres réelle sans activation `V9_EXECUTION_ENABLED` (geste
> Søn séparé).

---

## 1. Doctrine V9 — 30 règles immuables à respecter en TOUT état de cause

| Règle | Énoncé court | Pose en commentaire |
|---|---|---|
| **R7** | Suite complète verte avant chaque commit, 0 régression | `pytest tests/ -q` doit retourner `X passed, 2 skipped, 0 failed` (sans exclusion). |
| **R8** | Backup MD5 de TOUT `core/v9/*` AVANT modification | `mkdir -p docs/calibration/backups/2026-07-13_<chantier>/ && git show HEAD:core/v9/<file>.py > <backup>/<file>.py.bak` avant chaque patch. Format MD5 vérifié. |
| **R18** | Zéro LLM/appel réseau dans le chemin cognitif live | Aucune dépendance externe dans `core/v9/orchestrator.py`, `core/v9/signal_generator.py`, etc. |
| **R22** | 1 commit par livraison, atomique | `git commit -m "..." -- <files>` pour 1 chantier = 1 commit. Pas de "_ongoing" commit. |
| **R25'** | Vocabulaire descriptif, PAS de promotion auto au hit_rate | Tout nouveau seuil/coefficient = env var défaut OFF + DECISIONS_LOG datée. |
| **R26** | 1 commit = 1 entrée DECISIONS_LOG + STATE.md à jour | Mettre à jour `workspace/perplexity/memory/DECISIONS_LOG.md` ET `docs/STATE.md` dans le même commit que le code livré. |
| **R28** | Søn (Hermes CEO sur cette branche) = seul opérateur git | `--no-verify` interdit, push centralisé. Voir `docs/GIT_OPERATOR_PROCEDURE.md`. |

**Doctrine Phase 12 (fondateur)** : exécution d'ordres réelle INTERDITE.
Double verrou fail-closed (cf. `core/v9/order_executor.py::EXECUTION_ENABLED_ENV = "V9_EXECUTION_ENABLED"`).

---

## 2. État vérifiable au démarrage de la prochaine session

```bash
cd /c/projet/V9 && git status && git log --oneline -10 && git branch -vv
./.venv/Scripts/python.exe -m pytest tests/ -q
ls workspace/perplexity/MISSION_NEXT_20260713.md  # si absent, mission close
```

**Attendu** : HEAD = `8811519` ou plus récent, 1249 verts + 2 skipped + 0 fail,
branche `feat/v9-foundation-clean` synchronisée sur origin. Si chiffres
divergent : `git gagne toujours`, reconstruire depuis `git log --all --oneline`
et `git log --pretty=full` pour suivre les commits linéaires.

Si dépôt absent / non initialisé, demander à Søn via Telegram (token runtime
disponible hors session CEO autopilot, voir `logs/telegram_report_20260713_status.txt`)
ou re-cloner via :
```bash
git clone https://github.com/gestionzen57-alt/PowerFlow_V9.git
cd PowerFlow_V9 && git checkout feat/v9-foundation-clean
```

**Chemin absolu** : `C:\Projet\V9` (Windows) — `~/.venv/Scripts/python.exe`
pour Python.

---

## 3. Stacking technique 2026-07-13 — diagnostic pour orientation

### 3.1 Couche perceptuelle (immobile depuis Phase 9.9)

| Module | Rôle | Statut |
|---|---|---|
| `core/v9/capture_server.py` | TCP 31685 listener, écrit `forces_snapshots` depuis EA MT4 | ✅ production |
| `core/v9/scene_builder.py` | Détecte coalitions, antagonismes, pliure, zone, contexte | ✅ production |
| `core/v9/behavior_analyzer.py` | Qualifie comportements (bascule, rotation_leadership, etc.) — `BEHAVIOR_HISTORY_LOOKBACK=50` (P5) | ✅ production |
| `core/v9/window_gate.py` | Statut fenêtre (absente / en_preparation / ouverte / fragile / invalidee / ambigue) | ✅ production |
| `core/v9/exploitability_evaluator.py` | Trade-ready verdict | ✅ production |
| `core/v9/regime_detector.py` | Cassure/extension/repos/moyen_reversion/mean_reversion | ✅ production |
| `core/v9/zone_detector.py` | State machine 5 états, tension, absorbed_pullbacks | ✅ production |

### 3.2 Couche cognitive context enrichie (12+ nouveau champs `principle_engine._load_shared_context`)

| Champ | Source | Commit |
|---|---|---|
| `vol_regime`, `vol_atr_pips`, `vol_regime_level` | vol_regime ATR-30 | `9592ce3` |
| `news_phase`, `news_distance_min`, `news_importance`, `news_session_clean`, `news_type` | news_context NewsContext | pré-existant |
| `adaptive_thresholds_enabled`, `adaptive_coalition_threshold`, `adaptive_antagonism_threshold`, `adaptive_pliure_threshold` | adaptive_thresholds_at_runtime (R25' kill switch) | `1babf14` |
| `signals.exit_strategy_recommended`, `tp_pips_recommended`, `sl_pips_recommended` | signal_generator._recommend_dynamic_* | `331382f` |

### 3.3 Modules stratégie sortie (Phase 13.2)

`core/v9/exit_simulator.py` :
- `DYNAMIC_PROFILES` (TP/SL par session asie/london/overlap/new_york/after)
- `DYNAMIC_BLACKLIST_SESSIONS = frozenset({"new_york","after"})` (Brief O4)
- `is_session_tradable()` — helper pur
- `infer_session_from_hour()` — utility
- Stratégies : TP_SL / TRAILING / TIME_BASED / MFE_ONLY / DYNAMIC
- `pips_multiplier_for_symbol()` — 10000 GBPUSD, 100 JPY (Brief Q4)

### 3.4 Résolveur WIN/LOSS

`scripts/v9_resolve_decision_auto.py` :
- `DEFAULT_EXIT_STRATEGY = "DYNAMIC"` + `DEFAULT_SKIP_SESSIONS = "new_york,after"`
- `resolve_one()` skip automatique NY/after (Brief O4 actif)
- Dry-run par défaut, `--apply --backup <dir>` pour modifier la DB
- Sortie `EXIT_RESULT` en JSON dans `decisions.resolution_details`

### 3.5 Pipeline live

`core/v9/orchestrator.py::run_chain(snapshot_id)` :
- 9 stages séquentiels : SceneBuilder → BehaviorAnalyzer → WindowGate →
  ExploitabilityEvaluator → RegimeDetector → ZoneDetector → PrincipleEngine →
  SignalGenerator → DecisionLogger.
- Fail-soft : try/except sur chaque stage, échec = stop + log.
- Defense-in-depth decision_logger : si `exit_strategy_recommended=None` ET
  direction directionnelle → `aucune_action` (Brief O4 bypass-safe).

### 3.6 Order executor (livré verrouillé, désactivé)

`core/v9/order_executor.py` (commit `584d68f`) :
- **Double verrou fail-closed** : `V9_EXECUTION_ENABLED == "1"` ET
  HITL confirmation pour > 0.5 lots.
- Bridge JSON file `data/order_queue/` → EA MT4 lit côté (action opérateur).
- `OrderRequest` dataclass + `_validate_order()` + `_send_via_bridge()`.
- 25 tests verts (`tests/test_order_executor.py`).
- **Activation reste exclusivement Søn** (R12 fondateur, R28 push).

---

## 4. Diagnostic CEO 2026-07-13 — divergences humain/V9

6 divergences identifiées entre la lecture senior humaine et V9 (cf.
`workspace/perplexity/exchange.md` §Diagnostic strategist senior) :

| # | Divergence | Combler par |
|---|---|---|
| 1 | Microstructure (order book L2, options flow, etc.) | **Hors-périmètre** — V9 reste lecture 9 couches (forces 60s+). |
| 2 | Multi-modalité (news flash, sentiment live, calendar) | ✅ NewsContext étendu (Briefs Q1-Q5) + P4 Event Calendar enrichi. |
| 3 | Causalité (parce que news X, devise Y baisse) | **V9 n'a pas** — supra-structurel, hors-périmètre. |
| 4 | Ambiguïté / labels discrets | ✅ P3 Adaptive Thresholds = f(vol_regime, news, tf) → multiplicateur composite [0.5, 2.0]. |
| 5 | Mémoire adaptative | ✅ P5 `BEHAVIOR_HISTORY_LOOKBACK 10 → 50` (~12h M5 / 25h H1). |
| 6 | Seuils rigides | ✅ P3-WIRE : seuils scalés en runtime (kill switch `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED` OFF par défaut). |

---

## 5. Top-priorité missions futures (déjà publiées par sessions précédentes)

### 5.1 O4 — décision CEO tranchée par CEO autopilot (politique conservatrice)
**Brief O4 CEO 2026-07-13, commit `bd1ca6f`** : exclusion structurelle
NY/After de la tradabilité DYNAMIC. Asie/London/Overlap tradables seulement.
Réversibilité : changer `DYNAMIC_BLACKLIST_SESSIONS` dans `core/v9/exit_simulator.py`
suffit à ré-activer. Si Søn veut re-calibration plus agressive (scale NY=0.05
au lieu de blacklist), c'est un patch isolé `exit_simulator.py:140`.

### 5.2 P2 Shadow mode parallèle (CEO-only, J+2, infra lourd)
Pipeline doublé qui publie tout dans `hitl_reviews` sans bloquer le live.
Pas de simulation (lit DB live, écrit DB shadow, alertes Telegram).
Architecture à valider avec Søn avant ouverture (cf. `agents/AGENTIC_MAP.md`).

### 5.3 ORDER-BRIDGE (optionnel, basse priorité)
`core/v9/order_executor.py` dépose JSON dans `data/order_queue/`. Le lecteur
côté V9 (watcher + purge) reste à livrer — mais **PAS de modif EA MT4 réelle**,
c'est une action opérateur (cf. `ROADMAP_CLAUDE_CODE.md` §ORDER-BRIDGE).

---

## 6. Format de commit obligatoire (R22 + R26)

```bash
# 1. Vérifier working tree clean
cd /c/projet/V9 && git status -s | wc -l   # doit être 0

# 2. Backup MD5 AVANT modif core/v9/* (R8)
CHANTER="nom_du_chantier"
mkdir -p docs/calibration/backups/2026-07-13_${CHANTER}
git show HEAD:core/v9/<file>.py > docs/calibration/backups/2026-07-13_${CHANTER}/<file>.py.bak
md5sum docs/calibration/backups/2026-07-13_${CHANTER}/<file>.py.bak

# 3. Éditer les fichiers

# 4. Tests verts (R7)
./.venv/Scripts/python.exe -m pytest tests/ -q  # 1249 verts, 0 fail

# 5. Stage + commit atomique (R22)
git add <files>
git diff --cached --stat   # sanity check
git commit -m "feat(v9): <chantier> — <résumé 50 chars>

<description technique 200 chars max>

R8 backup: docs/calibration/backups/2026-07-13_<chantier>/
Tests: +N verts (X->Y). 0 régression Autopilot/Q5/O4/P3/P5/order_executor.

Référence: DECISIONS_LOG §2026-07-13, MISSION_NEXT_20260713.md §6."

# 6. Update DECISIONS_LOG + STATE.md (R26)
echo -e "\n---\n\n### YYYY-MM-DD — <chantier>\n\n- Décision : ..." >> workspace/perplexity/memory/DECISIONS_LOG.md
git add workspace/perplexity/memory/DECISIONS_LOG.md docs/STATE.md
git commit -m "docs(v9): DECISIONS_LOG+STATE — <chantier>"

# 7. Push R28 (si autorisé par Søn)
git push origin feat/v9-foundation-clean
```

---

## 7. Format de rapport final attendu pour Søn

Court (10-15 lignes max) :
```
CHANTIER: <P3-WIRE etc.>
Commit: <hash> + lien
Tests: +N verts (X -> Y), 0 fail
Activation: env var à setter ou NEANT (kill switch OFF par défaut)
Bloqué + pourquoi: <si applicable>
Doctrine: R7 ✓, R8 ✓, R22 ✓, R25' ✓, R26 ✓
```

Søn refuse les pavés — la concision est l'art senior.

---

## 8. Garde-fous permanents (hérités, non négociables)

1. **R7** : suite complète verte avant chaque commit, zéro régression.
2. **R8** : backup MD5 `docs/calibration/backups/2026-07-13_<chantier>/` avant
   toute modif `core/v9/*`.
3. **R18** : zéro LLM/appel réseau dans le chemin cognitif live.
4. **R22** : 1 commit + entrée `DECISIONS_LOG.md` + `STATE.md` à jour par chantier.
5. **R26** : STATE.md resynchronisé en cohérence avec la livraison.
6. **R28** : push via Bash, jamais `--no-verify`. Push centralisé (Søn CEO
   sur cette branche) sauf délégation explicite.
7. **Kill switch** : tout nouveau module/seuil = env var défaut OFF.
8. **Hors périmètre absolu, ne pas toucher** :
   - `core/v9/order_executor.py` (`V9_EXECUTION_ENABLED=0` reste l'état
     par défaut — seul Søn l'active, R12 fondateur + R28).
   - Phase 10 (fédération d'agents, gelée par R19).
   - toute modif EA MT4 réelle (documenter comme action opérateur).

---

## 9. Pour questions d'orientation auprès de Søn

- **Telegram runtime** : Søn seul sait où le token réel vit (env var daemon
  externe). Voir `logs/telegram_report_20260713_status.txt` pour le payload
  prêt-à-pousser.
- **Push R28** : demander à Søn « confirme tu veux que je push »
  explicitement. Jamais auto-push.
- **O4 ajustement** : Søn a peut-être un avis sur la stratégie de
  resolution WIN/LOSS (actuellement `DEFAULT_EXIT_STRATEGY = "DYNAMIC"`,
  `DEFAULT_SKIP_SESSIONS = "new_york,after"`).
- **Phase 12 activation** : geste séparé `V9_EXECUTION_ENABLED=1` requis
  de Søn + HITL approbation par snapshot > 0.5 lots.

---

## 10. Préparation de la session

1. Lire dans l'ordre :
   - `docs/STATE.md` (résumé exécutif)
   - `docs/checkpoints/CHECKPOINT_2026-07-13_AUTOPILOT_CEO.md`
   - `workspace/perplexity/BOARD.md` (1-min pour la phase)
   - `workspace/perplexity/MISSION_NEXT_20260713.md` (mission précédente close)
   - `workspace/perplexity/ROADMAP_CLAUDE_CODE.md` (chantiers parallèles)

2. Vérifier l'état de la machine locale :
   ```bash
   cd /c/projet/V9
   ./.venv/Scripts/python.exe -V  # doit être 3.11.x
   git remote -v                   # origin = github.com/gestionzen57-alt/PowerFlow_V9
   git config --get user.name      # doit être Søn
   git config --get user.email     # doit être son@powerflow.local
   ```

3. Si un quelconque de ces checks échoue, demander à Søn avant de coder.

4. Lancer les tests baseline (1249 verts attendus) :
   ```bash
   ./.venv/Scripts/python.exe -m pytest tests/ -q
   ```

5. Si OK, passer aux missions futures selon la roadmap.

---

*Megaprompt CEO autopilot V9 — 2026-07-13. Format Opus/Fable (auto-suffisant,
verifiable, actionnable). Søn opérateur unique (R28). Doctrine 30 règles
(R7/R8/R18/R22/R25'/R26/R28 imposées). Phase 12 (exécution réelle) interdite
par fondateur (R12). V9 cognition only.*
