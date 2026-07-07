# CHECKPOINT — Transition Phase 9 → Phase 10
_2026-07-07 10h08 CEST | Hermes (implémentation) + Perplexity (doctrine)_

---

## Contexte

Phase 9 (Décision et Principes) a été déclarée **terminée et canonisée**
le 2026-07-05 (commit `fe6323e`). Depuis, plusieurs chantiers
opérationnels ont été livrés sans modifier `core/v9/*` :

- ZoneDetector (`db11917`) — alimentation `zone_diagnostics`, débloque 9/10 principes ACTIVE
- Grammaire complétée (`a596f37`) — coalition_strength, cross-TF, absorption_factor
- Marquage `source_type` live/replay (commit `6a5d603`) — règle 12 doctrine
- Idempotence decisions (`3d42b6c`) — decision_id stable par snapshot_id
- Telegram notifier GBPUSD live (`4fde966`) — alertes confiance > 65
- Fix signal_generator currency gap (`8697d84`) — déblocage pipeline signaux
- `is_win` / `resolution_pips` (`b6b722e`) — colonnes nullable pour saisie post-trade
- `validate-coherence.py` 7 checks (`a303057`) — gardien cohérence DB live

Ce checkpoint acte la **transition** vers Phase 10.

---

## Pipeline Phase 9 — CANONISÉ ET STABLE LIVE

| Métrique | Valeur (vérifiée 2026-07-07) | Source |
|----------|------------------------------|--------|
| Tests | **426 verts**, 0 échec | `pytest tests/ -q` (chantier courant + historique) |
| HEAD | `a303057` | `git log --oneline -1` |
| Branche | `feat/v9-foundation-clean` | `git branch --show-current` |
| DB live | `data/v9_forces.db`, dernier snapshot `v9-GBPUSD-M15-1783422465-048964` (2026-07-07T08:07:45 UTC) | `SELECT MAX(timestamp) FROM forces_snapshots` |
| Signaux live 2026-07-07 | **7 directionnels baissiers GBPUSD**, confiance 80–100, moyenne 91.4 | `SELECT * FROM signals WHERE timestamp LIKE '2026-07-07%' AND direction='baissiere'` |
| Décisions live 2026-07-07 | **7 directionnelles baissières GBPUSD**, confiance 80–100 (4 décisions pre-fix signal_generator à signal_id orphelin — GAP-001) | `SELECT * FROM decisions WHERE timestamp LIKE '2026-07-07%'` |
| Principes déclenchés 2026-07-07 | **6 ACTIVE** : `PRICE_LAG_AT_NODE_BIRTH` (3612×), `POWER_ANGLE_BREAK_TO_PRICE_IMPACT` (295×), `ZONE_RETEST` (184×), `GRAVITY_RESPRING_NODE` (106×), `NODE_BIRTH_FAST` (46×), `RAW_NODE_BIRTH` (46×) | `SELECT principle_id, COUNT(*) FROM principle_evaluations WHERE timestamp LIKE '2026-07-07%' AND triggered=1 GROUP BY principle_id` |
| Telegram — messages envoyés | **2 messages à 10:07:49 CEST** ✅ | `logs/telegram_notifier.log` (lignes du 2026-07-07T10:07:49) |
| DB age_ms median (100 derniers snapshots) | 66 749 ms (~67s) — âge EA → serveur capture | `SELECT age_ms FROM forces_snapshots ORDER BY id DESC LIMIT 100` |

> **Note** : la latence "189,58 ms/snapshot" mentionnée dans certains briefs
> n'est pas vérifiable depuis la DB live — la métrique observable est `age_ms`
> (délai capture serveur depuis génération EA), médiane ~67s sur les 100
> derniers snapshots 2026-07-07T08:07Z. À investiguer en session dédiée si
> une métrique pipeline end-to-end (lecture → log) est nécessaire.

---

## Livrables session 2026-07-07

