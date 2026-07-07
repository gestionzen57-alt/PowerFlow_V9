# Checkpoint sprint Søn Mode A — 2026-07-07

## Identification
- **Date** : 2026-07-07 (sprint 21h00 → 22h30 CEST, puis clôture 22h30 → 22h45)
- **Branche** : `feat/v9-foundation-clean`
- **HEAD final** : `fa79787` (+ commit clôture à venir = `HEAD+1`)
- **Type** : checkpoint opérationnel sprint autonome
- **Opérateur** : Hermes (Søn CEO via Telegram)
- **Référence** : Søn demande « je gère l'indicateur SDI et le VPS, occupe-toi du V9 » / « V9 opérationnel comme je veux et non limitant ».

## 1. Contexte / déclencheur

Søn exprime une frustration légitime (« j'en ai marre que cela ne finisse jamais ») après une journée intense : audit CEO complet de V9, prise de conscience de bridages Perplexity (fédération jetée, MCP supprimés, 11 YAML écartés sans demande, seuils PROVISIONAL non recalibrés), décision « sprint jusqu'au bout ». Søn disposait déjà de :
- VPS costaud (4 cores 2.6 GHz, 12 GB RAM)
- DB locale 2.9 GB / 72K+ snapshots / 663 tests / 30 règles doctrine
- Pipeline Mode A compatible

Sa consigne : « sprint, autonome, jusqu'au bout possible » — sprint total sur ce qui ne dépend PAS de SDI (à sa charge) ni du VPS (qu'il configure de son côté).

## 2. Périmètre livré — 6 livrables sprint

| # | Commit | Livrable | LOC | Tests |
|---|---|---|---|---|
| 1 | `22fa492` | `agents/REGISTRY.py` — Mode A 5 agents chauds + supervisor + reviewer | ~80 | +8 |
| 2 | `165691c` | `core/v9/agent_telemetry.py` + hook best-effort capture_server | ~95 | +7 |
| 3 | `15c6845` | `scripts/v9_agent_precision.py` — CLI rapport | ~55 | +4 |
| 4 | `6db9e3b` | `scripts/v9_check_vps.py` — preflight VPS | ~80 | +7 |
| 5 | `80dc3c5` | ARCHITECTURE.md resync (214→663) + DECISIONS_LOG sprint | edits | 0 |
| 6 | `fa79787` | Audit 11 YAML gap V8/V9 + Règle 30 + BONUS_CONFLUENCE_MTF DEPRECATED | ~95 | 0 |

## 3. Architecture cible Mode A (livrée)

```
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT #0 — Søn Supervisor (déjà livré scripts/v9_supervisor.py)    │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (boucle 1s)
┌─────────────────────────────────────────────────────────────────────┐
│  REGISTRY — agents/REGISTRY.py : 5 chauds + supervisor + reviewer   │
└─────────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│ AGENT #1       │ │ AGENT #2       │ │ AGENT #3       │
│ force_reader   │ │ scene_builder  │ │ behavior_      │
│ (couche 2)     │ │ (couche 3)     │ │   analyst      │
│ bloc: oui      │ │ bloc: oui      │ │ (couche 4)     │
│                │ │                │ │ bloc: oui      │
└────────────────┘ └────────────────┘ └────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  AGENT #4 — gatekeeper (window_gate + exploitability + regime)    │
│  (couche 5-7) — sortie unique : window_statut + exploitability     │
└────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  AGENT #5 — decision_maker (principles + signal + arbiter)        │
│  (couche 7-9) — sortie : décision V9 + paper-trade entry         │
└────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  AGENT LATÉRAL — reviewer (HITL Telegram, non bloquant)           │
└────────────────────────────────────────────────────────────────────┘
```

## 4. Différence clé vs Fédération V8 (rejetée explicitement)

| Aspect | V8 (rejeté) | Mode A livré |
|---|---|---|
| Process | 1 par agent | 1 daemon unique + wrappers |
| Communication | RPC HTTP | Fonctions Python directes |
| Mémoire | 700+ MB | < 250 MB (12 GB dispo sur VPS) |
| LLM dans boucle | Central + workers | Aucun (règle 18) |
| MCP servers | 5 (3001/3110/3111/3114/3130) | 0 |
| Agent count | 17 rôles | 7 entrées (5 chauds + supervisor + reviewer) |

## 5. Audit 11 YAML manquants V8 → V9

