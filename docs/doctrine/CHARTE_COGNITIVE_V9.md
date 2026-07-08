# CHARTE COGNITIVE V9

## Statut
Document fondateur de PowerFlow V9.
Version de chantier : 0.2
Date : 2026-07-08

## Historique des révisions
- **0.1** (2026-07-05) — Création. 6 étapes de chaîne cognitive, vocabulaire de 11 termes.
- **0.2** (2026-07-08) — Réalignement Phase 9.8 Phase B (voir `docs/audit/AUDIT_DOCTRINE_REPORT.md`,
  frictions F3/F4). Vocabulaire étendu à 19 termes (+exploitabilité, principe, signal,
  décision, arbiter, risk_manager, paper_trade, heartbeat). Chaîne cognitive scindée en
  chaîne perceptuelle amont (6 couches immuables) et chaîne opérationnelle aval (4 couches
  évolutives), 10 couches au total — la CHARTE v0.1 ne documentait que les 6 couches amont
  et laissait les couches aval (Régime→Heartbeat, livrées Phase 9 à 9.8) hors de toute
  autorité doctrinale écrite.

## Mission

PowerFlow V9 est un système de lecture comportementale du marché.
Sa mission première n'est pas de produire un trade, mais de reconnaître fidèlement
la dynamique réelle des forces telle qu'elle est perçue par l'opérateur.

La priorité absolue est :

1. fidélité de lecture
2. cohérence comportementale
3. capacité de mémoire / confrontation
4. qualification de fenêtre
5. exploitabilité éventuelle
6. automatisation en dernier

## Phrase directrice

Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.

## Ce que V9 lit

V9 lit en priorité :

- les forces multi-devises
- la structure multi-timeframe
- la temporalité
- les zones
- les fenêtres d'opportunité
- les coalitions
- les antagonismes
- la cinématique des forces
- les changements d'équilibre
- les repulsions / rejets / recroisements
- les compressions / extensions
- les cascades temporelles
- les comportements fractals avec singularités locales

## Ce que V9 ne doit jamais faire

- Confondre lecture et décision.
- Confondre comportement et signal.
- Confondre scène et trade.
- Laisser une logique de rentabilité déformer la perception amont.
- Introduire un outillage (RAG, scoring, agentisation, Discord multi-IA, etc.) avant d'avoir localisé sa place exacte dans la chaîne cognitive.
- Hériter implicitement d'anciennes mémoires, conventions, ou dettes de V8/Hermes.

## Chaîne cognitive officielle

Toute réflexion, toute implémentation et toute architecture V9 doit respecter cet ordre.
La chaîne totale compte **10 couches**, scindées en deux blocs de nature différente :

### Chaîne perceptuelle amont (immuable, 6 couches)

1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Régime

Ce sont les couches de **lecture pure** : elles décrivent la scène de marché sans jamais
statuer sur une action. Toute révision de cette liste (ajout, retrait, réordonnancement)
exige une révision explicite de la CHARTE elle-même (nouvelle version, décision Søn
documentée dans `DECISIONS_LOG.md`) — elles ne peuvent pas évoluer par simple livraison de
code. Note historique : la v0.1 nommait la 6ᵉ étape « Exécution éventuelle », une notion
abstraite plutôt qu'une couche concrète. La v0.2 la remplace par **Régime**, qui est la
6ᵉ couche réellement implémentée (`core/v9/regime_detector.py`) et reste de la lecture pure
(classification de contexte, pas de décision) — « l'exécution éventuelle » qu'elle
annonçait est désormais explicitée dans la chaîne aval ci-dessous.

### Chaîne opérationnelle aval (évolutive, 4 couches)

7. **Principes → Signal** — les principes (`core/v9/principle_engine.py`) sont des
   détecteurs déclaratifs évalués contre la chaîne amont ; un principe déclenché émet un
   signal, jamais un ordre.
8. **Décision** — consolidation des signaux d'un même snapshot en une décision candidate.
9. **Arbiter → RiskManager** — arbitrage inter-principes et filtrage par le risque
   (`core/v9/arbiter.py`, `core/v9/risk_meter.py`).
10. **PaperTradeLogger → Heartbeat** — exécution simulée (paper_trade) et supervision de
    la chaîne vivante (`core/v9/heartbeat.py` / `scripts/v9_heartbeat.py`).

Cette chaîne aval peut évoluer (nouvelles sous-étapes, nouveaux modules) sans réviser la
CHARTE, à condition de respecter la Règle 4 (architecture avant code) et de ne jamais
remonter modifier une couche amont. Elle documente ce que la v0.1 laissait implicite dans
le code sans aucune autorité doctrinale écrite (voir historique des révisions ci-dessus).

**Règle invariante, aux deux blocs** : Aucune couche aval ne doit polluer ou court-circuiter
une couche amont. Aucune couche amont ne doit être déformée pour satisfaire une couche aval
(ex : un principe orienté rentabilité ne doit jamais influencer Régime, Exploitabilité,
Fenêtres, etc.).

## Définitions natives

### Force
Variation structurée d'intensité, direction, pression ou équilibre dans le jeu multi-devises et multi-timeframe.

### Scène
Configuration locale du marché à un instant ou sur une fenêtre donnée, avec ses relations de forces, zones et temporalités.

### Comportement
Dynamique observable de la scène dans le temps : lutte, bascule, contraction, extension, rotation, maintien, rupture, annulation, etc.

### Fenêtre
Moment ou période où une dynamique devient potentiellement exploitable, surveillable ou au contraire invalide.

### Exploitabilité
Évaluation tardive et subordonnée à la qualité de lecture. Ne définit jamais la réalité amont.

## Objets obligatoires du vocabulaire V9

Chaîne perceptuelle amont :
- force
- scène
- comportement
- fenêtre
- zone
- coalition
- antagonisme
- cinématique
- exploitabilité
- orchestration multi-devises
- confrontation replay
- mémoire de lecture

Chaîne opérationnelle aval (ajout v0.2 — voir « Chaîne cognitive officielle » ci-dessus) :
- principe
- signal
- décision
- arbiter
- risk_manager
- paper_trade
- heartbeat

Tout document ou agent qui n'utilise pas ce vocabulaire de base risque de dévier du cœur
PowerFlow. Les 7 termes de la chaîne aval désignent des mécanismes opérationnels, pas des
objets de perception : leur présence dans ce vocabulaire ne leur donne pas la même
immuabilité que les termes amont (cf. distinction des deux chaînes ci-dessus).

## Règles de gouvernance

### Règle 1 — Primauté de la lecture
Le système doit d'abord voir, puis décrire, puis qualifier. Agir vient après.

### Règle 2 — Séparation perception / exploitabilité
Une lecture juste peut ne produire aucun trade. C'est normal.

### Règle 3 — Mémoire au service de la perception
La mémoire sert d'abord à conserver et confronter les lectures, scènes, comportements et fenêtres.

### Règle 4 — Architecture avant code
Toute couche technique doit être justifiée par sa place dans la chaîne cognitive.

### Règle 5 — Migration curée
Aucun héritage de V8 n'entre dans V9 sans audit, classification et justification.

## Architecture mentale cible

PowerFlow V9 doit devenir :

- une machine qui lit le film du marché
- une machine qui découpe des scènes
- une machine qui reconnaît des comportements
- une machine qui confronte le présent au passé
- une machine qui qualifie des fenêtres
- une machine qui n'autorise l'exploitabilité qu'en dernier ressort

## Conclusion

PowerFlow V9 n'est pas un bot de trading en premier.
PowerFlow V9 est un système de compréhension structurée des forces de marché.