| Commit | Livrable |
|--------|----------|
| `8697d84` | fix signal_generator currency gap (PRICE_LAG_AT_NODE_BIRTH + POWER_ANGLE_BREAK_TO_PRICE_IMPACT visibles) |
| `15e632c` | docs DECISIONS_LOG + ACTIVE_TASKS — entrée signal currency gap |
| `52e39d0` | docs GAPS_RESIDUELS.md canonique (7 gaps P1-P3) |
| `4fde966` | feat telegram notifier GBPUSD live (alertes confiance > 65) |
| `b6b722e` | feat is_win / resolution_pips / resolved_at + v9_resolve_decision.py |
| `a303057` | feat validate-coherence.py — 7 checks DB live |
| `5fc39c5` | docs GAPS_RESIDUELS GAP-001 (décisions orphelines) |

**Chantiers non livrés / en attente :**

- ❌ Cron telegram notifier persistant (script `4fde966` existe, mode `--watch` démarré manuellement le 2026-07-07T09:00:15 — pas de cronjob enregistré)
- ❌ `workspace/perplexity/memory/memory.md` + `workspace/perplexity/exchange.md` (chantier B abandonné — alias `GAPS_RESIDUELS.md` créé à la place)

---

## Critères transition — ÉTAT OBJECTIF

Rappel doctrine V9 (DOCTRINE.md règle 16, 17, 19, 25) :

| Critère | Statut au 2026-07-07 10h08 CEST | Preuve |
|---------|--------------------------------|--------|
| 1. Flux EA live réel (timestamps avancent) | ✅ | `SELECT MAX(timestamp) FROM forces_snapshots` = `2026-07-07T08:07:45 UTC` |
| 2. `validate-ea` = VALIDE | ✅ | Aucun output ERROR dans logs depuis 2026-07-06 |
| 3. Pipeline signal bout-en-bout | ✅ | 7 signaux directionnels GBPUSD 2026-07-07, confiance 80–100 |
| 4. `zone_diagnostics` alimentée | ✅ | ZoneDetector `db11917` actif (9/10 principes ACTIVE déclenchables) |
| 5. `source_type` live dans decisions | ✅ | Colonne présente (commit `6a5d603`), valeurs `'live'` / `'replay'` |
| 6. Telegram actif | ✅ (partiel) | Script `--watch` opérationnel (2 messages envoyés 10:07:49 CEST), **mais pas de cron persistant** |
| 7. `validate-coherence.py` opérationnel | ✅ | Script livré (`a303057`), 20 tests verts, détecte GAP-001 (7 décisions orphelines) |
| 8. Tests verts | ✅ | **426 verts, 0 échec** (était 359 au checkpoint Phase 9 2026-07-05) |
| 9. WIN/LOSS ≥ 20 trades résolus (règle 25) | ❌ **NON REMPLI** | 0 décision résolue (`is_win`/`resolution_pips` tous NULL) — colonnes livrées `b6b722e`, saisie manuelle en attente |
| 10. Promotion SHADOW→ACTIVE ≥ 1 (hit_rate ≥ 60% sur ≥ 50 déclenchements) | ⚠️ PARTIEL | PRICE_LAG 3612× conf 100, POWER_ANGLE 295× conf 100, ZONE_RETEST 184× conf 70 — déjà ACTIVE, pas de hit_rate WIN/LOSS mesurable (cf. critère 9) |

**Doctrine règle 25** : "ne pas masquer l'incertitude" → WIN/LOSS ≥ 20 requis
avant promotion SHADOW→ACTIVE et avant déblocage Phase 10 sans réserve.

---

## Décision opérateur — TRANSITION AUTORISÉE

L'opérateur (CEO) autorise l'ouverture de la Phase 10 en **mode dégradé
assumé** le 2026-07-07 :

> "Phase 10 ouverte — WIN/LOSS suivi en parallèle via les colonnes
> `is_win` / `resolution_pips` (`b6b722e`). La règle 25 n'est pas
> contournée mais **différée** : les paper-trades Phase 10 alimenteront
> naturellement le compteur WIN/LOSS."

Cette décision est tracée ici par l'opérateur ; elle ne modifie pas la
doctrine mais autorise une **période de grâce** où Phase 10 tourne en
parallèle de la collecte WIN/LOSS via saisie manuelle.

