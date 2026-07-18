# AUDIT DOCTRINE V9 — Réalignement CHARTE / DOCTRINE (Phase A)

## 0. Identification

- **Date** : 2026-07-08
- **Commande** : CEO — Audit exhaustif Phase A, réalignement CHARTE/DOCTRINE
- **Branche** : `feat/v9-foundation-clean`, HEAD audité : `e06f7e3`
- **État repo au moment de l'audit** : 703 tests verts, doctrine 30 règles immuables,
  10 principes `v9_status=ACTIVE` / 17 `SHADOW` (voir §5 sur la fiabilité de ce décompte)
- **Méthode** : lecture intégrale ligne à ligne des 6 documents doctrinaires cités par
  la commande, lecture intégrale des 27 YAML `core/v9/principles/*.yaml`, lecture du
  code source qui les consomme (`core/v9/principle_engine.py`, `core/v9/config.py`)
  pour vérifier que les affirmations documentaires correspondent au comportement
  réel (règle DOC_GOVERNANCE.md #1 : le code fait foi). Lecture seule stricte — aucun
  fichier de code modifié.
- **Document source des 4 contradictions déjà connues** :
  `docs/checkpoints/CHECKPOINT_20260707_REPRISE_TELEGRAM.md` (échange Søn/Hermes
  Telegram, 2026-07-07, non résolu à ce jour — Phase 9.8 a été réaffectée au
  heartbeat/VPS-ready, la révision R25 n'a jamais eu lieu, voir §4.2).

---

## 1. Cartographie des documents doctrinaires

| Document | Version / statut | Dernière évolution de fond | Constat |
|---|---|---|---|
| `docs/doctrine/CHARTE_COGNITIVE_V9.md` | v0.1, datée 2026-07-05 | Aucune depuis création | **Gelée depuis 3 jours de sprints intensifs**, 130 lignes, jamais republiée malgré 27→30 règles DOCTRINE et l'ajout des Règles 29/30 (zone-type, WIN/LOSS) qui redéfinissent en pratique la chaîne cognitive et le vocabulaire |
| `docs/DOCTRINE.md` | 30 règles | 2026-07-08 (Règle 30, sprint CEO nuit) | Document vivant, mis à jour à chaque session ; c'est lui qui absorbe tout le nouveau vocabulaire métier (zone-type, SDI, news_phase, arbiter) sans que CHARTE ne soit retouchée en miroir |
| `docs/doctrine/MEMORY_POLICY_V9.md` | non versionné | — | Court (69 lignes), cohérent, pas de contradiction directe détectée avec CHARTE |
| `docs/doctrine/ORCHESTRATION_POLICY_V9.md` | non versionné | — | Court (58 lignes), rôles d'agents définis mais **non synchronisés** avec l'implémentation Mode A réelle (§4.4, friction F9) |
| `docs/doctrine/MIGRATION_POLICY_V9.md` | non versionné | — | Court (50 lignes), règle A/B/C/D claire mais **contournée** pour l'import de la Règle 29 (§4.3, friction F7) |
| `docs/architecture/CONTEXT_CONTRACT.md` | vivant, mis à jour à chaque session | 2026-07-07 (consolidation C-1) | Bien tenu, aligné avec le code, sert de garde-fou factuel pour cet audit |

**Constat transversal** : CHARTE_COGNITIVE_V9.md est le seul document de la liste à n'avoir
jamais été révisé depuis sa création, alors qu'il se présente comme « document fondateur »
(L.4) faisant autorité sur toute architecture et tout vocabulaire V9 (L.56, L.98). Les 5 autres
documents ont tous évolué avec le code. C'est la cause racine structurelle de la majorité des
frictions listées en §4 : DOCTRINE.md et le code citent une autorité (CHARTE) qui ne connaît
pas les concepts qu'on lui fait porter.

---

## 2. Inventaire des 27 YAML `core/v9/principles/`

### 2.1 Tableau complet

| id | kind | origin | v9_status (YAML) | v9_status (réel, `config.PRINCIPLE_ACTIVE_IDS`) | conditions | seuils chiffrés | Qualité |
|---|---|---|---|---|---|---|---|
| ANTAGONIST_NODE | node_rule | V7 | ACTIVE | ACTIVE | 5 conditions, dont cross-TF `h1_dir != m5_dir` | aucun seuil numérique inventé | Bonne — conditions concrètes, 6 nœuds loggés en réel |
| COALITION_NODE | node_rule | V7 | ACTIVE | ACTIVE | 5 conditions (state, coalition_strength, mtf_score, risk_sentiment, news_allow) | `coalition_strength >= 0.5`, bounds 0.4–1.0 — non sourcés à une calibration citée dans le fichier | 0 émis à ce jour (« DORMANT » dans les notes, terme à ne pas confondre avec CONTEXT_CONTRACT DORMANT — voir §5) |
| ELASTIC_BREATH | node_rule | V7 | ACTIVE | ACTIVE | 2 conditions | `absorbed_pullbacks >= 1` | 0 émis à ce jour |
| GRAVITY_RESPRING_NODE | node_rule | V7 | ACTIVE | ACTIVE | 4 conditions | aucun seuil numérique propre (bounds `{}`) | 0 émis, note « conditions jamais réunies » |
| NODE_BIRTH_FAST | node_rule | V7 | ACTIVE | ACTIVE | 7 conditions | `z_current >= 1.0`, `bars_in_extreme <= 2`, bounds 1.0–2.5 / 1–8 | Seul principe avec preuve statistique en note (« WR30j=71% n=31 ») |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | node_rule | V7 | ACTIVE | ACTIVE | 3 conditions | `tension_score >= 1.0`, bounds 0.7–2.0, `news_distance_min` [-60,0] | 0 émis à ce jour |
| RAW_NODE_BIRTH | node_rule | V7 | ACTIVE | ACTIVE | 5 conditions | bounds `bars_in_extreme` 1–10 | 84 nœuds loggés, aucune résolution exploitée |
| ZONE_RETEST | node_rule | V7 | ACTIVE | ACTIVE | 4 conditions (dont ancre YAML `&id001`/`*id001`) | bounds `bars_in_extreme` 1–6 | 73 nœuds loggés |
| PRICE_LAG_AT_NODE_BIRTH | node_rule | V7 | ACTIVE | ACTIVE | 4 conditions, dont `stale == false` (stale-guard Phase 14b) | `tension_score >= 0.5`, bounds 0.3–1.5 | 0 émis à ce jour, guard anti-fantôme ajouté 2026-07-08 |
| GRAMMAR_REGIME | grammar | V6 | ACTIVE | ACTIVE | **`conditions: []`** | bounds informatifs `risk_sentiment` 0–3, `coalition_mtf_score` 2–6 | **Anomalie critique — voir §5.1 : structurellement non-émetteur malgré ACTIVE** |
| GRAMMAR_ABSORPTION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_ANTAGONISME | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_BREAK | grammar | V8_NATIVE | SHADOW | SHADOW | `[]` | bounds informatifs `coalition_mtf_score` 2–6, `risk_confidence` 60–100 | Stub enrichi (commentaires) mais toujours 0 condition |
| GRAMMAR_COALITION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_CONTEXTE | grammar | V6 | SHADOW | SHADOW | `[]` | bounds informatifs `coalition_mtf_score` 2–6, `risk_confidence` 60–100 | Stub enrichi (13 champs documentés en note) mais toujours 0 condition |
| GRAMMAR_CROISEMENT | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_EXHAUSTION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_EXTENSION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_GRAVITE | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_INVERSION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_LEADER_FOLLOWER | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_LOCK | grammar | V8_NATIVE | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_OPPOSITION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_PULLBACK | grammar | V6 | SHADOW | SHADOW | `[]` | bounds informatifs `bascule_intensite` 0–50, `persistance_confirmee` 0–1 | Stub enrichi (note détaille 2 sessions d'enrichissement) mais 0 condition |
| GRAMMAR_RESPIRATION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_SQUEEZE | grammar | V8_NATIVE | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |
| GRAMMAR_TENSION | grammar | V6 | SHADOW | SHADOW | `[]` | aucun | Stub documentaire pur |

**Total** : 9 `node_rule` (tous ACTIVE, conditions non vides, tous émetteurs potentiels réels) +
18 `grammar` (dont 1 seul, GRAMMAR_REGIME, marqué ACTIVE — tous les 18 ont `conditions: []`).
9 + 18 = 27. Origine par fichier : 9 `node_rule` en `origin: V7`. Sur les 18 `grammar` : 15 en
`origin: V6` (ABSORPTION, ANTAGONISME, COALITION, CONTEXTE, CROISEMENT, EXHAUSTION, EXTENSION,
GRAVITE, INVERSION, LEADER_FOLLOWER, OPPOSITION, PULLBACK, REGIME, RESPIRATION, TENSION) et
3 en `origin: V8_NATIVE` (BREAK, LOCK, SQUEEZE).

### 2.2 Divergence code/doc sur le nombre de principes `kind: grammar`

`core/v9/principle_engine.py` L.16-25 (docstring de module) affirme :

> « Les 20 principes `kind: grammar` sont des entrées de vocabulaire documentaires
> (conditions vides, non émettrices en V8 déjà) »

Le comptage réel sur les 27 fichiers YAML donne **18** fichiers `kind: grammar** (17 SHADOW +
GRAMMAR_REGIME ACTIVE), pas 20. Et la même docstring affirme « 7 des 9 principes `kind:
node_rule` ACTIVE sont désormais déclenchables […] 2 principes ACTIVE restent hors périmètre
(ANTAGONIST_NODE […] ; COALITION_NODE […]) » — cette phrase est elle-même datée (elle décrit un
état où ANTAGONIST_NODE/COALITION_NODE n'étaient pas encore alimentés) et n'a pas été mise à
jour alors que le paragraphe suivant dans le même docstring dit que ces deux champs sont
« désormais alimentés ». **Cette docstring viole DOC_GOVERNANCE.md règle 1** (le code est la
source de vérité, un docstring qui contredit son propre fichier de constantes —
`PRINCIPLE_ACTIVE_IDS` dans `config.py` L.199-210, qui liste exactement 9 node_rule + 1
grammar = 10 — est un bug documentaire à corriger dans le code lui-même).

---

## 3. Frictions CHARTE ↔ DOCTRINE

### 3.1 Rappel — frictions déjà identifiées (Telegram 2026-07-07, non résolues)

Le document source (`CHECKPOINT_20260707_REPRISE_TELEGRAM.md` L.79-93) annonce en prose
« **4 contradictions directes** » (L.9) mais son propre tableau (L.84-93) n'en tague que
**3** comme `Contradiction` (🔴) : R20, R25, R27. Les 5 autres lignes du tableau sont taguées
`Tension` (🟡) : R3, R10, R13, R22, R23. **La 4ᵉ contradiction annoncée en prose n'existe nulle
part dans le document** — c'est en soi une incohérence dans le matériau d'entrée de cet audit
(à signaler au CEO, voir §3.2 friction F0).

| # | Règle DOCTRINE | Détail règle | CHARTE (extrait, ligne) | Sévérité |
|---|---|---|---|---|
| R3 | `Pas de signal si exploitabilité != exploitable` (DOCTRINE L.28) | conditionne l'émission d'un signal au statut d'exploitabilité | Règle 2, CHARTE L.105-106 : « Une lecture juste peut ne produire aucun trade. C'est normal. » | 🟡 Tension |
| R10 | `MT4 (forces) dicte, MT4 (ticks) confirme` (DOCTRINE L.35) | non implémenté (Phase 11 future) | Priorité 1, CHARTE L.16 : « fidélité de lecture » | 🟡 Tension |
| R13 | `Le système observe d'abord, agit ensuite (paper → réel)` (DOCTRINE L.38) | | Priorité 6, CHARTE L.21 : « automatisation en dernier » | 🟡 Tension |
| R20 | `Calibration-first` (DOCTRINE L.45) | lancer `v9_calibration.py --analyze` avant tout chantier sur marché ouvert | Interdit #4, CHARTE L.51 : « Introduire un outillage […] avant d'avoir localisé sa place exacte dans la chaîne cognitive » | 🔴 Contradiction |
| R22 | `Une session = une livraison complète` (DOCTRINE L.47) | | Règle 4, CHARTE L.111-112 : « Architecture avant code » | 🟡 Tension |
| R23 | `Principes YAML mis à jour dans la même session que le champ contexte` (DOCTRINE L.48) | | Règle 4, CHARTE L.111-112 | 🟡 Tension |
| R25 | `Promotion SHADOW → ACTIVE… hit_rate >= 60% sur >= 50 déclenchements` (DOCTRINE L.50) | filtrage par rentabilité | Interdit #4 (CHARTE L.50) + Règle 3 (CHARTE L.108-109 : « La mémoire sert d'abord à conserver et confronter les lectures ») | 🔴 Contradiction |
| R27 | `Champ DORMANT > 2 phases → promu ou supprimé` (DOCTRINE L.52) | pression de suppression de données de perception non consommées | Règle 3, CHARTE L.108-109 | 🔴 Contradiction |

**Statut de résolution au 2026-07-08** : aucune. Le checkpoint prévoyait un chantier « Phase
9.8 — Révision R25 » avec 3 options (A/B/C, L.104-107). `git log` et `docs/STATE.md` montrent
que le nom « Phase 9.8 » a été réaffecté au chantier heartbeat/VPS-ready (commit `4aa4fd3`,
STATE.md L.11-12, L.39-40) — **la décision Søn sur R25 n'a jamais été prise ni documentée dans
`DECISIONS_LOG.md`**. DOCTRINE.md L.50 (R25) est toujours formulée exactement comme au moment
du diagnostic Telegram. Les règles 29 (L.187) et 30 (L.184-188) — ajoutées après le diagnostic
— **citent R25 comme rendant leurs propres seuils légitimes** (« Aucune promotion SHADOW→ACTIVE
sans DECISIONS_LOG datée », « Aucun seuil chiffré inventé (règle 25) ») : une règle déjà
identifiée comme contradictoire à la CHARTE sert maintenant de fondement à deux règles
supplémentaires. La dette de friction s'est donc **propagée**, pas résorbée, entre le
2026-07-07 et le 2026-07-08.

### 3.2 Nouvelles frictions — CONTRADICTIONS (🔴)

**F0 — Incohérence du décompte des contradictions dans le document de référence.**
`CHECKPOINT_20260707_REPRISE_TELEGRAM.md` L.9 annonce 4 contradictions directes ; son tableau
L.84-93 n'en documente que 3. Aucune trace d'une 4ᵉ contradiction n'existe dans
`workspace/perplexity/memory/DECISIONS_LOG.md` ni dans `docs/STATE.md`. Proposition de
refonte : soit retrouver/reconstruire la 4ᵉ contradiction manquante (relire le fil Telegram
source si archivé ailleurs), soit corriger le checkpoint pour dire « 3 contradictions directes
+ 5 tensions », et ne plus citer « 4 » dans aucun document dérivé (y compris la commande de
cet audit, qui reprend le chiffre 4).

**F1 — GRAMMAR_REGIME classé ACTIVE dans `config.PRINCIPLE_ACTIVE_IDS` (config.py L.199-210)
alors qu'il est structurellement non-émetteur.** `GRAMMAR_REGIME.yaml` a `kind: grammar`,
`conditions: []`, `emits: {}` — strictement identique en structure aux 17 fichiers SHADOW.
`principle_engine.py` L.250-256 (`evaluate_principle`) retourne
`triggered: False, reason: "entree_documentaire_non_emettrice"` **inconditionnellement** dès
que `conditions` est vide, sans même consulter `v9_status`. Autrement dit, **GRAMMAR_REGIME ne
peut jamais déclencher de signal, quel que soit son statut ACTIVE** — le statut ACTIVE est
un artefact de configuration sans effet fonctionnel. Ceci contredit :
  - `docs/architecture/CHAINE_COGNITIVE.md` L.87-88 : « 10 principes ACTIVE routés vers le
    signal » — faux pour GRAMMAR_REGIME, donc **9 seulement** sont réellement routables ;
  - `docs/DOCTRINE.md` L.36 (Règle 11) : « Les principes sont des DÉTECTEURS » — un
    détecteur sans aucune condition ne détecte rien, il ne fait que journaliser sa propre
    non-évaluation ;
  - CHARTE Règle 4, L.111-112 : « Toute couche technique doit être justifiée par sa place
    dans la chaîne cognitive » — inclure GRAMMAR_REGIME dans `PRINCIPLE_ACTIVE_IDS` n'a
    aucune justification cognitive, uniquement un effet cosmétique sur le compte « 10 ACTIVE
    / 17 SHADOW » cité dans DOCTRINE.md Règle 11.
  Proposition de refonte : retirer `GRAMMAR_REGIME` de `PRINCIPLE_ACTIVE_IDS` (le classer
  SHADOW comme les 17 autres grammar), ou lui écrire de vraies `conditions:` s'il doit rester
  ACTIVE. Mettre à jour DOCTRINE.md Règle 11 en conséquence (9 ACTIVE réellement routables /
  18 grammar dont 18 non-émetteurs).

**F2 — Docstring `principle_engine.py` L.16-25 auto-contradictoire et obsolète** (détail §2.2).
Viole DOC_GOVERNANCE.md règle 1 en interne au même fichier (le docstring contredit la
constante `PRINCIPLE_ACTIVE_IDS` qu'il commente). Proposition : corriger le docstring
(20 → 18, et retirer la phrase datée sur ANTAGONIST_NODE/COALITION_NODE « hors périmètre »
puisqu'elle est immédiatement contredite par la phrase suivante du même paragraphe).

**F3 — Le vocabulaire obligatoire de la CHARTE (L.84-97 : force, scène, comportement,
fenêtre, zone, coalition, antagonisme, cinématique, orchestration multi-devises, confrontation
replay, mémoire de lecture) omet les quatre substantifs qui portent l'essentiel de DOCTRINE.md
et du code Phase 9 : « principe », « signal », « décision », « exploitabilité ».** CHARTE
L.98 dit explicitement : « Tout document ou agent qui n'utilise pas ce vocabulaire de base
risque de dévier du cœur PowerFlow. » Or `docs/LEXIQUE.md` L.19,20,27,31 canonise ces quatre
termes comme vocabulaire Phase 9 (« canonisés le 2026-07-05 » — la **même date** que la
création de la CHARTE) sans qu'ils soient reportés dans la liste CHARTE. « Exploitabilité »
est même définie dans la CHARTE elle-même (« Définitions natives », L.81-82) mais absente de
la liste des objets obligatoires trois paragraphes plus loin (L.84-97) : incohérence interne
à la CHARTE, pas seulement avec DOCTRINE. Proposition de refonte : ajouter à CHARTE L.84-97 les
quatre termes manquants (au minimum « exploitabilité », déjà définie dans le même document),
ou expliciter dans la CHARTE que « principe/signal/décision » appartiennent à une couche
distincte volontairement hors du noyau perceptuel (auquel cas le documenter, pas le laisser
implicite).

**F4 — La chaîne cognitive canonique de la CHARTE (L.54-64 : 6 étapes, Forces → Scènes →
Comportements → Fenêtres → Exploitabilité → Exécution éventuelle) ne correspond plus à la
chaîne réellement implémentée et documentée dans `CHAINE_COGNITIVE.md` (L.11-28) et le
docstring `principle_engine.py` (L.3-5) : Forces → Scènes → Comportements → Fenêtres →
Exploitabilité → Régime → Principes → Signal → Décision → [Phase 9.7] Arbiter → RiskManager
→ PaperTradeLogger → [Phase 9.8] Heartbeat.** CHARTE L.56 : « Toute réflexion, toute
implémentation et toute architecture V9 doit respecter cet ordre » et L.65 : « Aucune couche
aval ne doit polluer ou court-circuiter une couche amont » — la CHARTE ne mentionne aucune des
couches Régime / Principes / Signal / Décision / Arbiter / RiskManager / PaperTradeLogger /
Heartbeat, alors que ce sont exactement les couches qui ont fait l'objet de la majorité des
livraisons 2026-07-05 → 2026-07-08. Ce n'est pas une simple omission éditoriale : CHARTE Règle
4 (« Architecture avant code », L.111-112) exige que toute couche technique soit *justifiée
par sa place dans la chaîne cognitive* — une justification qui, pour ces 8 couches, n'existe
dans aucun document estampillé CHARTE. Proposition de refonte : republier CHARTE §« Chaîne
cognitive officielle » en 9-10 étapes alignées sur `CHAINE_COGNITIVE.md`, ou introduire
explicitement dans la CHARTE une distinction entre « chaîne perceptuelle » (les 6 étapes
actuelles, immuables) et « chaîne opérationnelle aval » (Régime→Heartbeat, qui peut évoluer
sans réviser la CHARTE) — actuellement cette distinction existe *de facto* dans le code mais
n'est écrite nulle part dans un document doctrinal.

**F5 — Règle 29 (DOCTRINE.md L.108-200) rapatrie un bloc de doctrine V8 substantiel
(« §3.1+§3bis+§6+§8 de DOCTRINE_LECTURE_MARCHE.md V8 », 792 lignes source, L.110-112) sans
passer par la classification A/B/C/D obligatoire de MIGRATION_POLICY_V9.md.**
MIGRATION_POLICY_V9.md L.10-11 : « Rien n'entre dans V9 sans être classé dans une de ces 4
catégories » (A — reprendre tel quel / B — réécrire / C — archiver / D — respécifier), et
L.25-32 exige pour tout élément candidat : origine, utilité, dette, dépendances, place dans
la chaîne cognitive, décision A/B/C/D. CHARTE Règle 5 (L.114-115) : « Aucun héritage de V8
n'entre dans V9 sans audit, classification et justification. » Or DOCTRINE.md L.113 ne
documente qu'une « Adoption : confirmée par Søn 2026-07-07 (Q1=oui, Q2=les 2, Q3=tous,
Q4=non) » — une validation orale/Q&A, pas un audit A/B/C/D avec les 5 champs requis. Aucune
entrée `AUDIT_*` ou classification n'existe pour ce rapatriement dans `docs/audit/`.
Proposition de refonte : rédiger a posteriori la fiche d'audit A/B/C/D pour le contenu importé
en Règle 29 (probable classe B — « réécrire avant reprise », puisque le contenu a été
recontextualisé en 6 dimensions/3 comportements/mécanisme énergétique plutôt que recopié tel
quel), à verser dans `docs/audit/` pour combler ce trou de traçabilité.

### 3.3 Nouvelles frictions — TENSIONS (🟡)

**F6 — Rule 30 (DOCTRINE.md L.171-192) construit une table de seuils WIN/LOSS (5/20/50/200)
dont la légitimité repose explicitement sur R25 (« Aucun seuil chiffré inventé (règle 25) »,
L.187) — une règle déjà cataloguée 🔴 contradiction avec la CHARTE en §3.1.** Tant que R25
n'est pas tranchée (option A/B/C, jamais décidée — §3.1), toute règle qui s'appuie dessus
comme garde-fou (R30, et par extension R29 §3.2 L.165-169 sur les seuils COALITION_THRESHOLD /
ANTAGONISM_THRESHOLD / PLIURE_THRESHOLD) hérite de la même tension non résolue. Proposition :
trancher R25 en priorité (c'est un prérequis logique, pas seulement chronologique, à la
publication de R29/R30) avant d'ajouter de nouvelles règles qui la citent comme fondement.

**F7 — ORCHESTRATION_POLICY_V9.md (L.9-38) définit 7 rôles canoniques (Orchestrator,
force-reader, scene-builder, behavior-analyst, replay-confronter, window-gate, reviewer).**
L'implémentation Mode A réelle (STATE.md L.48-51, Phase 9.10) déploie 5 « agents chauds » +
1 supervisor + 1 reviewer : `force_reader, scene_builder, behavior_analyst, gatekeeper,
decision_maker`. Écarts : `gatekeeper` ≠ `window-gate` (nom différent, rôle probablement
identique — à confirmer), `decision_maker` n'a **aucun équivalent** dans la liste des 7 rôles
canoniques, `replay-confronter` est **absent** de l'implémentation Mode A, `supervisor`
n'existe pas non plus dans la liste canonique. CHARTE Règle 4 (Architecture avant code)
s'applique aussi aux agents : un rôle implémenté sans entrée correspondante dans
ORCHESTRATION_POLICY_V9.md est une couche technique non justifiée dans la doctrine.
Proposition de refonte : soit renommer les agents Mode A pour coller aux 7 rôles canoniques,
soit mettre à jour ORCHESTRATION_POLICY_V9.md pour documenter `gatekeeper`, `decision_maker`,
`supervisor` et expliciter pourquoi `replay-confronter` n'a pas (encore) d'agent dédié.

**F8 — DOCTRINE.md Règle 19 (L.44) : « Les chantiers agents/routing/skills auto-générés ne
démarrent pas avant canonisation live » — or Mode A (5 agents + supervisor + reviewer,
Phase 9.10) est déjà implémenté et opérationnel (STATE.md L.48-55) alors qu'aucune
« canonisation live » n'est encore actée : Règle 30 (L.184) précise que la Phase 13 complète
(seuil de canonisation crédible : WIN/LOSS ≥ 50) n'est pas atteinte (STATE.md L.70 :
« Critères objectifs WIN/LOSS ≥ 20 (règle 25) : non remplis »).** Tension entre l'intention
de la Règle 19 (attendre une preuve live avant d'agentifier) et l'état de fait (l'agentification
bornée existe déjà, en mode « veille »). Le doctrine ROADMAP.md distingue une Phase 10
« fédération d'agents » (gelée) de la Phase 9.10 « Mode A bornée » actuelle — la distinction est
réelle dans ROADMAP.md mais absente de la Règle 19 elle-même, qui ne nuance pas entre
« agentification fédérée » (visée, gelée) et « agentification bornée en observation »
(existante). Proposition : préciser Règle 19 pour exempter explicitement le Mode A borné
(observation seule, zéro auto-apply) de l'interdiction, en citant la distinction ROADMAP.md.

### 3.4 Frictions défendables (🟢) — non bloquantes, à documenter seulement

**F9 — Bounds informatifs dans 4 fichiers `grammar` (GRAMMAR_BREAK, GRAMMAR_CONTEXTE,
GRAMMAR_PULLBACK, GRAMMAR_REGIME) sans effet fonctionnel.** `evaluate_principle`
(`principle_engine.py` L.250-256) sort en premier sur `if not principle.conditions` avant
même de regarder `bounds`. Les bounds ajoutés lors des enrichissements 2026-07-06 (« Tâche
B/C ») sur ces 4 fichiers ne sont donc jamais lus par le moteur — ils documentent une intention
de seuils futurs, mais rien ne les distingue visuellement d'un seuil actif dans le YAML lui-
même. Ce n'est pas une contradiction doctrinale (les notes disent explicitement « Entrée
documentaire, non émetteur »), mais un risque de confusion pour toute relecture rapide.
Défendable en l'état, mais un commentaire explicite type `# INERTE tant que conditions: []`
en tête de bloc `bounds:` réduirait le risque de mésinterprétation.

**F10 — CHARTE Règle 1 (« Primauté de la lecture », L.102-103) et DOCTRINE Règle 20
(« Calibration-first », L.45) opèrent à deux niveaux différents (philosophie perceptuelle vs.
process d'ingénierie de session) et ne se contredisent pas au sens strict — le tableau
Telegram les rapproche de l'Interdit #4 (rentabilité) plutôt que de la Règle 1. Signalé ici
uniquement pour mémoire : si R20 est un jour révisée (§3.1, F0/R20), vérifier qu'elle ne
devient pas également incompatible avec la Règle 1.

---

## 4. Synthèse de sévérité — vue consolidée

| Sévérité | Frictions déjà connues (Telegram) | Frictions nouvelles (cet audit) | Total |
|---|---|---|---|
| 🔴 Contradiction | R20, R25, R27 (3, pas 4 — voir F0) | F1, F2, F3, F4, F5 (5) | 8 |
| 🟡 Tension | R3, R10, R13, R22, R23 (5) | F6, F7, F8 (3) | 8 |
| 🟢 Défendable | — | F9, F10 (2) | 2 |
| **Total** | **8** | **10** | **18** |

---

## 5. Inventaire qualité des 17 (18) SHADOW

### 5.1 Constat central

Les 17 fichiers `kind: grammar` en statut SHADOW (+ GRAMMAR_REGIME, structurellement
identique mais classé ACTIVE, cf. F1) ont **tous** `conditions: []` et `emits: {}`. Aucun
n'a jamais émis une seule évaluation positive, non pas parce que leurs seuils sont trop stricts
ou parce que les données manquent, mais parce que **le code retourne `triggered: False` de
façon inconditionnelle avant même d'évaluer une seule condition** (`principle_engine.py`
L.250-256). Le débat doctrinal Søn (position D2 du checkpoint Telegram : les YAML sont des
« descripteurs de lecture », pas des « prédicteurs statistiques » à valider par hit_rate) est
donc **prématuré tant que ces 17 fichiers n'ont aucune condition écrite** — qu'on choisisse
l'option A, B ou C pour R25, aucune des trois n'a d'effet observable sur ces 17 fichiers tant
qu'ils restent des coquilles vides. Le vrai chantier bloquant n'est pas la politique de
promotion (R25), c'est l'écriture des conditions elles-mêmes.

### 5.2 Refactor nécessaire — verdict par fichier

| Fichier | Refactor nécessaire | Justification |
|---|---|---|
| GRAMMAR_ABSORPTION | **OUI** | 0 condition, source `zone_diagnostics` déjà alimentée (ZoneDetector livré, `CHAINE_COGNITIVE.md` L.103) — les données existent, rien n'empêche d'écrire des conditions réelles |
| GRAMMAR_ANTAGONISME | **OUI** | 0 condition ; source `pf_tick_cycle_detector` — dépendance V8 à ré-auditer avant d'écrire des conditions (pas de portage direct constaté côté V9) |
| GRAMMAR_BREAK | **OUI** | 0 condition malgré 2 enrichissements de notes (2026-07-06) qui décrivent déjà la logique attendue (`coalition_mtf_score >= 2`, `risk_sentiment == RISK_ON`, `coalition_mtf_depth in [H1,H4,D1]`) : le texte des conditions à écrire est déjà rédigé en note, il ne reste qu'à le transcrire en `conditions:` YAML |
| GRAMMAR_COALITION | **OUI** | 0 condition ; source `pf_multidevise.py`, champ `coalition_strength`/`coalitions_count` déjà PROPAGÉ (CONTEXT_CONTRACT.md L.44-45) — donnée disponible, condition non écrite |
| GRAMMAR_CONTEXTE | **OUI** | 0 condition malgré 17 champs documentés en note (session_marche, heure_utc, jour_semaine, marche_ouvert, contexte_temporel_fenetre) tous PROPAGÉS (CONTEXT_CONTRACT.md L.91-93) — cas le plus mûr pour passage immédiat en conditions réelles |
| GRAMMAR_CROISEMENT | **OUI** | 0 condition ; source `pf_tick_cycle_detector` — même réserve que GRAMMAR_ANTAGONISME |
| GRAMMAR_EXHAUSTION | **OUI** | 0 condition ; source `pf_grammar.py` — à ré-auditer, pas de champ V9 équivalent identifié dans CONTEXT_CONTRACT.md |
| GRAMMAR_EXTENSION | **OUI** | 0 condition ; champ `compression_extension.etat/intensite` déjà PROPAGÉ (CONTEXT_CONTRACT.md L.73-74) — donnée disponible |
| GRAMMAR_GRAVITE | **NON (à archiver)** | source `pf_relational_gravity_probe` — aucun équivalent V9 dans CONTEXT_CONTRACT.md ni dans les couches Scènes/Comportements ; candidat classe C (archiver) plutôt que refactor tant que la donnée source n'existe pas côté V9 |
| GRAMMAR_INVERSION | **NON (à archiver)** | idem GRAMMAR_GRAVITE, source `pf_tick_cycle_detector`, aucune donnée V9 équivalente confirmée |
| GRAMMAR_LEADER_FOLLOWER | **OUI** | source `pf_personalities` — mais `leader` (par coalition) est déjà PROPAGÉ (CONTEXT_CONTRACT.md L.46) ; rapprochement possible avec les champs `rotation_leadership.*` déjà consommés par PrincipleEngine |
| GRAMMAR_LOCK | **OUI** | 0 condition ; source `time_compression_events`, apparentée à GRAMMAR_SQUEEZE et GRAMMAR_BREAK qui partagent la même source — mutualisable |
| GRAMMAR_OPPOSITION | **OUI** | 0 condition ; champ `antagonismes_json.devises_en_conflit` déjà PROPAGÉ (CONTEXT_CONTRACT.md L.57) |
| GRAMMAR_PULLBACK | **OUI** | 0 condition malgré 2 sessions d'enrichissement de notes très détaillées (bascule_detectee, persistance_confirmee, bascule_intensite, point_de_rupture_declencheur, est_variante) — texte de conditions déjà rédigé en note, cas prioritaire pour transcription |
| GRAMMAR_RESPIRATION | **OUI** | source `pf_zone_breathing_topology`, apparentée à ELASTIC_BREATH (node_rule ACTIVE existant sur le même thème) — possibilité de dériver les conditions par symétrie |
| GRAMMAR_SQUEEZE | **OUI** | 0 condition ; source `time_compression_events`, partagée avec GRAMMAR_LOCK/GRAMMAR_BREAK |
| GRAMMAR_TENSION | **OUI** | champ `cinematique_json` (pente, courbure, pliure) largement PROPAGÉ (CONTEXT_CONTRACT.md L.63-77) — donnée disponible en abondance, condition non écrite |
| GRAMMAR_REGIME | **OUI (prioritaire)** | classé ACTIVE mais structurellement inerte (F1) — soit écrire ses conditions immédiatement (le corps de règle est déjà rédigé en note : risk_sentiment × régime, coalition_mtf_score, persistance_confirmee, contexte_temporel_fenetre), soit le repasser SHADOW en attendant |

**Synthèse** : 15 fichiers sur 18 ont un refactor OUI justifié par des données déjà PROPAGÉES
et disponibles dans CONTEXT_CONTRACT.md — le travail de rédaction des conditions est
documenté dans leurs propres notes pour au moins 4 d'entre eux (GRAMMAR_BREAK, GRAMMAR_CONTEXTE,
GRAMMAR_PULLBACK, GRAMMAR_REGIME). 2 fichiers (GRAMMAR_GRAVITE, GRAMMAR_INVERSION) n'ont pas
de donnée source V9 confirmée et sont candidats à l'archivage (classe C MIGRATION_POLICY_V9.md)
plutôt qu'au refactor tant que cette donnée n'existe pas.

---

## 6. Recommandations de refonte priorisées

1. **Corriger F0** — clarifier le décompte réel des contradictions (3, pas 4) avant toute
   décision CEO fondée sur ce chiffre.
2. **Trancher R25** (option A/B/C, jamais décidée depuis le 2026-07-07) — bloquant logique
   pour F6 (R30 en dépend) et pour tout chantier de refactor des 17 SHADOW en §5.
3. **Corriger F1/F2** immédiatement — retirer GRAMMAR_REGIME de `PRINCIPLE_ACTIVE_IDS` (ou lui
   écrire des conditions) et corriger le docstring `principle_engine.py` : correctifs
   mécaniques, faible risque, forte valeur de cohérence doc/code.
4. **Republier CHARTE_COGNITIVE_V9.md** (F3 + F4) — ajouter le vocabulaire manquant et
   documenter la chaîne opérationnelle aval (Régime→Heartbeat) sans nécessairement l'élever
   au rang de « chaîne cognitive officielle » immuable, mais au moins en la nommant.
5. **Écrire la fiche d'audit A/B/C/D manquante pour la Règle 29** (F5) a posteriori, à verser
   dans `docs/audit/`.
6. **Réaligner ORCHESTRATION_POLICY_V9.md sur Mode A** (F7/F8) — nommage des rôles et exemption
   explicite du Mode A borné dans la Règle 19.
7. **Refactor des 15 YAML SHADOW à donnée disponible** (§5.2) — en commençant par les 4 dont le
   texte de conditions est déjà rédigé en note (GRAMMAR_BREAK, GRAMMAR_CONTEXTE,
   GRAMMAR_PULLBACK, GRAMMAR_REGIME).
8. **Archiver (classe C) GRAMMAR_GRAVITE et GRAMMAR_INVERSION** faute de donnée source V9.

Aucune de ces actions ne requiert de modification de code dans le cadre de cette Phase A —
elles sont listées ici comme périmètre de la Phase B (réalignement), non exécutées.
