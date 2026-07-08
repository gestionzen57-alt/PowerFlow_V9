# AUDIT A/B/C/D rétrospectif — Règle 29 (import DOCTRINE_LECTURE_MARCHE.md V8)

## 0. Identification

- **Date** : 2026-07-08
- **Commande** : CEO — Phase 9.8 Phase B, livrable B6
- **Objet** : audit A/B/C/D rétrospectif du rapatriement effectué le 2026-07-07 dans
  `docs/DOCTRINE.md` Règle 29, tel qu'exigé par
  [`docs/doctrine/MIGRATION_POLICY_V9.md`](../doctrine/MIGRATION_POLICY_V9.md)
  (« Rien n'entre dans V9 sans être classé dans une de ces 4 catégories »).
- **Motif de l'audit** : `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.2 friction F5 constate que
  la Règle 29 a été rapatriée sur la seule base d'une validation orale/Q&A Søn
  (« Adoption : confirmée par Søn 2026-07-07 (Q1=oui, Q2=les 2, Q3=tous, Q4=non) »,
  `docs/DOCTRINE.md` L.113) sans qu'aucune fiche d'audit A/B/C/D à 5 champs n'ait jamais été
  écrite ni versée dans `docs/audit/`. Ce document comble ce trou de traçabilité a posteriori.
  Aucune modification de code ni de `docs/DOCTRINE.md` Règle 29 elle-même n'est requise par cet
  audit — la Règle 29 reste en l'état, ce document ne fait qu'expliciter sa classification.

## 1. Origine

Source : [`workspace/perplexity/memory/DOCTRINE_LECTURE_MARCHE.md`](../../workspace/perplexity/memory/DOCTRINE_LECTURE_MARCHE.md)
(« Doctrine de Lecture du Marché — PowerFlow V8 »), **792 lignes**, statut source
`ACTIF` / `source_de_verite: NON`, dernière mise à jour V8 2026-06-29.

Sections importées dans `docs/DOCTRINE.md` Règle 29 (L.108-200) :
- **§3.1** — 3 comportements en zone (REJET / ABSORPTION / ÉQUILIBRE) et leur construction HTF
- **§3bis** — lecture d'une arrivée en zone en 6 dimensions (trajectoire, alignement multi-TF,
  carte des coalitions, histoire récente, contexte marché, signature comportementale)
- **§6** (§6.1 cité) — mécanisme énergétique en cascade (stockage → croisement → attente →
  casse → cascade → épuisement) et rôle par timeframe
- **§8** — règle hiérarchique non-HTF-first conditionnelle (HTF = biais interdit, MTF =
  contexte, LTF = confirmation, anti-biais HTF-first)

Rapatriement effectué le 2026-07-07 (commit `72f1361`), adoption confirmée par Søn le même
jour par échange Q&A (Q1=oui, Q2=les 2, Q3=tous, Q4=non — le détail des 4 questions n'est pas
autrement documenté dans le repo, seule la synthèse des réponses figure dans `DOCTRINE.md`).

## 2. Utilité

Directement structurante pour la Phase 9 / 9.10 :
- Introduit la doctrine **zone-type × multi-TF × non-HTF-first conditionnelle**, absente de la
  doctrine V9 avant le 2026-07-07 alors que `core/v9/zone_detector.py` et
  `core/v9/zone_db.py` (Phase 9) produisaient déjà des `zone_diagnostics` sans cadre doctrinal
  explicite pour les interpréter en scène complète.
- Fournit le vocabulaire des **4 types de zone** (naissance / 2e_jambe / continuation /
  respiration) désormais persistés (`zone_type`, Règle 29 (a)) et consommés par
  `window_gate` (fenêtre `naissance_isolee`, Règle 29 (b)) et `arbiter.consolidate`
  (pondération zone-type × session, Règle 29 (c)).
- Corrige un biais V8 identifié explicitement par Søn (« la cascade fonctionne dans
  alignement, mais il y a pas que cela [...] chaque moment est unique ») qui aurait autrement
  été silencieusement reproduit en V9 sans ce rapatriement.

## 3. Dette

- **792 lignes source** pour ~90 lignes effectivement portées dans `DOCTRINE.md` Règle 29 —
  ratio de compression élevé (~11 %), le reste du document V8 (sections non citées, mémoire de
  session V8, historique de décisions V8) n'est pas repris et reste `source_de_verite: NON`
  côté V8 (le fichier source n'est conservé que comme référence historique, jamais comme
  autorité V9).