---

## Gaps non bloquants archivés

- **GAP-001** : 7 décisions orphelines (signal_id introuvable) — voir `docs/architecture/GAPS_RESIDUELS.md` gap #8 et `workspace/perplexity/GAPS_RESIDUELS.md`. **Archivé**, rouverture si check 2 détecte de nouveaux orphelins post-fix `8697d84`.
- **Check 4 stale** : `validate-coherence.py` détecte ~2500 rangées `source_type='live'` datées du 2026-07-06 (>24h) — **normal**, correspond à l'historique J-1 du pipeline live. À ignorer tant que le pipeline live tourne en continu.

---

## Seuils `config.py` — GELÉS (non bloquant Phase 10)

Valeurs **réelles** au 2026-07-07 10h08 CEST (vérifiées dans `core/v9/config.py`) :

| Seuil | Valeur | Statut | Condition de promotion |
|-------|--------|--------|------------------------|
| `COALITION_THRESHOLD` | **5.38** | ✅ Appliqué (commit `fb5383a`) | n > 10 000 scènes + WIN/LOSS ≥ 20 |
| `ANTAGONISM_THRESHOLD` | **31.39** | ⏳ PROVISIONAL | convergence 3 runs + WIN/LOSS ≥ 20 |
| `PLIURE_THRESHOLD` | **1.7** | ⏳ PROVISIONAL | proxy corrigé (commit `e9bd9b1`) — à recalibrer sur pente réelle |

**Aucune modification de `core/v9/config.py` durant cette session.**

---

## Phase 10 — PÉRIMÈTRE OUVERT

Périmètre **minimal** (défini par l'opérateur) :

| Composant | Statut | Périmètre |
|-----------|--------|-----------|
| `core/v9/arbiter.py` | 🆕 À créer | Consolidation décisions multi-scénarios |
| `core/v9/risk_manager.py` | 🆕 À créer | Filtre avant paper trade (taille position, exposition) |
| Table `paper_trades` | 🆕 À créer | Simulation uniquement (zéro ordre réel avant Phase 12) |

**Périmètre exclu** (rappels doctrine) :

- ❌ Aucune logique d'exécution d'ordre avant **Phase 12** (interdit fondateur)
- ❌ Aucune modification de `core/v9/config.py` ou des YAML principes pour ce chantier
- ❌ Aucun agent / fédération avant validation explicite de l'opérateur (chantier gelé par règle 22)

---

## Signature

| Rôle | Nom | Date / Heure (CEST) | Décision |
|------|-----|---------------------|----------|
| Implémentation | Hermes | 2026-07-07 10h08 | ✅ Pipeline stable, 426 tests verts, 7 signaux live |
| Doctrine / Coordination | Perplexity | 2026-07-07 | ✅ Cohérence documentaire vérifiée |
| Opérateur (CEO) | Søn | 2026-07-07 | ✅ **Phase 9 canonisée** · ✅ **Phase 9 stable live** · ✅ **Phase 10 autorisée (mode dégradé)** |

---

## Références

- `docs/STATE.md` — état global du projet
- `docs/CACHE_BOARD.md` — chantiers actifs
- `docs/ROADMAP.md` — définition Phase 10
- `docs/DOCTRINE.md` — règles 16, 17, 19, 25 (critères transition)
- `docs/architecture/GAPS_RESIDUELS.md` — gaps résiduels P1-P3
- `workspace/perplexity/DECISIONS_LOG.md` — journal décisions datées
- `workspace/perplexity/GAPS_RESIDUELS.md` — alias workspace du canonique
- `workspace/perplexity/ACTIVE_TASKS.md` — tâches en cours
- `scripts/validate-coherence.py` — gardien DB live (commit `a303057`)
- `scripts/v9_resolve_decision.py` — saisie WIN/LOSS manuelle (commit `b6b722e`)
- `scripts/v9_telegram_notifier.py` — alertes live (commit `4fde966`)
- `logs/telegram_notifier.log` — preuve 2 messages 2026-07-07T10:07:49 CEST