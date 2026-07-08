# Comparaison doctrine realign — Phase D (2026-07-08)

Sources : `baseline_pre_20260708.md` (copié depuis feat/v9-foundation-clean@5ce0c65),
`baseline_post_20260708.md` (D2), `replay_delta_20260708.md` (D3). DB : snapshot
cohérent de `V9/data/v9_forces.db` (58201 decisions, 100743 forces_snapshots,
fenêtre 2026-07-01 → 2026-07-08, symbole GBPUSD quasi-exclusif).

## 1. Hit_rate delta par principe (9 node_rule + 18 grammar = 27)

| Principe | Kind | Statut | Evalué pré→post | Déclenché pré→post | HitRate pré→post | Delta |
|---|---|---|---|---|---|---|
| ANTAGONIST_NODE | node_rule | ACTIVE | 253→253 | 0→0 | 0.0%→0.0% | =0 |
| COALITION_NODE | node_rule | ACTIVE | 56634→57322 | 53→53 | 0.1%→0.1% | =0 |
| ELASTIC_BREATH | node_rule | ACTIVE | 56634→57322 | 5→5 | 0.0%→0.0% | =0 |
| GRAVITY_RESPRING_NODE | node_rule | ACTIVE | 56634→57322 | 253→256 | 0.4%→0.4% | =0 |
| NODE_BIRTH_FAST | node_rule | ACTIVE | 56634→57322 | 121→121 | 0.2%→0.2% | =0 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | node_rule | ACTIVE | 56634→57322 | 717→726 | 1.3%→1.3% | =0 |
| PRICE_LAG_AT_NODE_BIRTH | node_rule | ACTIVE | 56634→57322 | 10302→10320 | 18.2%→18.0% | -0.2pp |
| RAW_NODE_BIRTH | node_rule | ACTIVE | 56634→57322 | 121→121 | 0.2%→0.2% | =0 |
| ZONE_RETEST | node_rule | ACTIVE | 56633→57321 | 499→505 | 0.9%→0.9% | =0 |
| GRAMMAR_REGIME | grammar | ACTIVE | 57512→58201 | 0→0 | 0.0%→0.0% | =0 |
| GRAMMAR_{ABSORPTION,ANTAGONISME,BREAK,COALITION,CONTEXTE,CROISEMENT,EXHAUSTION,EXTENSION,GRAVITE,INVERSION,LEADER_FOLLOWER,LOCK,OPPOSITION,PULLBACK,RESPIRATION,SQUEEZE,TENSION} (16) | grammar | SHADOW | 57512→58201 (chacun) | 0→0 | 0.0%→0.0% | =0 |