- **Recontextualisation nécessaire** : le texte importé ne reprend pas le vocabulaire V8 tel
  quel — il a été reformulé en termes de champs V9 concrets (`zone_type`,
  `contexte_temporel_fenetre`, `arbiter.consolidate`) et de conséquences code explicites
  (§ "Conséquences code" de la Règle 29), ce que MIGRATION_POLICY_V9.md exige pour la classe B
  (« élément utile mais pollué par ancienne structure [...] ») par opposition à la classe A
  (reprise telle quelle, qui n'aurait pas nécessité de reformulation).
- **Seuils chiffrés hérités** : COALITION_THRESHOLD=5.38, ANTAGONISM_THRESHOLD=31.39,
  PLIURE_THRESHOLD=1.7 sont importés comme « repères de calibrage, pas des règles figées »
  (§3.2 du texte source) — dette potentielle si un jour traités comme figés sans recalibrage
  V9 (garde-fou déjà écrit dans la Règle 29 elle-même : « évolueront avec l'apprentissage,
  Phase 13, WIN/LOSS ≥ 50 »).

## 4. Dépendances

- `core/v9/zone_db.py` / `core/v9/zone_detector.py` — persistance `zone_type` (Règle 29 (a))
- `core/v9/window_gate.py` (ou module équivalent) — assouplissement conditionnel
  `naissance_isolee` avec `validation_hitl_requise=true` renforcé (Règle 29 (b))
- `core/v9/arbiter.py` (`consolidate`) — pondération zone-type × session × inertie devise
  (Règle 29 (c)) ; tests associés dans `tests/test_v9_arbiter_rule29.py` (3 xfail documentés,
  fixtures in-memory fragiles — voir `DECISIONS_LOG.md` 2026-07-07)
- `docs/architecture/CONTEXT_CONTRACT.md` — les champs consommés par la Règle 29
  (`contexte_temporel_fenetre`, `coalition_mtf_score`, etc.) doivent rester PROPAGÉS
  (Règle 21) ; recoupe les champs déjà réutilisés par le refactor GRAMMAR_CONTEXTE
  (Phase 9.8 B4)
- `docs/DOCTRINE.md` Règle 30 (WIN/LOSS) — cite explicitement la Règle 29 §4 comme fondement
  du recalibrage arbiter à ≥ 50 déclenchements

## 5. Place dans la chaîne cognitive

Selon la distinction introduite en Phase 9.8 B1
([`docs/doctrine/CHARTE_COGNITIVE_V9.md`](../doctrine/CHARTE_COGNITIVE_V9.md) v0.2, « Chaîne
cognitive officielle ») : la Règle 29 opère principalement sur les **couches 5-6 de la chaîne
perceptuelle amont** (Exploitabilité, Régime) — la lecture en 6 dimensions d'une arrivée en
zone (§3bis) et la qualification zone-type nourrissent directement l'évaluation
d'Exploitabilité et la classification de Régime, avant toute couche opérationnelle aval. Sa
conséquence code sur `arbiter.consolidate` (couche 9 aval, Arbiter → RiskManager) est un effet
en aval de cette lecture, pas une redéfinition de la lecture elle-même — cohérent avec la règle
invariante CHARTE (« aucune couche aval ne doit polluer une couche amont »).

## 6. Décision A/B/C/D

**Classe B — Réécrire avant reprise.** *(déjà fait le 2026-07-07 ; cet audit confirme et
documente la classification a posteriori, ne rouvre pas le rapatriement.)*

Justification : le contenu source (792 lignes, vocabulaire et structure V8) n'a pas été copié
tel quel (ce qui aurait été classe A) — il a été recontextualisé en 6 dimensions / 3
comportements / mécanisme énergétique / règle hiérarchique, avec des « Conséquences code »
explicitement réécrites pour référencer des modules et champs V9 (`zone_type`, `window_gate`,
`arbiter.consolidate`) qui n'existaient pas en V8 sous cette forme. Ce n'est ni une classe A
(élément déjà sain et directement réutilisable), ni une classe C (archiver — la doctrine reste
activement consommée par le code Phase 9.10), ni une classe D (respécifier depuis zéro — le
contenu V8 était suffisamment clair pour servir de socle, contrairement à un contenu « trop
confus, trop couplé, ou trop biaisé pour être sauvé »).

## 7. Non-régression

Cet audit ne modifie ni `docs/DOCTRINE.md`, ni le code, ni les tests. Il documente
rétrospectivement une décision déjà en production, pour combler le trou de traçabilité
identifié par `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.2 F5.
