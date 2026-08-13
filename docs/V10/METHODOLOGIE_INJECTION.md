# MÉTHODOLOGIE D'INJECTION — Contrat de travail multi-IA (ZCode, Hermes, Perplexity)

> **Mandat CEO (13/08)** : *"est-ce que si on injecte toutes ces règles avant
> toute la lecture comportement et interprétation, ne sera pas biaisé pour la
> suite ?... implémente cette méthodologie et façon de procéder afin
> d'optimiser la lecture du comportement qui doit être plus fiable avec ma
> vision... met tous les documents et git à jour pour que session Hermes et
> Perplexity qui a seulement le git puisse aussi travailler en parallèle."*
>
> **Ce document est le CONTRAT DE TRAVAIL pour toutes les IA.** Il définit
> ce qu'on peut faire, ce qu'on ne peut PAS faire, et la méthode pour
> transformer la lecture de Søn en système fiable.

---

## 1. LA RÈGLE D'OR (la loi suprême)

> **Le brainstorming de Søn est la source de vérité. L'implémentation suit,
> ne précède pas.**
>
> - On ne code pas ce qu'on ne comprend pas complètement
> - On ne teste pas ce qu'on a mal interprété
> - On attend que la lecture de Søn soit COMPLÈTE avant d'injecter
> - On injecte UNIQUEMENT les piliers stables et validés

---

## 2. LES 3 PISTES PARALLÈLES

### PISTE A — BRAINSTORMING (Søn ↔ IA, source de vérité)

```
QUI    : Søn donne sa lecture, par fragments, librement
       : L'IA reformule, juxtapose, documente — NE CODE RIEN
QUOI   : Les 7 piliers de la lecture de marché
       :   P1 Cinématique (la courbe avant la valeur)
       :   P2 Imbrication temporelle (H4 juge, H1 timing, M15 exécution)
       :   P3 Coalition multidevise (leader/follower, rupture risk-on)
       :   P4 Personnalité de devise (tempo, véracité, comportement)
       :   P5 Fractalité temporelle (1min → H4, TF par devise)
       :   P6 Cycles Fatman (naissance/expansion/maturité/épuisement)
       :   P7 Forces par timeframe (échelles propres, croisement + zones
       :      extrêmes + double test de rejet + propagation/répulsion)
RÈGLE  : Chaque réponse de Søn → document mise à jour + git commit
       : Chaque document est VIVANT (statut : en cours / validé / à valider)
```

### PISTE B — IMPLÉMENTATION (seulement les piliers STABLES)

```
QUI    : ZCode / Hermes
QUOI   : UNIQUEMENT les piliers COMPLETS et VALIDÉS par Søn
       :   ✅ P1 Cinématique (codé 13/08, validé par benchmark)
       :   ✅ P2 Confluence TF (codé 13/08, validé par benchmark)
       :   ⬜ P3-P7 : EN ATTENTE du brainstorming complet
RÈGLE  : Pas de code basé sur une interprétation partielle
       : Pas de test sur une règle mal comprise
       : Chaque règle injectée = testée (benchmark 3 jours) AVANT adoption
```

### PISTE C — TEST (file d'attente, pas de précipitation)

```
QUI    : ZCode / Hermes
QUOI   : Benchmarks sur données réelles (3 jours minimum)
       : Chaque règle est testée AVANT adoption
       : Les règles qui détériorent sont REJETÉES (ex: momentum mort BLOCK)
       : Les règles qui améliorent sont ADOPTÉES (ex: cinématique)
RÈGLE  : Un test ne se fait qu'APRÈS validation de l'interprétation
       : Jamais de test sur une règle mal comprise
```

---

## 3. CE QU'ON PEUT FAIRE SANS BIAIS (en parallèle)

Ces tâches n'interprètent PAS la lecture de Søn — elles préparent
l'infrastructure. Elles peuvent être faites par TOUTES les IA en parallèle.

| Tâche | Pourquoi pas de biais | Qui |
|---|---|---|
| **Calibrer les zones par TF (percentile)** | Calcul statistique pur, pas d'interprétation | ZCode / Hermes |
| **Préparer les squelettes de modules (P3-P7)** | Architecture vide, règles injectées plus tard | ZCode / Hermes |
| **Scanner SHADOW continu (cron */20)** | Accumule des données pour les futurs tests | Cron |
| **Daily learning (track record)** | Construit l'historique forward | Cron/manuel |
| **Suivre les trades shadow (open/resolve)** | Track record R10 | Cron |
| **Vérifier la fraîcheur des données** | Qualité des données, pas d'interprétation | Toutes |
| **Health check / garde-fous** | Sécurité R10, pas d'interprétation | Toutes |

---

