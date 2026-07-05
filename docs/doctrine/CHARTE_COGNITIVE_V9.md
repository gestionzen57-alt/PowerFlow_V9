# CHARTE COGNITIVE V9

## Statut
Document fondateur de PowerFlow V9.
Version de chantier : 0.1
Date : 2026-07-05

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

Toute réflexion, toute implémentation et toute architecture V9 doit respecter cet ordre :

1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

Aucune couche aval ne doit polluer ou court-circuiter une couche amont.

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

- force
- scène
- comportement
- fenêtre
- zone
- coalition
- antagonisme
- cinématique
- orchestration multi-devises
- confrontation replay
- mémoire de lecture

Tout document ou agent qui n'utilise pas ce vocabulaire de base risque de dévier du cœur PowerFlow.

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