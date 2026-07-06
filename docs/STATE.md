# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-06 15h34 CEST — news_context livré (354 tests, pipeline complet et opérationnel)

## Statut opérationnel actuel

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité
       → Régime → Principes → Signal → Décision

✅ Bout-en-bout fonctionnel
✅ 3 signaux haussiers GBPUSD conf 80-100 produits en live
✅ 354 tests verts
✅ 10/10 principes ACTIVE débloqués
✅ 31 champs contexte propagés (26 précédents + 5 news)
✅ Contexte news actif : news_phase PRE_NEWS/NEWS_SHOCK/POST_NEWS/NEUTRE
```

---

## Session NewsContext (2026-07-06 — session 2)

Commits [`05f8232`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/05f8232) + [`f278a1e`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/f278a1e6c9e224acef6277576a97db225b99e0ed) | **354 tests verts** (+7).

### Philosophie inscrite dans le code
```
# Le système ne trade pas les news. Il lit les flux de liquidité
# qui les précèdent et la réorganisation des coalitions qui suit.
# La news est un repère temporel. Les forces sont la réalité.
# — Perplexity, architecte externe V9, 2026-07-06
```

### Module créé : core/v9/news_context.py
- Module pur : aucune I/O DB, aucun import orchestrateur
- Interface : `NewsContext().assess(utc_dt)` → dict 5 champs
- Calendrier statique : `data/economic_calendar.json` (7 règles : NFP, ISM_PMI, CPI_US, FOMC_RATE, FOMC_MINUTES, GDP_US, RETAIL_SALES_US)
- Prio multi-news : distance min puis importance HIGH > MEDIUM > LOW
- Tolérance ±3 min sur heure typique

### 5 champs PROPAGÉS (injectés EN DERNIER dans _load_shared_context)
```
news_type          : str | None    # "NFP" / "ISM_PMI" / "CPI_US" / "FOMC_RATE" / None
news_phase         : str           # "PRE_NEWS" / "NEWS_SHOCK" / "POST_NEWS" / "NEUTRE"
news_distance_min  : int | None    # >0=futur, <0=passée, None si NEUTRE
news_importance    : str           # "HIGH" / "MEDIUM" / "LOW" / "NEUTRE"
news_session_clean : bool          # True = aucune news HIGH dans 90 prochaines min
```

### Placement doctrine respecté
Injection après TOUS les `context.update()` existants —
leçon bug ANTAGONIST_NODE (ne jamais écraser un bloc `update()` antérieur).

### Tests : tests/test_news_context.py (7 tests)
- test_news_context_pre_news_45min_avant
- test_news_context_shock_5min_apres
- test_news_context_post_news_30min_apres
- test_news_context_neutre_hors_fenetre
- test_news_context_clean_session_sans_news_proche
- test_news_context_fallback_calendar_vide
- test_news_context_champs_propages_dans_shared_context

---

## Session Déblocage pipeline signaux (2026-07-06)

Commit [`c7bc76b`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/c7bc76b36e8b5e4ca2a0bacbc3b836484f9749d3) | **347 tests verts**.
3 goulets d'étranglement corrigés :
1. `REGIMES_INADEQUATS` contenait NEUTRE — rejeté
2. `_determine_status` toujours `non_exploitable` sur `window=absente` — fixé
3. Principes perdus si `raison_absence != None` + re-évaluation in-memory — fixé

Impact : 0 → 3 signaux haussiers GBPUSD conf 80-100.

---

## Session ANTAGONIST_NODE (2026-07-06)

Commit [`7466f01`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/7466f0186e9bcd8a78a32ee8e18d3fbc52bc1da7) | **347 tests verts** (+4).
Bug fallback cross-TF écrasant `h1_state/h1_dir/m5_state/m5_dir` par None après `context.update()`.
10/10 principes ACTIVE techniquement débloqués.

---

## Session Calibration Live + Tuning YAML (2026-07-06)

**343 tests verts**. 3 commits : `046b285` / `35939aa` / `ecc056b`.
2245 snapshots / 1708 scènes / 0 signaux (pré-déblocage pipeline).
8 YAML enrichis avec 13 nouveaux champs contexte. `config.py` inchangé.
`DOCTRINE.md` 19 → 27 règles. Commit [`2a970cf`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/2a970cf98551c62f2506e20e6699b53d27432763).

---

## Session Coalition Intelligence (2026-07-06)

**339 tests verts**. 13 champs contexte + CONTEXT_CONTRACT.md + gardien auto.
Commits : cd50cd7 / 4ebf86a / 24c0653 / 4d6cf53 / 44c8ae4 / 6648d27

---

## Correctif Phase 9.5 (2026-07-06) — observabilité DST US
Correctif `market_status_warning()`. `core/v9/*` inchangé. 269 tests verts.

## Phase 9 TERMINÉE (2026-07-05)
Chaîne cognitive complète. 27 principes YAML (10 ACTIVE / 17 SHADOW).
Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE9.md`.

## PHASES 1→8 TERMINÉES
Voir `docs/checkpoints/`.

---

## Décisions actées
- V9 from scratch. GitHub = source de vérité. V8 = migration curée.
- CONTEXT_CONTRACT.md + test_context_propagation.py = gardien de propagation.
- DOCTRINE.md 27 règles (calibration-first, sessions, YAML, fallbacks).
- COALITION_THRESHOLD → reporté à n>5000 scènes + WIN/LOSS.
- news_context.py : la news = repère temporel, jamais déclencheur.
- Tout fallback dans `_load_shared_context` TOUJOURS placé AVANT ou après
  son `context.update()` selon sa logique — jamais l'inverser.

## Objectif immédiat
**Observer les premiers signaux post-ISM PMI avec news_context actif.**
Lancer après 16h Paris :
```
python scripts/v9_dashboard.py --watch decisions --once
python scripts/v9_calibration.py --principes
```
Suivre : ANTAGONIST_NODE se déclenche-t-il sur NEWS_SHOCK ISM PMI ?
Suivre : POWER_ANGLE_BREAK_TO_PRICE_IMPACT sur POST_NEWS ?

## Chantiers en file
1. **Test bout-en-bout** — snapshot → signal (fixture manquante critique)
2. **YAML news-aware** (session 3) — POWER_ANGLE, NODE_BIRTH, COALITION, ANTAGONIST note
3. **Calibration --principes** — relancer à ~500 scènes post-tuning YAML
4. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS
5. **Métriques DORMANT P2** — contexte_temporel.fenetre + declencheur + variante
6. **Promotion SHADOW→ACTIVE** — décision sur base hit_rate live (règle 25)
7. AGENT.md racine V9
8. Inventaire migration V8 → V9

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code / Hermes / MiniMax : implémentation selon périmètre assigné

## Règle d'or
Aucune implémentation structurante sans ancrage explicite dans la doctrine V9.
Toute métrique ajoutée tracée dans CONTEXT_CONTRACT.md.
Tout fallback dans `_load_shared_context` — ordre respecté par rapport aux `context.update()`.