**Lecture** : aucun principe ne bouge de hit_rate entre pré et post. L'écart d'Evalué
(+688 à +900 selon le principe) correspond à l'accumulation naturelle de bougies
entre les deux captures (quelques heures d'écart), pas à un effet du patch —
confirmé par D3 (0 divergence de signal sur 58200 snapshots rejoués). Les 17
principes nouvellement ACTIVE en catalogue (Phase C1, 10→27) restent à 0% : conditions
grammar encore vides (attendu, cf. Phase B/AUDIT_R29 — pas un bug de Phase D).

## 2. Latence vote majoritaire (p50/p95/p99)

**Donnée indisponible — pas de chiffre inventé.** `agent_telemetry.latency_ms`
existe en schéma mais contient 0 ligne (aucune instrumentation active). Proxy
tenté : `decisions.created_at - forces_snapshots.timestamp` (join sur
snapshot_id, 58201 lignes) → résultats incohérents (min -9.7M ms, p99 71.6M ms,
soit des écarts négatifs et des écarts de +20h), signe que ce join n'est pas un
proxy causal fiable de la latence de vote (horodatage de persistance ≠ horodatage
de calcul). Rejeté plutôt que rapporté comme mesure.

**Fallback proposé** : instrumenter `SignalGenerator` (vote majoritaire) avec
`time.perf_counter()` autour de l'agrégation des principes, écrire dans
`agent_telemetry.latency_ms` (colonne déjà prête, jamais alimentée) — mesure
réelle disponible dès le prochain cycle de collecte, pas de reconstruction a
posteriori possible sur les données actuelles.

## 3. Contexte_complet — ratio d'enrichissement

**100% (58201/58201 décisions)** ont un `contexte_complet_json` non vide avec
les 6 clés attendues (`signal, scene, behavior, window, exploitability, regime,
principle_evaluations`) — confirme le commit C4 ("déjà exhaustif, 0 filtre
trace"). `scene` et `behavior` sont non-vides sur 200/200 décisions échantillonnées.

**Anomalie détectée (hors scope fix Phase D)** : la longueur de la liste
`principle_evaluations` imbriquée varie anormalement sur un échantillon de 200 —
26 (92%, valeur attendue = 27 principes -1, à vérifier), mais aussi 208, 216, 144,
18 sur quelques décisions isolées. Signale un possible bug de duplication
d'écriture ou d'agrégation multi-snapshot dans `_load_principles` /
`contexte_complet`. À investiguer en Phase E — ne bloque pas la lecture hit_rate
(agrégée depuis `principle_evaluations`, table plate, non affectée).

## 4. Faux positifs suspects

Seuil littéral "hit_rate < 30%" englobe les 27/27 principes (max = 18.0% sur
PRICE_LAG_AT_NODE_BIRTH) — non discriminant pour un système à règles sélectives
par construction. Reformulé en "0% de déclenchement sur un large échantillon" :

- **GRAMMAR_REGIME** (ACTIVE, 58201 évals, 0 déclenchement) : seul principe
  ACTIVE de la famille grammar à ne jamais déclencher — statut ACTIVE non
  justifié tant que la condition reste vide.
- **ANTAGONIST_NODE** (ACTIVE, 253 évals seulement — 230x moins que les autres
  ACTIVE, 0 déclenchement) : déjà signalé par le script de calibration lui-même
  ("conditions marché non remplies ou bug d'intégration, gap zone_diagnostics
  comblé le 2026-07-06") — échantillon anormalement restreint à re-vérifier.
- Les 16 autres GRAMMAR_* (SHADOW, 0%) : conforme à leur statut, pas une anomalie.

**Anomalie transverse (bloque le hit_rate PAR DEVISE demandé en Phase D)** :
`principle_evaluations.currency` / `decisions.currency` = `"NZD"` sur 100% des
1 506 446 lignes, quel que soit le symbole réel (`GBPUSD` ou `EURUSD`, aucune
paire ne contient NZD). Bug de tagging devise en amont (probablement
`_build_currency_context` ou la construction de `decisions`/`principle_evaluations`) —
invalide toute segmentation par devise dans `baseline_post_20260708.md`
(colonnes "devise" toutes à NZD=0-1%). À corriger avant toute calibration future
par devise ; non bloquant pour le hit_rate global (basé sur `symbol`, correct).

## 5. Recommandations

| Principe(s) | Recommandation | Raison |
|---|---|---|
| PRICE_LAG_AT_NODE_BIRTH, GRAVITY_RESPRING_NODE, POWER_ANGLE_BREAK_TO_PRICE_IMPACT, ZONE_RETEST | **ACTIVE dur, aucune action** | Hit_rate stable pré/post, volume de déclenchements significatif (121-10320), aucune régression |
| COALITION_NODE, ELASTIC_BREATH, NODE_BIRTH_FAST, RAW_NODE_BIRTH | **ACTIVE, surveiller** | Hit_rate <0.2% stable — pas de régression mais échantillon 7j insuffisant pour conclure définitivement ; refaire ce comparatif après 30j |
| ANTAGONIST_NODE | **Refactor / investiguer avant tout maintien ACTIVE** | 0 déclenchement, échantillon 230x plus faible que les pairs — bug d'intégration suspecté, déjà noté par le script lui-même |
| GRAMMAR_REGIME | **Re-SHADOW jusqu'à condition réelle implémentée** | Seul ACTIVE de la famille grammar à 0% — statut ACTIVE prématuré sans logique de déclenchement |
| 16 GRAMMAR_* restants | **Rester SHADOW** | Conforme Phase B (conditions non finalisées) ; repasser en ACTIVE dur seulement après implémentation + hit_rate > 0% observé en SHADOW |
| Latence vote | **Instrumenter `agent_telemetry.latency_ms`** | Colonne vide — aucune mesure possible sans instrumentation ; fallback proposé section 2 |
| Tagging devise (`currency`="NZD" partout) | **Corriger en priorité avant calibration par devise** | Invalide toute analyse "hit_rate par devise" demandée en Phase D |
| `principle_evaluations` longueur variable dans `contexte_complet` | **Investiguer (Phase E)** | Anomalie de volume (26 à 216 entrées selon décision), ne bloque pas le hit_rate global mais fragilise le replay détaillé |

---
*Écarts hit_rate = 0 partout où deux mesures existent (pré/post) : le patch
doctrine realign (Phase B+C) n'a introduit aucune régression comportementale
sur les signaux déjà produits. Les axes ouverts (latence, devise, longueur
contexte) sont des dettes préexistantes, révélées par cette calibration, pas
introduites par le patch.*
