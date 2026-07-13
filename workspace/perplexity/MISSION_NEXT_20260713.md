# MISSION — Prochaine session (Opus / Fable / Claude Code)
*Préparée le 2026-07-13 par la session Claude Code qui a livré la série Q1→Q5.*

> À coller telle quelle en début de session, sur le dépôt local `C:\Projet\V9`,
> branche `feat/v9-foundation-clean`. Auto-suffisante — n'importe quelle session
> avec accès au dépôt peut l'exécuter sans relire cette conversation.

---

## Contexte vérifiable (ne pas prendre pour acquis, re-vérifier au démarrage)

```
git status && git log --oneline -10
.venv/Scripts/python.exe -m pytest tests/ -q
```

Attendu au 2026-07-13 : HEAD = `584d68f` (ou plus récent), **1226 tests verts,
2 skips documentés, 15 échecs pré-existants dans `tests/test_telegram_notifier.py`**
(dette Telegram post-refactor 2026-07-11, indépendante — un des chantiers
ci-dessous la corrige). Si les chiffres divergent : **git gagne toujours**,
reconstruis l'état depuis `git log` plutôt que depuis ce document.

Lire dans l'ordre avant de coder : `workspace/perplexity/ROADMAP_CLAUDE_CODE.md`
(périmètre STRICT alloué, section "déjà livré — NE PAS REFAIRE"),
`docs/checkpoints/CHECKPOINT_20260713_QUANTUM_LEAP.md`, `docs/STATE.md`.

## Garde-fous permanents (hérités, non négociables)

- R7 : suite complète verte avant chaque commit, zéro régression.
- R8 : backup MD5 `docs/calibration/backups/2026-07-13_<chantier>/` avant
  toute modif `core/v9/*`.
- R18 : zéro LLM/appel réseau dans le chemin cognitif live.
- R26 : 1 commit + entrée `DECISIONS_LOG.md` + `STATE.md` à jour par chantier.
- R28 : commits via Bash, jamais `--no-verify`. Tu peux pousser toi-même
  (`git push origin feat/v9-foundation-clean`) après suite verte — plus de
  restriction "Hermes opérateur unique" sur cette branche à ce stade.
- Kill switch : tout nouveau module/seuil = env var défaut OFF.
- **Hors périmètre absolu, ne pas toucher** : `core/v9/order_executor.py`
  (`V9_EXECUTION_ENABLED` reste à 0 — seul Søn l'active), Phase 10 (fédération
  d'agents), toute modif EA MT4 réelle (documenter comme action opérateur si besoin).
- Avant de coder quoi que ce soit dans `core/v9/`, relire la section
  "Chantiers déjà livrés (NE PAS REFAIRE)" de `ROADMAP_CLAUDE_CODE.md` — une
  autre session peut avoir avancé depuis la rédaction de cette mission.

## Chantiers proposés, par priorité

### 1. TG-FIX — corriger les 15 échecs `tests/test_telegram_notifier.py` (2-4h, priorité HAUTE)
Dette réelle et documentée depuis le 2026-07-11 (refactoring Telegram), jamais
traitée. Comprendre la cause (probablement un changement de signature/fixture
non répercuté dans les tests), corriger localement. **Ne touche pas au
comportement runtime réel** (le token dans `.env` est un vrai secret, ne pas
tenter d'appel réseau réel dans les tests — mock). Objectif : 1226 → ~1241
verts, 0 fail.

### 2. P4 — Event Calendar dynamique (6-8h, priorité HAUTE)
Enrichir `data/economic_calendar.json` (événements datés + impact 1-3).
Étendre `news_context.py` pour des fenêtres NFP/CPI. `principle_engine.
_load_shared_context` doit pouvoir lire `news_phase != "HIGH"`. Module pur,
pas d'écriture DB. Coordonne avec le module `vol_regime`/`adaptive_thresholds`
déjà livrés (P6/P3) mais ne les modifie pas.

### 3. P3-WIRE — câbler `adaptive_thresholds_at_runtime.py` (4-6h, priorité MOYENNE)
Le module de calcul existe (`core/v9/adaptive_thresholds_at_runtime.py`,
commit `5abfa2b`) mais n'est branché nulle part — les seuils
`COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD`/`CONFIANCE_MIN` restent statiques
en prod malgré le module. Wire-up dans `principle_engine.evaluate_condition`,
**kill switch dédié** (nouveau nom, ne pas réutiliser un switch existant),
défaut OFF. Test de non-régression obligatoire : switch OFF → sortie
strictement identique à avant (diff bit-à-bit sur un échantillon de scènes).

### Optionnel / basse priorité — ORDER-BRIDGE
`core/v9/order_executor.py` dépose des commandes JSON dans `data/order_queue/`
mais rien ne les consomme côté MT4 aujourd'hui. Un chantier séparé pourrait
livrer le **lecteur/watcher côté V9** (purge des fichiers traités, logs) —
mais PAS la modification de l'EA MT4 réelle (action opérateur, hors
autopilot). Ne pas activer `V9_EXECUTION_ENABLED`. À ne prendre que si les
3 chantiers ci-dessus sont finis et que Søn confirme vouloir avancer sur ce point.

## Clôture attendue

Comme pour la série Q1-Q5 : suite complète verte, `STATE.md` mis à jour,
`DECISIONS_LOG.md` une entrée par chantier livré, `ROADMAP_CLAUDE_CODE.md`
resynchronisé (déplacer les chantiers livrés vers "NE PAS REFAIRE"), checkpoint
si la session livre plusieurs chantiers. Rapport final court (10-15 lignes) :
livré/actif, éteint en attente d'activation (env vars exactes), bloqué et pourquoi.