## 4. LES DOCUMENTS DE RÉFÉRENCE (hiérarchie de vérité)

### Niveau 1 — LA LOI (le contrat)

| Document | Rôle |
|---|---|
| `docs/V10/METHODOLOGIE_INJECTION.md` | **Ce fichier** — contrat de travail multi-IA |
| `docs/V10/POINT_GENERAL_INSTITUTIONNEL.md` | Tableau de bord 7 piliers + état |

### Niveau 2 — LA LECTURE (source de vérité, vivant)

| Document | Pilier | Statut |
|---|---|---|
| `docs/V10/BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` | P1+P2+P3 | 🔶 En cours (12 blocs) |
| `docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` | P4+P5+P6 | 🔶 En cours (15 blocs) |
| `docs/V10/LECTURE_FORCES_PAR_TIMEFRAME.md` | P7 | 🔶 En cours (5 règles) |
| `docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` | P6+P7 | 🔶 En cours (5 règles) |
| `docs/V10/DOCTRINE_LECTURE_GBPUSD.md` | Tous | 🔶 À mettre à jour |
| `docs/V10/LECTURE_GBPUSD_QUESTIONS_REGLES.md` | P1 | 🔶 Historique (absorbé) |

### Niveau 3 — LES DÉCISIONS (trace)

| Document | Rôle |
|---|---|
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Chaque décision tracée (DEC-xxx) |
| `docs/V10/DECISION_OVERLAP_VS_SCAN_LARGE.md` | Option C (edge ciblé) |

### Niveau 4 — L'ÉTAT (runtime)

| Document | Rôle |
|---|---|
| `docs/V10/STATE.md` | État pipeline complet |
| `reports/*.json` | Rapports horodatés (edge, replay, learning) |

---

## 5. LE PROCESS DE TRAVAIL (pour chaque IA)

### ZCode / Hermes (session interactive avec Søn)

```
1. LIRE : docs/V10/METHODOLOGIE_INJECTION.md + POINT_GENERAL_INSTITUTIONNEL.md
2. BRAINSTORMING : si Søn répond → reformuler, documenter, commit (Piste A)
3. IMPLÉMENTATION : si pilier validé → coder + tester + commit (Piste B)
4. TEST : si règle codée → benchmark 3 jours AVANT adoption (Piste C)
5. COMMIT : atomique, DECISIONS_LOG à jour, STATE.md à jour
6. NE PAS : coder un pilier non validé par le brainstorming
```

### Perplexity (session git seule, sans Søn)

```
1. LIRE : docs/V10/METHODOLOGIE_INJECTION.md + POINT_GENERAL_INSTITUTIONNEL.md
         + tous les docs BRAINSTORMING/LECTURE (Niveau 2)
2. PRÉPARER : squelettes de modules P3-P7 (sans règles)
3. CALIBRER : zones par TF (percentile) — calcul statistique pur
4. TESTER : les piliers déjà codés (P1 cinématique, P2 confluence)
5. NE PAS : inventer des règles de lecture — la source de vérité est Søn
6. COMMIT : atomique, DECISIONS_LOG à jour
```

---

## 6. LES PILIERS — ÉTAT D'AVANCEMENT (13/08 21:30)

| Pilier | Document | Interprété par Søn ? | Codé ? | Testé ? |
|---|---|---|---|---|
| P1 Cinématique | DOCTRINE_LECTURE_GBPUSD | ✅ Oui | ✅ Oui | ✅ Oui (WR 63%) |
| P2 Imbrication TF | MATRICE_INSTITUTIONNEL | ✅ Oui | ✅ Oui | ✅ Oui (confluence) |
| P3 Coalition multidevise | MATRICE_INSTITUTIONNEL | 🔶 Partiel (blocs 3.1-3.4) | ❌ Non | ❌ Non |
| P4 Personnalité de devise | FATMAN_DEVISE_FRACTAL | 🔶 Partiel (blocs 1.1-1.3) | ❌ Non | ❌ Non |
| P5 Fractalité temporelle | FATMAN_DEVISE_FRACTAL | 🔶 Partiel (blocs 3.1-3.3) | 🔶 Partiel (confluence) | 🔶 Partiel |
| P6 Cycles Fatman | FATMAN_DEVISE_FRACTAL + CHANGEMENT_PHASE | 🔶 Partiel (exemple 11-13/08) | ❌ Non | ❌ Non |
| P7 Forces par TF | FORCES_PAR_TIMEFRAME + CHANGEMENT_PHASE | 🔶 Partiel (5 règles) | ❌ Non | ❌ Non |

### Règle d'injection

Un pilier passe de "partiel" à "validé" quand Søn a répondu à TOUTES les
questions du bloc (ou dit "c'est bon"). Seulement ensuite : code + test.