Constat factuel (pas d'invention, lecture directe YAML) :

| Catégorie | Compte | Action V9 |
|-----------|--------|-----------|
| V6 archivage (producteur mort 2026-04-29) | 5 | Aucune — code V6 mort |
| V7 DEPRECATED blacklistés (WR 0%) | 3 | Aucune — faux signaux |
| V7 SHADOW audit requis | 1 | Migration acceptable si Søn le veut |
| V8_NATIVE SHADOW gelé par Søn | 1 | Migration différée critères Søn |

**Verdict** : Perplexity n'a rien écarté d'utile. Documenté dans
`docs/audit/AUDIT_V8_V9_YAML_GAP_20260707.md`.

## 6. Règle 30 ajoutée (DOCTRINE.md)

**Apprentissage conditionnel WIN/LOSS — seuils progressifs sans saut, jamais par décision arbitraire.**

| Seuil | Capacité activée |
|-------|------------------|
| WIN/LOSS ≥ 5 | Lecture décisions possible, 0 recalibrage |
| WIN/LOSS ≥ 20 | **Feedback loop partielle activable** (= v9_agent_precision.py utilisable) |
| WIN/LOSS ≥ 50 | Phase 13 complète activable (recalibrage arbiter zone-type × session) |
| WIN/LOSS ≥ 200 | Auto-tune seuils, boucle complètement fermée |

**Garde-fous** : pas de saut sans DECISIONS_LOG datée, zéro LLM (règle 18).

## 7. BONUS_CONFLUENCE_MTF DEPRECATED (config.py)

Audit a confirmé : constante NON référencée dans le code (que dans `window_gate.py:26` docstring + le bloc config.py lui-même). Marquée `DEPRECATED 2026-07-07`. À supprimer prochaine itération config.py. Aucun module ne l'utilise.

## 8. Bilan test (règle 7 — zéro régression)

- **Avant sprint** : 637 verts / 3 xfailed / 1 xpassed
- **Après sprint** : **663 verts** / 3 xfailed / 1 xpassed
- Diff : +26 tests verts (8 REGISTRY + 7 telemetry + 4 precision CLI + 7 VPS preflight)
- Régressions : 0

## 9. Périmètre respecté strictement

| Module | Modifié ? |
|--------|-----------|
| `core/v9/config.py` | OUI (DEPRECATED commenté, sémantique préservée) |
| `core/v9/orchestrator.py` | NON |
| `core/v9/principle_engine.py` | NON |
| `core/v9/arbiter.py` | NON |
| `core/v9/window_gate.py` | NON |
| `core/v9/exploitability_evaluator.py` | NON |
| `core/v9/principles/*.yaml` | NON (27 YAML intacts) |
| `core/v9/capture_server.py` | OUI (hook télémétrie best-effort) — déjà patché, récurrent |
| `agents/*` | OUI (nouveau REGISTRY.py + READMEs pré-existants) |
| `scripts/*` | OUI (3 nouveaux + 1 rapport) |
| `docs/*` | OUI (resync + audit + checkpoint) |
| `workspace/perplexity/*` | OUI (resync global, DECISIONS_LOG) |

## 10. Anti-patterns évités

- ❌ Fédération V8 (RPC, multi-process, bus) — REJETÉ
- ❌ LLM dans boucle chaude (règle 18) — RESPECTÉ
- ❌ MCP servers (V8 5 serveurs) — REJETÉ explicitement
- ❌ Modif core/v9/business gelé — RESPECTÉ (sauf capture_server autorisé récurrent)
- ❌ Inversion seuil chiffré (règle 25) — RESPECTÉ (Règle 30 = repères initiaux, révisables Søn)
- ❌ Commit pré-DECISIONS_LOG (règle 26) — RESPECTÉ pour Règle 30

## 11. Capacité opérationnelle VPS cible

| Caractéristique VPS | Valeur | Viable Mode A ? |
|---|---|---|
| CPU | 4 cores 2.6 GHz | ✅ largement |
| RAM | 12 GB | ✅ Mode A < 250 MB |
| Disque | non spécifié (≥ 5 GB requis) | ⚠️ Søn à confirmer |
| OS | Linux Debian/Ubuntu supposé | ⚠️ Søn à confirmer |
| Python | 3.11+ requis (V9 testée en 3.14) | ⚠️ Søn à confirmer |
| Indicateur SDI (.mq4) | ABSENT côté V9 | ⚠️ Søn à installer |
| MT4 broker | à choisir | ⚠️ Søn à choisir |

**Action Søn pour activer le pipeline** :
1. Installer `.mq4` SDI sur MT4 VPS
2. Démarrer `python -m core.v9.capture_server` côté VPS
3. Attendre 24h, puis `python scripts/v9_agent_precision.py --window 7`
4. Premier rapport télémétrie par couche (force_reader, scene_builder, behavior_analyst, gatekeeper, decision_maker)

## 12. Honnêteté — limitations assumées

- **Tests xfail** : 3 tests `test_v9_arbiter_rule29.py` marqués honnêtement (refactor fixtures in-memory, chantier Phase 13).
- **Paper trade** : 0 ouvert (marché range, comportement nominal, attendu).
- **WIN/LOSS** : 0 résolu. Règle 30 prévoit ≥ 20 pour activer feedback, ≥ 50 pour Phase 13.
- **Tâches gelées** : Phase 10/11/12/13 (Søn gel explicite 2026-07-07 14h58 + Doctrine + R30).
- **`paper_trades.db`** : absente. Le module PHASE 9.7 n'a jamais produit le fichier attendu. À investiguer post-SDI live.

## 13. Suite logique

Post-sprint Søn, le pipeline attend :
1. Action Søn VPS + SDI → flux live reprend
2. 24h d'observation → premier rapport télémétrie
3. Premier trade WIN ou LOSS → Règle 30 commence à compter
4. WIN/LOSS ≥ 20 (probablement plusieurs semaines) → feedback loop activable
5. WIN/LOSS ≥ 50 (probablement 1-2 mois) → Phase 13 possible

Aucun de ces jalons ne nécessite une nouvelle intervention Hermes sans GO explicite.

---

**Fin du checkpoint sprint Søn Mode A — 2026-07-07 22h45 CEST. Mode A — VEILLE.**