---

## 7. LES 20 RÈGLES EN ATTENTE (file d'attente d'injection)

| # | Règle | Pilier | Bloc source | Statut |
|---|---|---|---|---|
| 1 | Calibration par TF (percentile) | P7 | FORCES_PAR_TIMEFRAME R1 | ⏳ En attente validation |
| 2 | Lecture par TF (zones) | P7 | FORCES_PAR_TIMEFRAME R2 | ⏳ En attente |
| 3 | Croisement M5 + zones extrêmes M15/M30 | P7 | FORCES_PAR_TIMEFRAME R3 | ⏳ En attente |
| 4 | Double test de rejet de prix | P7 | FORCES_PAR_TIMEFRAME R4 | ⏳ En attente |
| 5 | Propagation vs Répulsion | P7 | FORCES_PAR_TIMEFRAME R5 | ⏳ En attente |
| 6 | Détecteur de vagues (impulsion/correction) | P6 | FATMAN_DEVISE_FRACTAL 4.1 | ⏳ En attente |
| 7 | Phases du cycle (naissance/expansion/maturité/épuisement) | P6 | FATMAN_DEVISE_FRACTAL 4.2 | ⏳ En attente |
| 8 | Calibrage cycle par devise | P6 | FATMAN_DEVISE_FRACTAL 4.3 | ⏳ En attente |
| 9 | Tempo par devise | P4 | FATMAN_DEVISE_FRACTAL 1.1 | ⏳ En attente |
| 10 | Véracité par devise | P4 | FATMAN_DEVISE_FRACTAL 1.2 | ⏳ En attente |
| 11 | Comportement de session par devise | P4 | FATMAN_DEVISE_FRACTAL 1.3 | ⏳ En attente |
| 12 | Force normalisée par session | P4 | FATMAN_DEVISE_FRACTAL 2.1 | ⏳ En attente |
| 13 | Leader/follower (qui mène) | P3 | MATRICE 3.1 | ⏳ En attente |
| 14 | Rupture de coalition risk-on | P3 | MATRICE 3.2 | ⏳ En attente |
| 15 | Safe haven (JPY/CHF → risk-off) | P3 | MATRICE 3.3 | ⏳ En attente |
| 16 | Cross-pair confirmation (EURGBP) | P3 | MATRICE 3.4 | ⏳ En attente |
| 17 | Couche 1min (timing d'entrée scalp) | P5 | FATMAN_DEVISE_FRACTAL 3.1+5.1 | ⏳ En attente |
| 18 | TF de lisibilité par devise | P5 | FATMAN_DEVISE_FRACTAL 3.3 | ⏳ En attente |
| 19 | Emboîtement H1→H4 + croisement H4 = changement de phase | P6 | CHANGEMENT_PHASE R1-R2 | ⏳ En attente |
| 20 | Antagonisme = retournement + confirmation TF < | P6 | CHANGEMENT_PHASE R3-R5 | ⏳ En attente |

**Chaque règle passe par : brainstorming (Søn) → validation → code → test
(benchmark 3 jours) → adoption ou rejet.**

---

## 8. LES RÈGLES DÉJÀ ADOPTÉES (P1-P2, ne pas toucher)

| Règle | Module | Impact mesuré |
|---|---|---|
| Cinématique (exhaustion/divergence BLOCK) | `v10_cinematics.py` | WR 60→63%, 45% faux signaux bloqués |
| Confluence TF (sizing modulé) | `v10_confluence_tf.py` | Protection jours difficiles (-8p sur 13/08) |
| Option C (edge ciblé + exploration) | `v10_edge_overlap_filter.py` | Exécution = edge prouvé uniquement |
| Garde-fous (circuit breaker/news/corrélation) | `v10_decision_pipeline.py` | R10 renforcé |
| Suivi trades shadow (open/resolve) | `v10_shadow_edge_overlap.py` | Track record R10 possible |

---

## 9. QUE FAIRE EN CAS DE DOUTE

```
1. TOUJOURS lire METHODOLOGIE_INJECTION.md en premier
2. Si une règle n'est pas validée par le brainstorming → NE PAS la coder
3. Si une interprétation est ambiguë → documenter la question, NE PAS deviner
4. Si un test échoue → vérifier si c'est la règle ou l'interprétation
5. Si Søn donne une réponse → documenter + commit IMMÉDIATEMENT (Piste A)
6. Jamais d'invention de règles de lecture — la source de vérité est Søn
```

---

> **Ce document est la loi.** Toute IA (ZCode, Hermes, Perplexity) qui
> travaille sur ce projet DOIT le lire et le respecter. La lecture de Søn
> est la source de vérité. L'implémentation suit, ne précède pas.